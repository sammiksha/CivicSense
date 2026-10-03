"""Generate SYNTHETIC fallback price series (clearly labelled in the API as 'synthetic_fallback').
Real data: run scripts/fetch_market_data.py (needs internet + yfinance)."""
import numpy as np, pandas as pd
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "data" / "market"
OUT.mkdir(parents=True, exist_ok=True)


def gbm(start, mu, sigma, seed, crash=False):
    idx = pd.bdate_range("2010-01-01", "2026-09-30")
    rng = np.random.default_rng(seed)
    r = (mu - 0.5 * sigma**2) / 252 + sigma / np.sqrt(252) * rng.standard_normal(len(idx))
    if crash:
        c = (idx >= "2020-02-20") & (idx <= "2020-03-23")
        r[c] = np.log(0.62) / c.sum() + 0.01 * rng.standard_normal(c.sum())
        rb = (idx >= "2020-03-24") & (idx <= "2020-08-31")
        r[rb] += np.log(1.45) / rb.sum()
    return pd.Series(start * np.exp(np.cumsum(r)), index=idx, name="Close")


for name, s in {"NIFTY50": gbm(5000, 0.11, 0.15, 7, True), "USDINR": gbm(45, 0.03, 0.05, 11)}.items():
    s.round(4).rename_axis("Date").to_csv(OUT / f"{name}_fallback.csv")
    print(name, len(s), "rows")
