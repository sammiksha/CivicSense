from __future__ import annotations
import numpy as np
import pandas as pd
from numpy.lib.stride_tricks import sliding_window_view
from .payoff import value_fraction, barrier_breached
from ..schemas import ProductSpec

TRADING_DAYS_PER_MONTH = 21


def replay(p: ProductSpec, prices: pd.Series) -> dict:
    """Apply the payoff to every rolling window of tenor length in real history."""
    w = p.tenor_months * TRADING_DAYS_PER_MONTH
    arr = prices.to_numpy(dtype=float)
    if len(arr) <= w + 1:
        raise ValueError("not enough history for this tenor")
    win = sliding_window_view(arr, w + 1)
    final = win[:, -1] / win[:, 0] - 1.0
    mn = np.minimum(win.min(axis=1) / win[:, 0] - 1.0, 0.0)
    profit = (value_fraction(p, final, mn) - 1.0) * 100.0
    i_worst, i_best = int(profit.argmin()), int(profit.argmax())
    idx = prices.index
    counts, edges = np.histogram(profit, bins=20)
    return {
        "n_windows": int(len(profit)),
        "window_trading_days": int(w),
        "best_pct": round(float(profit.max()), 2),
        "worst_pct": round(float(profit.min()), 2),
        "avg_pct": round(float(profit.mean()), 2),
        "median_pct": round(float(np.median(profit)), 2),
        "pct_windows_loss": round(float((profit < 0).mean() * 100), 2),
        "pct_windows_barrier_breached": round(float(barrier_breached(p, mn).mean() * 100), 2),
        "worst_window": [str(idx[i_worst].date()), str(idx[i_worst + w].date())],
        "best_window": [str(idx[i_best].date()), str(idx[i_best + w].date())],
        "worst_loss_pct": round(max(0.0, -float(profit.min())), 2),
        "histogram": {"edges": [round(float(e), 2) for e in edges], "counts": [int(c) for c in counts]},
    }
