from __future__ import annotations
import numpy as np
import pandas as pd
from .payoff import value_fraction, barrier_breached
from ..schemas import ProductSpec


def simulate(p: ProductSpec, prices: pd.Series, n_paths: int = 10000, seed: int = 42, drift: float = 0.08) -> dict:
    """Geometric Brownian motion, volatility estimated from history, fixed seed => reproducible."""
    logret = np.diff(np.log(prices.to_numpy(dtype=float)))
    sigma = float(logret.std() * np.sqrt(252))
    steps = max(1, int(round(252 * p.tenor_months / 12)))
    dt = 1.0 / 252
    rng = np.random.default_rng(seed)
    z = rng.standard_normal((n_paths, steps))
    inc = (drift - 0.5 * sigma**2) * dt + sigma * np.sqrt(dt) * z
    paths = np.exp(np.cumsum(inc, axis=1))
    final = paths[:, -1] - 1.0
    mn = np.minimum(paths.min(axis=1) - 1.0, 0.0)
    profit = (value_fraction(p, final, mn) - 1.0) * 100.0
    return {
        "n_paths": n_paths, "seed": seed, "annual_vol_pct": round(sigma * 100, 2), "drift_pct": drift * 100,
        "prob_loss_pct": round(float((profit < 0).mean() * 100), 2),
        "prob_barrier_breach_pct": round(float(barrier_breached(p, mn).mean() * 100), 2),
        "p1_pct": round(float(np.percentile(profit, 1)), 2),
        "p5_pct": round(float(np.percentile(profit, 5)), 2),
        "median_pct": round(float(np.median(profit)), 2),
        "mean_pct": round(float(profit.mean()), 2),
        "p1_loss_pct": round(max(0.0, -float(np.percentile(profit, 1))), 2),
    }
