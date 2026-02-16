from datetime import datetime

import pandas as pd

from app.services.constituent_service import ConstituentService
from app.services.screener_service import ScreenerService
import app.services.screener_service as screener_module


def test_momentum_hits_rows_use_live_quote_and_preserve_hit_context(monkeypatch):
    idx = pd.date_range('2025-01-01', periods=8, freq='D')

    # A qualifying hit occurs at index=5 (>2% and volume shock), while index=7 is latest.
    stock_df = pd.DataFrame(
        {
            'Close': [100, 100.4, 100.8, 101.0, 101.2, 104.0, 104.3, 104.5],
            'Volume': [100, 102, 98, 101, 99, 500, 110, 108],
        },
        index=idx,
    )
    sector_df = pd.DataFrame(
        {
            'Close': [200, 200.5, 201.0, 201.5, 202.0, 202.4, 202.6, 202.8],
            'Volume': [1000] * 8,
        },
        index=idx,
    )

    stock_batch = pd.concat({'ABC.NS': stock_df}, axis=1)
    sector_batch = pd.concat({'^NSEBANK': sector_df}, axis=1)

    monkeypatch.setattr(ConstituentService, 'SECTOR_CONSTITUENTS', {'NIFTY_BANK': ['ABC.NS']})

    calls = {'count': 0}

    def fake_download(*args, **kwargs):
        calls['count'] += 1
        return stock_batch if calls['count'] == 1 else sector_batch

    class FakeTicker:
        def __init__(self, _symbol):
            self.fast_info = {
                'lastPrice': 106.0,
                'previousClose': 104.5,
            }

    monkeypatch.setattr(screener_module.yf, 'download', fake_download)
    monkeypatch.setattr(screener_module.yf, 'Ticker', FakeTicker)

    rows = ScreenerService.get_screener_data('1D')
    assert rows

    row = rows[0]
    expected_live_change = round(((106.0 - 104.5) / 104.5) * 100, 2)
    hit_change = round(float((stock_df['Close'].pct_change() * 100).iloc[5]), 2)

    assert row['price'] == 106.0
    assert row['change'] == expected_live_change
    assert row['hitChange'] == hit_change
    assert row['hitAsOf'].startswith(str(idx[5].date()))
    assert row['asOf'].startswith(datetime.now().strftime('%Y-%m-%d'))
