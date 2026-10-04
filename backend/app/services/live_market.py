from __future__ import annotations
import time
import pandas as pd
from datetime import datetime, timezone
from pathlib import Path
from .. import config

_CACHE = {
    "timestamp": 0.0,
    "data": None
}
CACHE_TTL_SECONDS = 45.0

FALLBACK_QUOTES = [
    {
        "id": "nifty50",
        "name": "NIFTY 50",
        "symbol": "^NSEI",
        "category": "Indian Equities",
        "price": 22421.95,
        "display_price": "22,421.95",
        "change": -198.50,
        "change_pct": -0.88,
        "trend": "down",
        "badge": "-0.88%",
        "currency": "INR",
        "spark_trend": "down",
        "sub_text": "National Stock Exchange"
    },
    {
        "id": "sensex",
        "name": "SENSEX",
        "symbol": "^BSESN",
        "category": "Indian Equities",
        "price": 71909.70,
        "display_price": "71,909.70",
        "change": -570.59,
        "change_pct": -0.79,
        "trend": "down",
        "badge": "-0.79%",
        "currency": "INR",
        "spark_trend": "down",
        "sub_text": "Bombay Stock Exchange"
    },
    {
        "id": "gold",
        "name": "Gold (24K / 10g)",
        "symbol": "GC=F",
        "category": "Commodities",
        "price": 4162.30,
        "display_price": "₹92,850",
        "change": -43.20,
        "change_pct": -1.03,
        "trend": "down",
        "badge": "-1.03%",
        "currency": "INR",
        "spark_trend": "down",
        "sub_text": "$4,162.30 / oz spot"
    },
    {
        "id": "usdinr",
        "name": "USD/INR",
        "symbol": "USDINR=X",
        "category": "Forex",
        "price": 96.30,
        "display_price": "₹96.30",
        "change": -0.01,
        "change_pct": -0.01,
        "trend": "down",
        "badge": "-0.01%",
        "currency": "INR",
        "spark_trend": "down",
        "sub_text": "RBI Reference Rate"
    },
    {
        "id": "sp500",
        "name": "S&P 500",
        "symbol": "^GSPC",
        "category": "Global Equities",
        "price": 7722.72,
        "display_price": "7,722.72",
        "change": 56.27,
        "change_pct": 0.73,
        "trend": "up",
        "badge": "+0.73%",
        "currency": "USD",
        "spark_trend": "up",
        "sub_text": "US Large Cap Index"
    },
    {
        "id": "nasdaq",
        "name": "NASDAQ",
        "symbol": "^IXIC",
        "category": "Global Equities",
        "price": 27190.86,
        "display_price": "27,190.86",
        "change": 319.26,
        "change_pct": 1.19,
        "trend": "up",
        "badge": "+1.19%",
        "currency": "USD",
        "spark_trend": "up",
        "sub_text": "Tech Composite Index"
    }
]


def _read_latest_csv_price(csv_name: str) -> tuple[float | None, float | None]:
    """Read last and second last close from market CSV."""
    p = config.MARKET_DIR / f"{csv_name}.csv"
    if not p.exists():
        return None, None
    try:
        df = pd.read_csv(p, parse_dates=["Date"]).dropna(subset=["Close"]).sort_values("Date")
        if len(df) >= 2:
            return float(df["Close"].iloc[-1]), float(df["Close"].iloc[-2])
        elif len(df) == 1:
            return float(df["Close"].iloc[-1]), float(df["Close"].iloc[-1])
    except Exception:
        pass
    return None, None


def get_live_market_quotes(force_refresh: bool = False) -> dict:
    now = time.time()
    if not force_refresh and _CACHE["data"] and (now - _CACHE["timestamp"] < CACHE_TTL_SECONDS):
        return _CACHE["data"]

    # Try live fetch via yfinance
    quotes = []
    source = "live_yfinance"
    try:
        import yfinance as yf
        raw_symbols = {
            "nifty50": ("^NSEI", "NIFTY 50", "Indian Equities", "INR", "National Stock Exchange"),
            "sensex": ("^BSESN", "SENSEX", "Indian Equities", "INR", "Bombay Stock Exchange"),
            "gold": ("GC=F", "Gold (24K / 10g)", "Commodities", "INR", "MCX Spot / International"),
            "usdinr": ("USDINR=X", "USD/INR", "Forex", "INR", "RBI Reference Rate"),
            "sp500": ("^GSPC", "S&P 500", "Global Equities", "USD", "US Large Cap Index"),
            "nasdaq": ("^IXIC", "NASDAQ", "Global Equities", "USD", "Tech Composite Index")
        }

        # First obtain USDINR for Gold calculation
        usdinr_price = 96.30
        try:
            usdinr_fi = yf.Ticker("USDINR=X").fast_info
            u_last = getattr(usdinr_fi, "last_price", None)
            if u_last and u_last > 0:
                usdinr_price = float(u_last)
        except Exception:
            pass

        for q_id, (sym, name, cat, cur, sub_lbl) in raw_symbols.items():
            t = yf.Ticker(sym)
            fi = t.fast_info
            last = getattr(fi, "last_price", None)
            prev = getattr(fi, "previous_close", None)
            
            # If fast_info didn't populate, fall back to historical CSV
            if last is None or last <= 0:
                csv_map = {"nifty50": "NIFTY50", "usdinr": "USDINR", "gold": "GOLD"}
                c_last, c_prev = _read_latest_csv_price(csv_map.get(q_id, ""))
                if c_last:
                    last, prev = c_last, c_prev

            # If still None, take from fallback defaults
            if last is None or last <= 0:
                fb = next((f for f in FALLBACK_QUOTES if f["id"] == q_id), None)
                last = fb["price"] if fb else 100.0
                prev = last - (fb["change"] if fb else 0.0)

            last = float(last)
            prev = float(prev) if (prev and prev > 0) else last
            chg = last - prev
            pct = (chg / prev * 100.0) if prev else 0.0

            sub_text = sub_lbl
            if q_id == "gold":
                # Convert international oz price to 10g 24K INR (with typical 15% duty/tax)
                inr_10g = round((last * usdinr_price / 31.1034768 * 10.0) * 1.15, -1)
                display_price = f"₹{inr_10g:,.0f}"
                sub_text = f"${last:,.2f} / oz"
            elif q_id == "usdinr":
                display_price = f"₹{last:.2f}"
            elif cur == "INR":
                display_price = f"{last:,.2f}"
            else:
                display_price = f"{last:,.2f}"

            trend = "up" if chg >= 0 else "down"
            badge = f"{'+' if chg >= 0 else ''}{pct:.2f}%"

            quotes.append({
                "id": q_id,
                "name": name,
                "symbol": sym,
                "category": cat,
                "price": round(last, 2),
                "display_price": display_price,
                "change": round(chg, 2),
                "change_pct": round(pct, 2),
                "trend": trend,
                "badge": badge,
                "currency": cur,
                "spark_trend": trend,
                "sub_text": sub_text
            })

    except Exception:
        quotes = FALLBACK_QUOTES
        source = "cached_fallback"

    res = {
        "status": "ok",
        "as_of": datetime.now(timezone.utc).isoformat(),
        "source": source,
        "quotes": quotes
    }
    _CACHE["timestamp"] = now
    _CACHE["data"] = res
    return res
