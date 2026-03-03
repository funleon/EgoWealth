-- init.sql

-- 1. Users 表
CREATE TABLE IF NOT EXISTS Users (
    user_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    username VARCHAR(50) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    role VARCHAR(20) NOT NULL CHECK (role IN ('user', 'admin')),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 2. User_Preferences 表 (使用者設定檔)
CREATE TABLE IF NOT EXISTS User_Preferences (
    user_id UUID PRIMARY KEY REFERENCES Users(user_id) ON DELETE CASCADE,
    weight_map JSONB NOT NULL DEFAULT '{"pe_weight": 1.0, "yield_weight": 1.0, "yoy_weight": 1.0, "roe_weight": 1.0}',
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 3. Stocks 表 (股票主檔)
CREATE TABLE IF NOT EXISTS Stocks (
    ticker VARCHAR(20) PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    industry VARCHAR(50),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 4. Market_Data 表 (市場數據)
CREATE TABLE IF NOT EXISTS Market_Data (
    ticker VARCHAR(20) REFERENCES Stocks(ticker) ON DELETE CASCADE,
    date DATE NOT NULL,
    pe_ratio NUMERIC,
    yield NUMERIC,
    yoy_growth NUMERIC,
    roe NUMERIC,
    ai_tag VARCHAR(50), -- 例如 'Value', 'Growth'
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (ticker, date)
);

-- 5. Portfolio_Transactions 表 (投資組合明細表)
CREATE TABLE IF NOT EXISTS Portfolio_Transactions (
    tx_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES Users(user_id) ON DELETE CASCADE,
    ticker VARCHAR(20) REFERENCES Stocks(ticker) ON DELETE RESTRICT,
    action VARCHAR(10) NOT NULL CHECK (action IN ('BUY', 'SELL')),
    price NUMERIC NOT NULL CHECK (price >= 0),
    quantity NUMERIC NOT NULL CHECK (quantity > 0),
    tx_date TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 6. Portfolio_Summary 表 (投資組合總覽表)
CREATE TABLE IF NOT EXISTS Portfolio_Summary (
    summary_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES Users(user_id) ON DELETE CASCADE,
    ticker VARCHAR(20) REFERENCES Stocks(ticker) ON DELETE RESTRICT,
    total_shares NUMERIC NOT NULL CHECK (total_shares >= 0),
    average_cost NUMERIC NOT NULL CHECK (average_cost >= 0),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (user_id, ticker)
);

-- 7. Audit_Logs 表 (稽核日誌)
CREATE TABLE IF NOT EXISTS Audit_Logs (
    log_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    actor_user_id UUID REFERENCES Users(user_id) ON DELETE SET NULL, -- 紀錄操作者 (Admin)
    target_user_id UUID REFERENCES Users(user_id) ON DELETE CASCADE, -- 被操作的目標使用者
    action_detail TEXT NOT NULL,
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
