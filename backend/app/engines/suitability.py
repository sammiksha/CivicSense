"""Rule engine: deterministic, reason-coded decisions.  The LLM never decides suitability."""
from __future__ import annotations
from .payoff import loss_at_shock
from ..schemas import ProductSpec, CustomerProfile

RANK = {"SUITABLE": 0, "REVIEW": 1, "MISMATCH": 2}
NAME = {v: k for k, v in RANK.items()}
LEVEL = {"conservative": 1, "moderate": 2, "aggressive": 3}
LEVEL_NAME = {1: "low", 2: "medium", 3: "high"}


def product_risk_level(p: ProductSpec) -> int:
    if p.product_type == "CPN":
        return 1 if p.protection_pct >= 100 else 2
    if p.product_type == "DCD":
        return 2
    b = p.barrier_pct or 100
    return 3 if b > 60 else (2 if b > 50 else 1)   # deep-buffer ELN (barrier <= 50%) counts as low


def loss_status(loss: float, tol: float, mult: float) -> str:
    if loss <= tol:
        return "SUITABLE"
    return "REVIEW" if loss <= tol * mult else "MISMATCH"


def _g(x: float) -> str:
    return f"{x:g}"


def evaluate(p: ProductSpec, c: CustomerProfile, tail_loss_pct: float, rules: dict) -> list[dict]:
    out = []
    # R1 risk appetite
    pl, cl = product_risk_level(p), LEVEL[c.risk_appetite]
    gap = pl - cl
    st = "SUITABLE" if gap <= 0 else ("REVIEW" if gap == 1 else "MISMATCH")
    out.append({"rule_id": "R1_RISK_APPETITE", "name": "Risk appetite", "status": st,
                "customer_value": c.risk_appetite, "product_value": f"{LEVEL_NAME[pl]} downside risk",
                "message": f"Risk appetite: {c.risk_appetite} vs {LEVEL_NAME[pl]}-risk product"})
    # R2 loss tolerance
    st = loss_status(tail_loss_pct, c.loss_tolerance_pct, rules["loss_tolerance_review_multiple"])
    out.append({"rule_id": "R2_LOSS_TOLERANCE", "name": "Loss tolerance", "status": st,
                "customer_value": f"{_g(c.loss_tolerance_pct)}%", "product_value": f"{_g(tail_loss_pct)}% modeled tail loss",
                "message": f"Loss tolerance: {_g(c.loss_tolerance_pct)}% vs modeled tail loss {_g(tail_loss_pct)}%"})
    # R3 horizon
    st = "SUITABLE" if p.tenor_months <= c.horizon_months else "MISMATCH"
    out.append({"rule_id": "R3_HORIZON", "name": "Investment horizon", "status": st,
                "customer_value": f"{c.horizon_months} months", "product_value": f"{p.tenor_months} months",
                "message": f"Horizon: customer {c.horizon_months} months vs product tenor {p.tenor_months} months"})
    # R4 concentration
    existing = c.existing_exposures.get(p.underlying, 0.0)
    new = p.notional / c.portfolio_value * 100.0
    total = existing + new
    limit = rules["concentration_limit_pct"]
    st = "SUITABLE" if total <= limit else "MISMATCH"
    out.append({"rule_id": "R4_CONCENTRATION", "name": "Concentration", "status": st,
                "customer_value": f"{_g(round(existing, 2))}% existing", "product_value": f"{_g(round(new, 2))}% new",
                "message": f"Concentration: existing {_g(round(existing, 2))}% + new {_g(round(new, 2))}% = "
                           f"{_g(round(total, 2))}% in {p.underlying}, limit {_g(limit)}%"})
    return out


def overall(results: list[dict]) -> str:
    return NAME[max(RANK[r["status"]] for r in results)]


def breaking_point(p: ProductSpec, c: CustomerProfile, rules: dict, max_shock: int = 60) -> dict:
    """Re-run the loss rule under market shocks 0%, -1%, ... -60% and find where it breaks."""
    static = [r for r in evaluate(p, c, 0.0, rules) if r["rule_id"] != "R2_LOSS_TOLERANCE"]
    static_worst = max([RANK[r["status"]] for r in static], default=0)
    ladder, suitable_until, still_ok = [], None, True
    review_from = mismatch_from = None
    for s in range(0, max_shock + 1):
        shock = -float(s)
        loss = loss_at_shock(p, shock)
        st = loss_status(loss, c.loss_tolerance_pct, rules["loss_tolerance_review_multiple"])
        if st == "SUITABLE" and still_ok:
            suitable_until = shock
        else:
            still_ok = False
        if st == "REVIEW" and review_from is None:
            review_from = shock
        if st == "MISMATCH" and mismatch_from is None:
            mismatch_from = shock
        ladder.append({"shock_pct": shock, "loss_pct": round(loss, 2), "loss_rule": st,
                       "overall": NAME[max(RANK[st], static_worst)]})
    return {"suitable_until_pct": suitable_until, "review_from_pct": review_from, "mismatch_from_pct": mismatch_from,
            "blocked_by_other_rules": [r["rule_id"] for r in static if r["status"] != "SUITABLE"],
            "ladder": ladder}
