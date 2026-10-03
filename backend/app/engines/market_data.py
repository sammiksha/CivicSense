from __future__ import annotations
from functools import lru_cache
import pandas as pd
from .. import config
from ..schemas import UNDERLYINGS


def _load(path) -> pd.Series:
    df = pd.read_csv(path, parse_dates=["Date"])
    return df.set_index("Date")["Close"].dropna().sort_index()


@lru_cache(maxsize=8)
def get_prices(underlying: str) -> tuple[pd.Series, str]:
    """Returns (prices, source). source in {cached_real, yfinance, synthetic_fallback}."""
    name = UNDERLYINGS[underlying]
    real = config.MARKET_DIR / f"{name}.csv"
    if real.exists():
        return _load(real), "cached_real"
    if config.LIVE_DATA:
        try:
            import yfinance as yf
            sym = {"NIFTY50": "^NSEI", "USDINR": "USDINR=X"}[name]
            s = yf.download(sym, start="2007-09-01", progress=False, auto_adjust=True)["Close"].squeeze().dropna()
            s.rename("Close").rename_axis("Date").to_csv(real)
            return s.sort_index(), "yfinance"
        except Exception:
            pass
    return _load(config.MARKET_DIR / f"{name}_fallback.csv"), "synthetic_fallback"
