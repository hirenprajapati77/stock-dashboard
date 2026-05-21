-- S&R Pro Stock Dashboard - Quantitative Analytics Database Schema
-- Compatible with both PostgreSQL and SQLite (fallback)

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
    alert_type TEXT NOT NULL, -- "CPR_BREAKOUT", "GANN_BREAKOUT", "VWAP_CROSSOVER", "VOLUME_SPIKE", "SMART_MONEY"
    trigger_price REAL NOT NULL,
    message TEXT NOT NULL,
    triggered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 3. Scanner Signals Table (Latest State)
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
