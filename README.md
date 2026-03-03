# EgoWealth: AI 財務投資與資產管理系統

## 📌 系統介紹
本專案為一個專屬的 **AI 財務投資與資產管理系統** 基礎骨架，旨在協助使用者管理投資組合、追蹤市場數據，並利用 AI 標籤化與使用者自訂參數（JSONB 格式）進行個人化的動態股票推薦。

系統採用 **Python (FastAPI)** 作為後端核心框架，並以 **PostgreSQL** 作為關聯式資料庫。設計上強調資料一致性（Transaction）、冪等性寫入（UPSERT）與企業級的 Admin 身分模擬稽核（Audit）機制。

---

## ✨ 核心功能說明

### 1. 資料庫設計與一致性防護
- **完善關聯設計**：設計 `Users`、`Stocks`、`Market_Data` 等實體關聯表（`init.sql`）。
- **JSONB 彈性設定**：將用戶的權重設定（`pe_weight`, `yield_weight` 等）儲存於 `User_Preferences` 的 `JSONB` 欄位中，保留未來的擴展彈性。
- **投資組合雙表同步**：交易明細（`Portfolio_Transactions`）與總覽（`Portfolio_Summary`）分開管理，並具備 `UNIQUE`、`CHECK` 等完整約束以確保資料準確性。

### 2. 每日自動化 ETL 腳本 (`etl_pipeline.py`)
- **防呆抓取機制**：實作呼叫外部 API 時的 Timeout 設定、錯誤攔截與 10 分鐘等待重試邏輯。
- **Pandas 資料整併與清洗**：處理多端點來源的收盤價、本益比、殖利率等數據，並處理缺失值（NaN）。
- **AI 標籤化 (AI Tagging)**：
  - **價值型 (Value)**：PE < 15 且 殖利率 > 5.0。
  - **成長型 (Growth)**：YoY > 20.0 且 ROE > 20.0。
- **冪等性儲存**：使用 Raw SQL 的 `INSERT ... ON CONFLICT DO UPDATE` 完成無縫的資料庫 UPSERT，重複執行也不會產生多餘的重複資料。

### 3. FastAPI 後端核心業務
- **動態推薦引擎**：直接於 PostgreSQL 內以 `->>` 運算子即時讀取 JSONB 權重進行乘積計算與排序，找出最適合用戶配置的前 5 名股票。
- **投資組合高一致性記帳**：利用 Database Transaction（回滾防護），確保每次新增或刪除投資組合明細時，總表（Summary）的總股數與均價能同步更新，任一步驟出錯即撤銷交易。
- **Admin 身分模擬與稽核**：
  - 提供 Middleware 權限攔截，讓管理員能以 `X-Impersonate-ID` 模擬客戶視角。
  - 在模擬身分期間，防護任何有副作用的操作（POST、PUT、DELETE），自動且強制地將動作軌跡寫入 `Audit_Logs`。

---

## 🚀 安裝及執行方式

### 系統環境需求
- **Python**: 3.9+ 
- **Database**: PostgreSQL 13+

### 步驟 1：建立資料庫
請先確保本機或遠端已開啟 PostgreSQL 服務，並建立名為 `egowealth` 的資料庫。
然後透過匯入 `init.sql` 建立基礎結構：
```bash
psql -U postgres -d egowealth -f init.sql
```

### 步驟 2：設定環境變數
複製範例檔建立設定檔，並將其填入您實際的資料庫帳戶與連線資訊：
```bash
cp .env.example .env
```

### 步驟 3：安裝 Python 依賴包
在專案根目錄執行：
```bash
pip install -r requirements.txt
```

### 步驟 4：執行每日 ETL 腳本
執行自動化資料抓取與標籤化腳本以初始化 `Market_Data`：
```bash
python etl_pipeline.py
```

### 步驟 5：啟動 FastAPI 伺服器
執行主程式以啟動 API Server：
```bash
uvicorn app.main:app --reload
```
預設服務將會跑在 `http://127.0.0.1:8000`。

---

## 🎯 驗證方式與操作說明

### 1. Swagger UI 測試 (核心 API 操作)
伺服器啟動後，開啟瀏覽器造訪 **[http://localhost:8000/docs](http://localhost:8000/docs)** 即可看到自動生成的 API 文件。您可以在此網頁上直接發送 Request 測試：
- **`GET /api/recommendations`**: (需要傳入 Headers `X-User-ID`) 觀察如何透過 JSONB 搭配 Market Data 產生排序結果。
- **`POST /api/portfolio/transactions`**: 測試發送 BUY/SELL 指令，您可以隨後去資料庫觀察 `Portfolio_Summary` 內的 `total_shares` 與 `average_cost` 是否同步發生變化。

### 2. Admin 模擬身分實測
- 在 Header 帶入真正的 Admin `X-User-ID`，以及欲模擬目標客戶的 `X-Impersonate-ID`。
- 如果這時候使用 POST 戳了 `transactions` API 來建立一筆交易，可以觀察資料庫中的 `Audit_Logs` 表是否會多出一筆操作由 Admin 發起但目標為該客戶的稽核紀錄。

### 3. 前端開發參考
本實作僅提供後端核心架構，針對 React / Vue 3 等前端應用串接之技術建言（狀態管裡與 API Client Interceptor）已於此目錄之 `frontend_architecture_guide.md` 提供完整範例。

---

## 📄 授權協議 (License)
依據專案所建立的條款，請閱根目錄 `LICENSE`。
