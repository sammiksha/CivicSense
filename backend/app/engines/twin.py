"""Historical Twin: compare current market conditions against historical rolling windows.
Pure deterministic similarity score — no LLM, no prediction.
"""
from __future__ import annotations
import numpy as np
import pandas as pd
from .historical import TRADING_DAYS_PER_MONTH
from .payoff import value_fraction, barrier_breached
from ..schemas import ProductSpec

DISCLAIMER = "Historical comparison only, not a forecast. Past conditions do not predict future outcomes."


def _recent_stats(prices: pd.Series, lookback_days: int = 63) -> dict:
    """3-month trailing stats from the last available price."""
    tail = prices.iloc[-lookback_days:] if len(prices) >= lookback_days else prices
    ret = float(tail.iloc[-1] / tail.iloc[0] - 1) * 100
    log_rets = np.diff(np.log(tail.to_numpy()))
    vol = float(np.std(log_rets) * np.sqrt(252) * 100)
    rolling_max = tail.cummax()
    drawdown = float(((tail - rolling_max) / rolling_max).min() * 100)
    return {"return_pct": round(ret, 2), "vol_pct": round(vol, 2), "drawdown_pct": round(drawdown, 2)}


def find_twin(p: ProductSpec, prices: pd.Series) -> dict:
    """Find the historical rolling window most similar to current market conditions."""
    w = p.tenor_months * TRADING_DAYS_PER_MONTH
    arr = prices.to_numpy(dtype=float)
    if len(arr) < w + 1 + 63:
        return {"error": "Not enough history to compute historical twin."}

    current = _recent_stats(prices)

    # Compute stats for every window
    from numpy.lib.stride_tricks import sliding_window_view
    wins = sliding_window_view(arr, w + 1)
    idx = prices.index

    records = []
    for i in range(len(wins) - 63):  # leave last 63 days as "current"
        win = wins[i]
        start_price = win[0]
        tail_w = arr[i: i + 63]  # 3m context before the window
        if len(tail_w) < 10:
            continue
        ret = float(tail_w[-1] / tail_w[0] - 1) * 100
        log_r = np.diff(np.log(tail_w))
        vol = float(np.std(log_r) * np.sqrt(252) * 100)
        rm = np.maximum.accumulate(tail_w)
        dd = float(((tail_w - rm) / rm).min() * 100)

        # Euclidean distance (normalized)
        dr = (ret - current["return_pct"]) / 20.0
        dv = (vol - current["vol_pct"]) / 10.0
        dd2 = (dd - current["drawdown_pct"]) / 10.0
        dist = float(np.sqrt(dr ** 2 + dv ** 2 + dd2 ** 2))

        # Product outcome for this window
        final_ret = float(win[-1] / win[0] - 1)
        min_ret = float(min(win / win[0] - 1))
        vf = float(value_fraction(p, final_ret, min(min_ret, 0.0)))
        pnl_pct = round((vf - 1) * 100, 2)
        breached = bool(barrier_breached(p, min(min_ret, 0.0))) if p.product_type == "ELN" else False
        payout_inr = round(p.notional * vf)

        records.append({
            "i": i,
            "start_date": str(idx[i].date()),
            "end_date": str(idx[min(i + w, len(idx) - 1)].date()),
            "context_return_pct": round(ret, 2),
            "context_vol_pct": round(vol, 2),
            "context_drawdown_pct": round(dd, 2),
            "underlying_return_pct": round(final_ret * 100, 2),
            "min_return_pct": round(min_ret * 100, 2),
            "dist": dist,
            "product_pnl_pct": pnl_pct,
            "product_loss_pct": round(max(0, -pnl_pct), 2),
            "barrier_breached": breached,
            "final_payout_inr": payout_inr,
            "status": "BARRIER BREACHED" if breached else ("CAPITAL PRESERVED" if vf >= 1.0 else "CAPITAL ERODED"),
            "summary": (
                f"Underlying moved {final_ret * 100:+.1f}% across this window. "
                f"{'Downside safety barrier was breached, exposing principal to market loss.' if breached else 'Safety barrier held safely throughout: 100% principal was protected and full coupon paid.'}"
            )
        })

    if not records:
        return {"error": "Could not compute twin."}

    records.sort(key=lambda x: x["dist"])
    best = records[0]

    return {
        "current_market": current,
        "twin": {
            "period": f"{best['start_date']} to {best['end_date']}",
            "start_date": best["start_date"],
            "end_date": best["end_date"],
            "similarity_score": round(1.0 / (1.0 + best["dist"]), 3),
            "distance": round(best["dist"], 3),
            "context_return_pct": best["context_return_pct"],
            "context_vol_pct": best["context_vol_pct"],
            "context_drawdown_pct": best["context_drawdown_pct"],
            "underlying_return_pct": best["underlying_return_pct"],
            "min_return_pct": best["min_return_pct"],
            "product_pnl_pct": best["product_pnl_pct"],
            "product_loss_pct": best["product_loss_pct"],
            "barrier_breached": best["barrier_breached"],
            "product_loss_inr": round(p.notional * best["product_loss_pct"] / 100),
            "final_payout_inr": best["final_payout_inr"],
            "status": best["status"],
            "summary": best["summary"],
        },
        "top3": [
            {
                "period": f"{r['start_date']} to {r['end_date']}",
                "similarity_score": round(1.0 / (1.0 + r["dist"]), 3),
                "underlying_return_pct": r["underlying_return_pct"],
                "product_pnl_pct": r["product_pnl_pct"],
                "final_payout_inr": r["final_payout_inr"],
                "barrier_breached": r["barrier_breached"],
            }
            for r in records[:3]
        ],
        "disclaimer": DISCLAIMER,
    }
