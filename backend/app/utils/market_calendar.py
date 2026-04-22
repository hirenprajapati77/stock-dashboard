
from datetime import datetime, time as dt_time
import pytz
from typing import List, Dict, Optional

class MarketCalendar:
    TZ = pytz.timezone('Asia/Kolkata')
    
    # Session Definitions (IST)
    SESSIONS = {
        "EQUITY": [
            (dt_time(9, 15), dt_time(15, 30))
        ],
        "COMMODITY": [
            (dt_time(9, 0), dt_time(17, 0)),
            (dt_time(17, 0), dt_time(23, 30))
        ]
    }
    
    # Placeholder for 2026 Holidays (Common major ones)
    # In a production app, this would be fetched from Fyers or a DB
    HOLIDAYS_2026 = {
        "2026-01-26", # Republic Day
        "2026-03-04", # Holi
        "2026-04-02", # Good Friday
        "2026-05-01", # Maharashtra Day
        "2026-08-15", # Independence Day
        "2026-10-02", # Gandhi Jayanti
        "2026-10-21", # Dussehra
        "2026-11-10", # Diwali
        "2026-12-25"  # Christmas
    }

    @classmethod
    def get_ist_now(cls) -> datetime:
        return datetime.now(cls.TZ)

    @classmethod
    def is_holiday(cls) -> bool:
        now = cls.get_ist_now()
        # Weekend check (Saturday=5, Sunday=6)
        if now.weekday() >= 5:
            return True
        
        # Holiday check
        date_str = now.strftime("%Y-%m-%d")
        return date_str in cls.HOLIDAYS_2026

    @classmethod
    def get_segment(cls, symbol: str) -> str:
        """Detects segment from Fyers symbol format."""
        symbol = symbol.upper()
        if symbol.startswith("MCX:"):
            return "COMMODITY"
        if symbol.startswith("NSE:"):
            return "EQUITY"
        return "EQUITY" # Default fallback

    @classmethod
    def is_market_open(cls, symbols: Optional[List[str]] = None) -> bool:
        """
        Checks if any of the markets for the given symbols are open.
        If no symbols provided, checks both Equity and Commodity sessions.
        """
        if cls.is_holiday():
            return False
            
        now = cls.get_ist_now().time()
        
        segments = set()
        if symbols:
            for s in symbols:
                segments.add(cls.get_segment(s))
        else:
            segments = {"EQUITY", "COMMODITY"}
            
        for seg in segments:
            sessions = cls.SESSIONS.get(seg, [])
            for start, end in sessions:
                if start <= now <= end:
                    return True
        return False

    @classmethod
    def get_market_status(cls, symbols: Optional[List[str]] = None) -> str:
        """Returns a string status for health monitoring."""
        if cls.is_market_open(symbols):
            return "open"
        return "closed"
