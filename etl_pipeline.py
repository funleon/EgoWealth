import logging
import time
import os
import requests
import pandas as pd
import psycopg2
from psycopg2.extras import execute_values
from datetime import datetime
from dotenv import load_dotenv

# 設定日誌
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 載入環境變數
load_dotenv()
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "egowealth")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "password")
API_KEY = os.getenv("MARKET_API_KEY", "dummy_key")

def fetch_data_with_retry(url: str, params: dict, max_retries: int = 2, wait_seconds: int = 600) -> dict | None:
    """擷取並實作錯誤重試防呆機制的 API 請求函數"""
    for attempt in range(max_retries + 1):
        try:
            logger.info(f"正在擷取資料 (第 {attempt + 1} 次嘗試): {url}")
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"擷取失敗: {e}")
            if attempt < max_retries:
                logger.info(f"等待 {wait_seconds} 秒後重試...")
                time.sleep(wait_seconds)
            else:
                logger.error("達到最大重試次數，放棄擷取。")
                return None

def get_mock_market_data() -> pd.DataFrame:
    """
    假資料產生，模擬外部 API 拿到的各端點資料整併。
    實務上需透過 fetch_data_with_retry 打多個 API 端點後進行 dict -> df。
    """
    data = [
        {"ticker": "AAPL", "pe_ratio": 25.5, "yield": 0.5, "yoy_growth": 10.2, "roe": 140.5},
        {"ticker": "MSFT", "pe_ratio": 30.2, "yield": 0.8, "yoy_growth": 20.5, "roe": 40.2}, # Growth
        {"ticker": "NVDA", "pe_ratio": 60.5, "yield": 0.1, "yoy_growth": 50.5, "roe": 60.1}, # Growth
        {"ticker": "T",    "pe_ratio": 9.5,  "yield": 6.5, "yoy_growth": 1.2,  "roe": 10.5},  # Value
        {"ticker": "XOM",  "pe_ratio": 12.0, "yield": 5.2, "yoy_growth": 8.5,  "roe": 22.0},  # Value
        {"ticker": "TSLA", "pe_ratio": 50.0, "yield": 0.0, "yoy_growth": 15.0, "roe": 18.0},
        {"ticker": "O",    "pe_ratio": None, "yield": 5.8, "yoy_growth": 2.1,  "roe": None},  # Missing data
    ]
    df = pd.DataFrame(data)
    df["date"] = datetime.now().date()
    return df

def clean_and_merge_data(df: pd.DataFrame) -> pd.DataFrame:
    """資料清洗與合併"""
    # 填補缺失值或丟棄 (這裡展示將數值欄位缺失補 0，或可直接用 dropna)
    numeric_cols = ["pe_ratio", "yield", "yoy_growth", "roe"]
    df[numeric_cols] = df[numeric_cols].fillna(0)
    return df

def assign_ai_tags(df: pd.DataFrame) -> pd.DataFrame:
    """
    AI 標籤化：
    - 價值型 (Value)：PE < 15 且 殖利率 > 5.0。
    - 成長型 (Growth)：YoY > 20.0 且 ROE > 20.0。
    """
    def label_stock(row):
        # 注意: 確保 pe_ratio > 0 避免 PE < 15 將盈餘為負或缺失(補0)的算成優質
        is_value = (0 < row["pe_ratio"] < 15) and (row["yield"] > 5.0)
        is_growth = (row["yoy_growth"] > 20.0) and (row["roe"] > 20.0)
        
        tags = []
        if is_value:
            tags.append("Value")
        if is_growth:
            tags.append("Growth")
        
        return ",".join(tags) if tags else "Neutral"
    
    df["ai_tag"] = df.apply(label_stock, axis=1)
    return df

def upsert_to_db(df: pd.DataFrame):
    """冪等性寫入 Database"""
    if df.empty:
        logger.warning("DataFrame is empty. 略過寫入。")
        return

    # 準備寫入資料
    records = df[["ticker", "date", "pe_ratio", "yield", "yoy_growth", "roe", "ai_tag"]].to_records(index=False)
    data_list = list(records)

    conn = None
    try:
        conn = psycopg2.connect(
            host=DB_HOST,
            port=DB_PORT,
            dbname=DB_NAME,
            user=DB_USER,
            password=DB_PASSWORD
        )
        cur = conn.cursor()
        
        # 確保股票主檔(Stocks)內有紀錄，否則 Market_Data 的 FK 會報錯。這裡做個簡單的同步寫入(實務上可能透過其他流程同步)
        stocks_data = [(row["ticker"], row["ticker"] + " Inc.", "Unknown") for row in data_list]
        insert_stocks_query = """
            INSERT INTO Stocks (ticker, name, industry)
            VALUES %s
            ON CONFLICT (ticker) DO NOTHING;
        """
        execute_values(cur, insert_stocks_query, stocks_data)
        
        # 冪等性寫入 Market_Data
        insert_market_data_query = """
            INSERT INTO Market_Data (ticker, date, pe_ratio, "yield", yoy_growth, roe, ai_tag, updated_at)
            VALUES %s
            ON CONFLICT (ticker, date) DO UPDATE SET
                pe_ratio = EXCLUDED.pe_ratio,
                "yield" = EXCLUDED.yield,
                yoy_growth = EXCLUDED.yoy_growth,
                roe = EXCLUDED.roe,
                ai_tag = EXCLUDED.ai_tag,
                updated_at = CURRENT_TIMESTAMP;
        """
        execute_values(cur, insert_market_data_query, data_list)
        
        conn.commit()
        logger.info(f"成功更新 {len(data_list)} 筆市場數據。")
        
    except (Exception, psycopg2.DatabaseError) as error:
        logger.error(f"資料庫操作失敗: {error}")
        if conn:
            conn.rollback()
    finally:
        if conn is not None:
            conn.close()

def run_pipeline():
    logger.info("開始執行 ETL Pipeline...")
    
    # 1. 擷取與重試 (此處用 Mock 示範)
    raw_df = get_mock_market_data()
    
    # 2. 資料清洗與整併
    cleaned_df = clean_and_merge_data(raw_df)
    
    # 3. AI 標籤化
    tagged_df = assign_ai_tags(cleaned_df)
    
    logger.info(f"資料處理完成，預覽:\n{tagged_df.head()}")
    
    # 4. 冪等性寫入
    upsert_to_db(tagged_df)
    
    logger.info("ETL Pipeline 執行完畢。")

if __name__ == "__main__":
    run_pipeline()
