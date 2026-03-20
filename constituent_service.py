class ConstituentService:
    """
    Manages string mappings of NIFTY sectors to their top constituents.
    Used for breadth and volume analysis.
    """
    
    SECTOR_CONSTITUENTS = {
        "NIFTY_BANK": ["HDFCBANK.NS", "ICICIBANK.NS", "SBIN.NS", "AXISBANK.NS", "KOTAKBANK.NS", "INDUSINDBK.NS", "BANKBARODA.NS", "PNB.NS", "IDFCFIRSTB.NS", "AUBANK.NS"],
        "NIFTY_IT": ["TCS.NS", "INFY.NS", "HCLTECH.NS", "WIPRO.NS", "TECHM.NS", "LTIM.NS", "PERSISTENT.NS", "COFORGE.NS", "MPHASIS.NS", "LTTS.NS"],
        "NIFTY_FMCG": ["ITC.NS", "HINDUNILVR.NS", "NESTLEIND.NS", "TATACONSUM.NS", "BRITANNIA.NS", "VBL.NS", "GODREJCP.NS", "DABUR.NS", "MARICO.NS", "COLPAL.NS"],
        "NIFTY_AUTO": ["M&M.NS", "TATAMOTORS.NS", "MARUTI.NS", "BAJAJ-AUTO.NS", "EICHERMOT.NS", "TVSMOTOR.NS", "HEROMOTOCO.NS", "BHARATFORG.NS", "ASHOKLEY.NS", "MOTHERSON.NS"],
        "NIFTY_METAL": ["TATASTEEL.NS", "JSWSTEEL.NS", "HINDALCO.NS", "VEDL.NS", "JINDALSTEL.NS", "NMDC.NS", "COALINDIA.NS", "SAIL.NS", "NATIONALUM.NS", "ADANIENT.NS"],
        "NIFTY_PHARMA": ["SUNPHARMA.NS", "DRREDDY.NS", "CIPLA.NS", "DIVISLAB.NS", "LUPIN.NS", "AUROPHARMA.NS", "ALKEM.NS", "TORNTPHARM.NS", "ZYDUSLIFE.NS", "GLENMARK.NS"],
        "NIFTY_ENERGY": ["RELIANCE.NS", "NTPC.NS", "ONGC.NS", "POWERGRID.NS", "BPCL.NS", "IOC.NS", "TATAPOWER.NS", "GAIL.NS", "ADANIGREEN.NS", "ADANIENSOL.NS"],
        "NIFTY_REALTY": ["DLF.NS", "GODREJPROP.NS", "OBEROIRLTY.NS", "PHOENIXLTD.NS", "PRESTIGE.NS", "BRIGADE.NS", "SOBHA.NS", "LODHA.NS", "SWANENERGY.NS", "MAHLIFE.NS"],
        "NIFTY_PSU_BANK": ["SBIN.NS", "BANKBARODA.NS", "PNB.NS", "CANBK.NS", "UNIONBANK.NS", "INDIANB.NS", "BANKINDIA.NS", "IOB.NS", "UCOBANK.NS", "CENTRALBK.NS"],
        "NIFTY_MEDIA": ["SUNTV.NS", "ZEEL.NS", "PVRINOX.NS", "NAZARA.NS", "TV18BRDCST.NS", "HATHWAY.NS", "NETWORK18.NS", "NDTV.NS", "TVTODAY.NS"]
    }

    @classmethod
    def get_constituents(cls, sector_name):
        return cls.SECTOR_CONSTITUENTS.get(sector_name, [])

    @classmethod
    def get_sector_for_ticker(cls, ticker):
        """
        Finds which NIFTY sector a ticker belongs to.
        """
        for sector, constituents in cls.SECTOR_CONSTITUENTS.items():
            if ticker in constituents:
                return sector
        return None
