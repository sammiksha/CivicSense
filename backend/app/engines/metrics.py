from __future__ import annotations
from .historical import replay
from .montecarlo import simulate
from .. import config
from ..schemas import ProductSpec


def compute_metrics(p: ProductSpec, prices, n_paths: int | None = None) -> dict:
    n = n_paths or config.MC_PATHS
    hist = replay(p, prices)
    mc = simulate(p, prices, n_paths=n, seed=config.MC_SEED)
    tail = max(hist["worst_loss_pct"], mc["p1_loss_pct"])
    return {"historical": hist, "monte_carlo": mc, "tail_loss_pct": round(tail, 2),
            "tail_loss_basis": "max(historical worst-window loss, Monte Carlo 1st-percentile loss)"}
