"""Regime stress and stress ladder engines.
Purely deterministic — no LLM.
"""
from __future__ import annotations
from .payoff import loss_at_shock, value_fraction
from .suitability import loss_status, evaluate, overall
from ..schemas import ProductSpec, CustomerProfile

REGIMES = [
    {"name": "Bull",         "label": "Bull Market",    "min_pct":  15,  "max_pct": 100,  "example_pct":  25},
    {"name": "Normal",       "label": "Normal",          "min_pct":   0,  "max_pct":  15,  "example_pct":   8},
    {"name": "MildStress",   "label": "Mild Stress",     "min_pct": -10,  "max_pct":   0,  "example_pct":  -5},
    {"name": "SevereStress", "label": "Severe Stress",   "min_pct": -20,  "max_pct": -10,  "example_pct": -15},
    {"name": "Crash",        "label": "Crash",           "min_pct": -100, "max_pct": -20,  "example_pct": -35},
]


def regime_stress(p: ProductSpec, c: CustomerProfile, rules: dict) -> list[dict]:
    out = []
    mult = rules["loss_tolerance_review_multiple"]
    for reg in REGIMES:
        shock = float(reg["example_pct"])
        r = shock / 100.0
        v = float(value_fraction(p, r, min(r, 0.0)))
        loss = max(0.0, (1.0 - v) * 100.0)
        pnl_pct = round((v - 1) * 100, 2)
        st = loss_status(loss, c.loss_tolerance_pct, mult)
        from .payoff import barrier_breached
        import numpy as np
        breached = bool(barrier_breached(p, np.array([min(r, 0.0)]))[0]) if p.product_type == "ELN" else False
        out.append({
            "regime": reg["name"],
            "label": reg["label"],
            "range": f"{reg['min_pct']}% to {reg['max_pct']}%",
            "example_shock_pct": shock,
            "pnl_pct": pnl_pct,
            "loss_pct": round(loss, 2),
            "loss_inr": round(p.notional * loss / 100),
            "barrier_breached": breached,
            "suitability": st,
        })
    return out


def stress_ladder(p: ProductSpec, c: CustomerProfile, rules: dict, steps: list[float] | None = None) -> list[dict]:
    if steps is None:
        steps = [0, -5, -10, -15, -20, -25, -30, -35, -40, -45, -50]
    mult = rules["loss_tolerance_review_multiple"]
    # static rules (non-loss)
    static = [r for r in evaluate(p, c, 0.0, rules) if r["rule_id"] != "R2_LOSS_TOLERANCE"]
    static_worst = max(({"SUITABLE": 0, "REVIEW": 1, "MISMATCH": 2}[r["status"]] for r in static), default=0)
    name_map = {0: "SUITABLE", 1: "REVIEW", 2: "MISMATCH"}
    out = []
    for shock in steps:
        loss = loss_at_shock(p, float(shock))
        st = loss_status(loss, c.loss_tolerance_pct, mult)
        rank = {"SUITABLE": 0, "REVIEW": 1, "MISMATCH": 2}
        overall_status = name_map[max(rank[st], static_worst)]
        out.append({
            "shock_pct": float(shock),
            "loss_pct": round(loss, 2),
            "loss_inr": round(p.notional * loss / 100),
            "loss_rule": st,
            "overall": overall_status,
        })
    return out
