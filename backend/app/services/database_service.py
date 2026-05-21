import os
import sqlite3
import traceback
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional

class DatabaseService:
    _connection_type: str = "SQLITE"
    _sqlite_path: str = str(Path(__file__).resolve().parent.parent / "data" / "stock_dashboard.db")
    _pg_conn_str: Optional[str] = None
    
    @classmethod
    def initialize(cls):
        """Initializes the database. Loads the schema and creates tables."""
        # Ensure data directory exists for SQLite
        os.makedirs(os.path.dirname(cls._sqlite_path), exist_ok=True)
        
        # Check environment for PostgreSQL
        cls._pg_conn_str = os.getenv("DATABASE_URL") or os.getenv("POSTGRES_URL")
        if cls._pg_conn_str:
            try:
                import psycopg2
                # Verify PG connection
                conn = psycopg2.connect(cls._pg_conn_str)
                conn.close()
                cls._connection_type = "POSTGRES"
                print(f"[Database] Production PostgreSQL detected and connected.", flush=True)
            except Exception as e:
                print(f"[Database] PG connection failed ({e}). Falling back to local SQLite.", flush=True)
                cls._connection_type = "SQLITE"
        else:
            cls._connection_type = "SQLITE"
            print(f"[Database] No production PG url configured. Using local SQLite at: {cls._sqlite_path}", flush=True)
            
        cls._run_schema_initialization()

    @classmethod
    def _run_schema_initialization(cls):
        """Reads schema.sql and runs schema commands to ensure tables exist."""
        try:
            curr_dir = Path(__file__).resolve().parent
            schema_path = curr_dir.parent.parent / "schema.sql"
            if not schema_path.exists():
                print(f"[Database] Warning: schema.sql not found at {schema_path}. Skipping table auto-creation.", flush=True)
                return
                
            with open(schema_path, "r", encoding="utf-8") as f:
                schema_sql = f.read()
                
            # If using PostgreSQL, SQLite's 'AUTOINCREMENT' needs to be replaced with 'SERIAL'
            if cls._connection_type == "POSTGRES":
                schema_sql = schema_sql.replace("AUTOINCREMENT", "")
                schema_sql = schema_sql.replace("INTEGER PRIMARY KEY", "SERIAL PRIMARY KEY")
                
            conn = cls.get_connection()
            cursor = conn.cursor()
            
            # Execute schema statements
            if cls._connection_type == "SQLITE":
                cursor.executescript(schema_sql)
            else:
                cursor.execute(schema_sql)
                
            conn.commit()
            cursor.close()
            conn.close()
            print("[Database] Schema initialization successful.", flush=True)
        except Exception as e:
            print(f"[Database] Error during schema initialization: {e}", flush=True)
            traceback.print_exc()

    @classmethod
    def get_connection(cls):
        """Returns an active database connection."""
        if cls._connection_type == "POSTGRES":
            import psycopg2
            return psycopg2.connect(cls._pg_conn_str)
        else:
            conn = sqlite3.connect(cls._sqlite_path)
            conn.row_factory = sqlite3.Row
            return conn

    # --- Watchlist Methods ---
    @classmethod
    def get_watchlist(cls) -> List[str]:
        """Returns the list of all symbols in the watchlist."""
        try:
            conn = cls.get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT symbol FROM watchlist ORDER BY added_at DESC")
            rows = cursor.fetchall()
            cursor.close()
            conn.close()
            return [row[0] if isinstance(row, tuple) else row["symbol"] for row in rows]
        except Exception as e:
            print(f"[Database] get_watchlist error: {e}", flush=True)
            # Default fallback watchlist matching constituent leaders
            return ["RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK", "SBIN"]

    @classmethod
    def add_to_watchlist(cls, symbol: str) -> bool:
        """Adds a symbol to the watchlist."""
        try:
            conn = cls.get_connection()
            cursor = conn.cursor()
            cursor.execute(
                "INSERT OR IGNORE INTO watchlist (symbol) VALUES (?)" if cls._connection_type == "SQLITE"
                else "INSERT INTO watchlist (symbol) VALUES (%s) ON CONFLICT (symbol) DO NOTHING",
                (symbol.upper(),)
            )
            conn.commit()
            cursor.close()
            conn.close()
            return True
        except Exception as e:
            print(f"[Database] add_to_watchlist error: {e}", flush=True)
            return False

    @classmethod
    def remove_from_watchlist(cls, symbol: str) -> bool:
        """Removes a symbol from the watchlist."""
        try:
            conn = cls.get_connection()
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM watchlist WHERE symbol = ?" if cls._connection_type == "SQLITE"
                else "DELETE FROM watchlist WHERE symbol = %s",
                (symbol.upper(),)
            )
            conn.commit()
            cursor.close()
            conn.close()
            return True
        except Exception as e:
            print(f"[Database] remove_from_watchlist error: {e}", flush=True)
            return False

    # --- Alerts Methods ---
    @classmethod
    def log_alert(cls, symbol: str, alert_type: str, price: float, message: str):
        """Saves a triggered alert to the database."""
        try:
            conn = cls.get_connection()
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO alerts (symbol, alert_type, trigger_price, message) VALUES (?, ?, ?, ?)"
                if cls._connection_type == "SQLITE"
                else "INSERT INTO alerts (symbol, alert_type, trigger_price, message) VALUES (%s, %s, %s, %s)",
                (symbol.upper(), alert_type, price, message)
            )
            conn.commit()
            cursor.close()
            conn.close()
        except Exception as e:
            print(f"[Database] log_alert error: {e}", flush=True)

    @classmethod
    def get_recent_alerts(cls, limit: int = 20) -> List[Dict[str, Any]]:
        """Returns the recent active alerts."""
        try:
            conn = cls.get_connection()
            cursor = conn.cursor()
            cursor.execute(
                f"SELECT symbol, alert_type, trigger_price, message, triggered_at FROM alerts ORDER BY triggered_at DESC LIMIT {limit}"
            )
            rows = cursor.fetchall()
            cursor.close()
            conn.close()
            
            results = []
            for r in rows:
                results.append({
                    "symbol": r[0] if cls._connection_type == "POSTGRES" else r["symbol"],
                    "alert_type": r[1] if cls._connection_type == "POSTGRES" else r["alert_type"],
                    "price": r[2] if cls._connection_type == "POSTGRES" else r["trigger_price"],
                    "message": r[3] if cls._connection_type == "POSTGRES" else r["message"],
                    "timestamp": r[4] if cls._connection_type == "POSTGRES" else r["triggered_at"]
                })
            return results
        except Exception as e:
            print(f"[Database] get_recent_alerts error: {e}", flush=True)
            return []

    # --- Scanner & Signal State Caching ---
    @classmethod
    def save_scanner_signal(cls, symbol: str, timeframe: str, signal: str, confidence: float, rvol: float, cpr_width: str, cpr_position: str, smart_money: str):
        """Caches the latest generated signal for a stock."""
        try:
            conn = cls.get_connection()
            cursor = conn.cursor()
            query = """
                INSERT OR REPLACE INTO scanner_signals (symbol, timeframe, signal, confidence, relative_volume, cpr_width, cpr_position, smart_money_state, last_updated)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """ if cls._connection_type == "SQLITE" else """
                INSERT INTO scanner_signals (symbol, timeframe, signal, confidence, relative_volume, cpr_width, cpr_position, smart_money_state, last_updated)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (symbol) DO UPDATE SET
                    timeframe = EXCLUDED.timeframe,
                    signal = EXCLUDED.signal,
                    confidence = EXCLUDED.confidence,
                    relative_volume = EXCLUDED.relative_volume,
                    cpr_width = EXCLUDED.cpr_width,
                    cpr_position = EXCLUDED.cpr_position,
                    smart_money_state = EXCLUDED.smart_money_state,
                    last_updated = EXCLUDED.last_updated
            """
            cursor.execute(query, (
                symbol.upper(), timeframe, signal, confidence, rvol, cpr_width, cpr_position, smart_money, datetime.now().isoformat()
            ))
            conn.commit()
            cursor.close()
            conn.close()
        except Exception as e:
            print(f"[Database] save_scanner_signal error: {e}", flush=True)

    @classmethod
    def get_scanner_signals(cls) -> List[Dict[str, Any]]:
        """Returns all cached scanner signals."""
        try:
            conn = cls.get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM scanner_signals")
            rows = cursor.fetchall()
            cursor.close()
            conn.close()
            
            results = []
            for r in rows:
                if cls._connection_type == "POSTGRES":
                    results.append({
                        "symbol": r[0], "timeframe": r[1], "signal": r[2], "confidence": r[3],
                        "rvol": r[4], "cpr_width": r[5], "cpr_position": r[6], "smart_money": r[7], "last_updated": r[8]
                    })
                else:
                    results.append({
                        "symbol": r["symbol"], "timeframe": r["timeframe"], "signal": r["signal"], "confidence": r["confidence"],
                        "rvol": r["relative_volume"], "cpr_width": r["cpr_width"], "cpr_position": r["cpr_position"],
                        "smart_money": r["smart_money_state"], "last_updated": r["last_updated"]
                    })
            return results
        except Exception as e:
            print(f"[Database] get_scanner_signals error: {e}", flush=True)
            return []
