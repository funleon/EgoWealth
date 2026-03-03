from fastapi import APIRouter, Depends, Request, HTTPException
from typing import List, Dict, Any
from app.database import get_db_connection
from app.schemas import TransactionCreate, TransactionDelete, ImpersonateRequest
import psycopg2
from psycopg2.extras import RealDictCursor

router = APIRouter()

def get_db():
    conn_gen = get_db_connection()
    conn = next(conn_gen)
    try:
        yield conn
    finally:
        try:
            next(conn_gen)
        except StopIteration:
            pass

@router.get("/recommendations", response_model=List[Dict[str, Any]])
def get_recommendations(request: Request, db=Depends(get_db)):
    """
    動態 AI 評分引擎
    利用 ->> 運算子即時運算 JSONB 權重與 Market_Data，回傳前 5 名。
    """
    user_id = request.state.target_user_id
    if not user_id:
        raise HTTPException(status_code=401, detail="User ID is missing")

    query = """
    WITH UserWeights AS (
        SELECT weight_map
        FROM User_Preferences
        WHERE user_id = %s
    )
    SELECT 
        m.ticker, 
        m.date,
        m.pe_ratio,
        m.yield,
        m.yoy_growth,
        m.roe,
        m.ai_tag,
        (
            (COALESCE(m.pe_ratio, 0) * COALESCE((uw.weight_map->>'pe_weight')::numeric, 1.0)) +
            (COALESCE(m.yield, 0) * COALESCE((uw.weight_map->>'yield_weight')::numeric, 1.0)) +
            (COALESCE(m.yoy_growth, 0) * COALESCE((uw.weight_map->>'yoy_weight')::numeric, 1.0)) +
            (COALESCE(m.roe, 0) * COALESCE((uw.weight_map->>'roe_weight')::numeric, 1.0))
        ) AS personalized_score
    FROM Market_Data m
    CROSS JOIN UserWeights uw
    ORDER BY personalized_score DESC
    LIMIT 5;
    """
    
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute(query, (user_id,))
        results = cur.fetchall()
        # dict conversions for datetime
        return [dict(row) for row in results]
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()

@router.post("/portfolio/transactions")
def add_transaction(tx: TransactionCreate, request: Request, db=Depends(get_db)):
    """
    投資組合記帳同步 - 新增明細 (使用 Transaction 保證一致性)
    """
    user_id = request.state.target_user_id
    cur = db.cursor()
    try:
        # 1. 寫入明細表
        insert_tx_query = """
            INSERT INTO Portfolio_Transactions (user_id, ticker, action, price, quantity)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING tx_id;
        """
        cur.execute(insert_tx_query, (user_id, tx.ticker, tx.action, tx.price, tx.quantity))
        
        # 影響 Summary 計算邏輯: 如果是 SELL, 股數減少, 但均價不變 (這裡採簡化版算術: 僅加減)
        # 實務上平均成本計算法隨會計準則而異。我們用 SQL 動態重算歷史所有紀錄。
        
        upsert_summary_query = """
            INSERT INTO Portfolio_Summary (user_id, ticker, total_shares, average_cost, updated_at)
            VALUES (
                %(user_id)s, %(ticker)s, 
                CASE WHEN %(action)s = 'BUY' THEN %(quantity)s ELSE -%(quantity)s END, 
                %(price)s, CURRENT_TIMESTAMP
            )
            ON CONFLICT (user_id, ticker) DO UPDATE SET
                total_shares = Portfolio_Summary.total_shares + (CASE WHEN %(action)s = 'BUY' THEN %(quantity)s ELSE -%(quantity)s END),
                -- 簡化版均價: 只在買入時攤平重算
                average_cost = CASE 
                    WHEN %(action)s = 'BUY' THEN 
                        ((Portfolio_Summary.average_cost * Portfolio_Summary.total_shares) + (%(price)s * %(quantity)s)) 
                        / NULLIF((Portfolio_Summary.total_shares + %(quantity)s), 0)
                    ELSE Portfolio_Summary.average_cost
                END,
                updated_at = CURRENT_TIMESTAMP;
        """
        cur.execute(upsert_summary_query, {
            "user_id": user_id,
            "ticker": tx.ticker,
            "action": tx.action,
            "price": tx.price,
            "quantity": tx.quantity
        })
        
        db.commit() # Database Transaction 提交
        return {"status": "success", "message": "Transaction added and summary updated"}
    except Exception as e:
        db.rollback() # 出錯回滾
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        cur.close()

@router.delete("/portfolio/transactions")
def delete_transaction(tx: TransactionDelete, request: Request, db=Depends(get_db)):
    """
    投資組合記帳同步 - 刪除明細 (簡化實作: 實務上可能需要反向重算整串均價，這裡僅做總股數反向更正以示範 DB Transaction)
    """
    user_id = request.state.target_user_id
    cur = db.cursor(cursor_factory=RealDictCursor)
    try:
        # 取得明細
        cur.execute("SELECT * FROM Portfolio_Transactions WHERE tx_id = %s AND user_id = %s", (tx.tx_id, user_id))
        record = cur.fetchone()
        if not record:
            raise HTTPException(status_code=404, detail="Transaction not found")
        
        # 刪除明細
        cur.execute("DELETE FROM Portfolio_Transactions WHERE tx_id = %s", (tx.tx_id,))
        
        # 反向更新總表數量
        action = record['action']
        quantity = record['quantity']
        # BUY 被刪除 -> 扣除股數, SELL 被刪除 -> 加回股數
        reverse_modifier = -quantity if action == 'BUY' else quantity
        
        update_summary = """
            UPDATE Portfolio_Summary 
            SET total_shares = total_shares + %s, updated_at = CURRENT_TIMESTAMP
            WHERE user_id = %s AND ticker = %s;
        """
        cur.execute(update_summary, (reverse_modifier, user_id, record['ticker']))
        
        db.commit()
        return {"status": "success", "message": "Transaction deleted vertically"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        cur.close()

@router.post("/admin/impersonate")
def admin_impersonate(request: Request, payload: ImpersonateRequest):
    """
    Admin 身分模擬 API。
    實務上可能將目標 User ID 寫入 Session/JWT Token 並回傳，或者要求前端隨後帶上特製 Header。
    這裡回傳 Token 指示。
    """
    actor_id = request.state.actor_user_id
    # (驗證 actor_id role == 'admin')
    
    return {
        "status": "impersonating",
        "actor_id": actor_id,
        "target_user_id": payload.target_user_id,
        "message": "Please include X-Impersonate-ID header in subsequent requests"
    }
