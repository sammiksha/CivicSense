"""Download REAL history with yfinance and cache it (overrides the synthetic fallback)."""
import yfinance as yf
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "data" / "market"
for name, sym in {"NIFTY50": "^NSEI", "USDINR": "USDINR=X"}.items():
    df = yf.download(sym, start="2007-09-01", progress=False, auto_adjust=True)
    close = df["Close"].squeeze().dropna().rename("Close")
    close.rename_axis("Date").to_csv(OUT / f"{name}.csv")
    print(name, len(close), "rows saved")
