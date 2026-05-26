-- MOMENTUM IQ Stock Dashboard - Institutional Analytics Database Schema
-- Compatible with both SQLite (local development) and PostgreSQL (production)

-- 1. Watchlist Table
CREATE TABLE IF NOT EXISTS watchlist (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL UNIQUE,
    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 2. Alert Logs Table
CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    alert_type TEXT NOT NULL, -- "CPR_BREAKOUT", "GANN_BREAKOUT", "VWAP_CROSSOVER", "VOLUME_SPIKE", "SMART_MONEY", "BREAKOUT_FAILED"
    trigger_price REAL NOT NULL,
    message TEXT NOT NULL,
    triggered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 3. Scanner Signals Table (Legacy State Compatibility)
CREATE TABLE IF NOT EXISTS scanner_signals (
    symbol TEXT PRIMARY KEY,
    timeframe TEXT NOT NULL,
    signal TEXT NOT NULL, -- "BUY", "SELL", "HOLD"
    confidence REAL NOT NULL,
    relative_volume REAL NOT NULL,
    cpr_width TEXT NOT NULL,
    cpr_position TEXT NOT NULL,
    smart_money_state TEXT NOT NULL,
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 4. Signal History Table (For Performance Auditing)
CREATE TABLE IF NOT EXISTS signal_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    signal TEXT NOT NULL,
    confidence REAL NOT NULL,
    pnl REAL DEFAULT 0.0,
    is_closed INTEGER DEFAULT 0, -- Boolean: 0 = Open, 1 = Closed
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 5. Market Snapshots Table (OHLCV Cache)
CREATE TABLE IF NOT EXISTS market_snapshots (
    symbol TEXT PRIMARY KEY,
    price REAL NOT NULL,
    open REAL NOT NULL,
    high REAL NOT NULL,
    low REAL NOT NULL,
    close REAL NOT NULL,
    volume REAL NOT NULL,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 6. Active Sectors and Live Rotational Metrics
CREATE TABLE IF NOT EXISTS sectors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    theme_category TEXT NOT NULL, -- 'AI', 'Semiconductor', 'Data Centers', etc.
    composite_score REAL DEFAULT 0.00,
    rsi_weekly REAL DEFAULT 0.00,
    rsi_monthly REAL DEFAULT 0.00,
    fii_flow_score REAL DEFAULT 0.00,
    breakout_count_30d INTEGER DEFAULT 0,
    is_active INTEGER DEFAULT 0, -- 0 = False, 1 = True
    active_since TIMESTAMP,
    reason_tags TEXT, -- JSON string or comma-separated tags
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 7. Security Master (US & India)
CREATE TABLE IF NOT EXISTS instruments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker TEXT UNIQUE NOT NULL, -- e.g. 'TATAELXSI.NS', 'NVDA'
    name TEXT NOT NULL,
    market TEXT NOT NULL, -- 'IN' or 'US'
    sector_id INTEGER,
    market_cap_cr REAL NOT NULL,
    avg_daily_volume_20d INTEGER NOT NULL,
    avg_daily_turnover_cr REAL NOT NULL,
    governance_flag INTEGER DEFAULT 0, -- 0 = OK, 1 = Governance issue
    promoter_holding_pct REAL,
    debt_to_equity REAL,
    roe_pct REAL,
    roce_pct REAL,
    sales_cagr_3y REAL,
    profit_cagr_3y REAL,
    operating_cash_flow_positive INTEGER DEFAULT 1, -- 0 = False, 1 = True
    is_quality_passed INTEGER DEFAULT 0, -- 0 = False, 1 = True
    avoid_until TIMESTAMP,
    avoid_reason TEXT,
    next_earnings_date DATE,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 8. Live Technical and Score Buffers (MOMENTUM IQ Core)
CREATE TABLE IF NOT EXISTS stock_intelligence_buffer (
    ticker TEXT PRIMARY KEY,
    price_live REAL NOT NULL,
    prev_close REAL NOT NULL,
    change_pct REAL NOT NULL,
    master_score INTEGER NOT NULL,
    ai_confidence_score INTEGER NOT NULL,
    signal_status TEXT NOT NULL, -- 'STRONG BUY', 'MOMENTUM BUY', 'WATCHLIST', 'AVOID'
    stop_loss REAL,
    target_price REAL,
    risk_reward_ratio REAL,
    suggested_position_size_pct REAL,
    compression_ratio REAL,
    rsi_daily REAL,
    rsi_weekly REAL,
    rsi_monthly REAL,
    extension_pct_50d REAL,
    mtf_alignment_status TEXT, -- 'ELITE SETUP', 'GOOD SETUP', 'WATCHLIST'
    story_score INTEGER DEFAULT 0,
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 9. Story & Narrative Sentiment Master
CREATE TABLE IF NOT EXISTS narratives (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    theme_name TEXT UNIQUE NOT NULL,
    narrative_score INTEGER NOT NULL,
    policy_tailwind_score INTEGER DEFAULT 50,
    macro_alignment_score INTEGER DEFAULT 50,
    sentiment_score_30d INTEGER DEFAULT 50,
    status TEXT DEFAULT 'ACTIVE', -- 'STRONG', 'FADING', 'DEAD'
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 10. Historical Signal Auditing Logs (Golden Rule tracking)
CREATE TABLE IF NOT EXISTS signal_audit_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker TEXT NOT NULL,
    signal_type TEXT NOT NULL, -- 'FRESH BREAKOUT', 'CONFIRMED', 'FAILED'
    trigger_price REAL NOT NULL,
    stop_loss REAL,
    master_score INTEGER NOT NULL,
    regime_state TEXT NOT NULL,
    action_taken TEXT NOT NULL, -- 'ENTRY', 'EXIT', 'AUTO-LIQUIDATE'
    logged_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
