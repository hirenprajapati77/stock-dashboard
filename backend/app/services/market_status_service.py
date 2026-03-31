import datetime

class MarketStatusService:
    # Basic NSE Holidays for current year (2026/2024/etc - approximate subset)
    # Format: "MM-DD"
    NSE_HOLIDAYS = [
        "01-26", # Republic Day
        "03-08", # Mahashivratri (approx)
        "03-25", # Holi (approx)
        "04-11", # Id-Ul-Fitr (approx)
        "04-17", # Ram Navami (approx)
        "05-01", # Maharashtra Day
        "08-15", # Independence Day
        "10-02", # Gandhi Jayanti
        "11-01", # Diwali (Laxmi Pujan)
        "12-25", # Christmas
    ]

    @classmethod
    def get_current_ist_time(cls):
        ist = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
        return datetime.datetime.now(ist)

    @classmethod
    def is_holiday(cls, dt: datetime.datetime):
        month_day = dt.strftime("%m-%d")
        return month_day in cls.NSE_HOLIDAYS

    @classmethod
    def is_weekend(cls, dt: datetime.datetime):
        # 5 = Saturday, 6 = Sunday
        return dt.weekday() >= 5

    @classmethod
    def get_market_status(cls):
        now = cls.get_current_ist_time()
        
        # 1. Check Weekend or Holiday
        if cls.is_weekend(now) or cls.is_holiday(now):
            return {
                "market_phase": "CLOSED",
                "mode": "CLOSED",
                "is_data_stale": True,
                "message": "Market is closed (Weekend/Holiday)",
                "last_updated": now.isoformat()
            }

        # Market Hours in IST
        # Pre-market: 09:00 - 09:15
        # Open: 09:15 - 15:30
        # Post-market: 15:30 - 16:00
        # Closed: < 09:00 or > 16:00

        current_time_val = now.hour * 100 + now.minute

        if current_time_val < 900:
            return {
                "market_phase": "CLOSED",
                "mode": "CLOSED",
                "is_data_stale": True,
                "message": "Market is currently closed",
                "last_updated": now.isoformat()
            }
        elif 900 <= current_time_val < 915:
            return {
                "market_phase": "PRE_MARKET",
                "mode": "PRE_MARKET",
                "is_data_stale": True,
                "message": "Pre-market session",
                "last_updated": now.isoformat()
            }
        elif 915 <= current_time_val < 1530:
            return {
                "market_phase": "OPEN",
                "mode": "OPEN",
                "is_data_stale": False,
                "message": "Market is open",
                "last_updated": now.isoformat()
            }
        elif 1530 <= current_time_val <= 1600:
            return {
                "market_phase": "POST_MARKET",
                "mode": "POST_MARKET",
                "is_data_stale": False,
                "message": "Post-market session",
                "last_updated": now.isoformat()
            }
        else:
            return {
                "market_phase": "CLOSED",
                "mode": "CLOSED",
                "is_data_stale": True,
                "message": "Market is closed",
                "last_updated": now.isoformat()
            }
