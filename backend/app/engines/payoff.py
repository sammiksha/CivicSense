"""Deterministic payoff engine for ELN, DCD and CPN.  No LLM is involved here.

value_fraction() returns the maturity value as a fraction of the invested principal
(1.0 = get exactly your money back), coupon/interest included.

Assumptions (shown in the UI):
* ELN: coupon always paid; principal returned unless the barrier was breached AND the
  final level is below the strike, then principal x final/initial.
* DCD: interest always paid; if final < strike (conversion) level the deposit is converted
  at the strike, worth principal x final/strike in home currency.
* CPN: protected% + participation% x max(0, underlying return); coupon is not used.
* Barrier is monitored on the path minimum (continuous). For instantaneous scenario
  tables, path minimum = min(final return, 0).
"""
from __future__ import annotations
import numpy as np
from ..schemas import ProductSpec


def value_fraction(p: ProductSpec, final_ret, min_ret):
    final_ret = np.asarray(final_ret, dtype=float)
    min_ret = np.asarray(min_ret, dtype=float)
    t = p.tenor_months / 12.0
    f = 1.0 + final_ret
    if p.product_type == "ELN":
        coupon = p.coupon_pct / 100.0 * t
        breached = (1.0 + min_ret) < p.barrier_pct / 100.0
        loss_case = breached & (f < p.strike_pct / 100.0)
        return np.where(loss_case, f, 1.0) + coupon
    if p.product_type == "DCD":
        interest = p.coupon_pct / 100.0 * t
        k = p.strike_pct / 100.0
        return np.where(f < k, f / k, 1.0) + interest
    if p.product_type == "CPN":
        return p.protection_pct / 100.0 + p.participation_pct / 100.0 * np.maximum(0.0, final_ret)
    raise ValueError(p.product_type)


def barrier_breached(p: ProductSpec, min_ret):
    if p.product_type != "ELN":
        return np.zeros_like(np.asarray(min_ret, dtype=float), dtype=bool)
    return (1.0 + np.asarray(min_ret, dtype=float)) < p.barrier_pct / 100.0


def loss_at_shock(p: ProductSpec, move_pct: float) -> float:
    """Loss % of principal if the underlying ends at `move_pct` (instantaneous shock)."""
    r = move_pct / 100.0
    v = float(value_fraction(p, r, min(r, 0.0)))
    return max(0.0, (1.0 - v) * 100.0)


def scenario_table(p: ProductSpec, moves=(20, 0, -10, -25, -40)) -> list[dict]:
    rows = []
    for m in moves:
        r = m / 100.0
        v = float(value_fraction(p, r, min(r, 0.0)))
        rows.append({
            "move_pct": float(m),
            "final_value": round(p.notional * v, 2),
            "pnl": round(p.notional * (v - 1), 2),
            "pnl_pct": round((v - 1) * 100, 2),
            "barrier_breached": bool(barrier_breached(p, min(r, 0.0))) if p.product_type == "ELN" else None,
        })
    return rows


def payoff_curve(p: ProductSpec, lo=-60, hi=40, step=1) -> list[dict]:
    xs = np.arange(lo, hi + step, step, dtype=float)
    r = xs / 100.0
    v = value_fraction(p, r, np.minimum(r, 0.0))
    return [{"move_pct": float(x), "return_pct": round(float((y - 1) * 100), 3)} for x, y in zip(xs, v)]
