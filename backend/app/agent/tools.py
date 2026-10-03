"""Tools the copilot agent can call.  Every number the agent reports must come from here."""
from __future__ import annotations
import json
from pathlib import Path
from .. import config
from ..engines import suitability as suit
from ..engines.payoff import value_fraction, barrier_breached
from ..rag.store import get_kb
from ..schemas import ProductSpec, CustomerProfile
from ..services.assessment import assess
from .session import Session

WHAT_IF_KEYS = {"barrier_pct", "tenor_months", "notional", "coupon_pct", "strike_pct", "protection_pct", "participation_pct"}


def load_customers() -> list[CustomerProfile]:
    raw = json.loads((config.DATA_DIR / "samples" / "customers.json").read_text())
    return [CustomerProfile(**c) for c in raw]


def find_customer(cid: str) -> CustomerProfile | None:
    return next((c for c in load_customers() if c.id == cid), None)


def _need(s: Session):
    if s.product is None or s.customer is None:
        raise ValueError("Select a customer and configure a product first.")


def _assessment(s: Session, p: ProductSpec | None = None, full: bool = True) -> dict:
    p = p or s.product
    key = (p.model_dump_json(), s.customer.id, full)
    if key not in s.cache:
        s.cache[key] = assess(p, s.customer, n_paths=None if full else 3000, with_repairs=full)
    return s.cache[key]


def _summary(a: dict) -> dict:
    m, bp = a["metrics"], a["breaking_point"]
    return {"decision": a["decision"], "rules": [{k: r[k] for k in ("rule_id", "status", "message")} for r in a["rules"]],
            "tail_loss_pct": m["tail_loss_pct"],
            "historical": {k: m["historical"][k] for k in ("worst_pct", "best_pct", "avg_pct", "pct_windows_loss", "n_windows")},
            "monte_carlo": {k: m["monte_carlo"][k] for k in ("prob_loss_pct", "prob_barrier_breach_pct", "p5_pct")},
            "breaking_point": {k: bp[k] for k in ("suitable_until_pct", "review_from_pct", "mismatch_from_pct")},
            "data_source": a["data_source"]}


# ---- tool implementations ----
def get_context(s: Session, **_):
    _need(s)
    return {"product": s.product.model_dump(), "customer": s.customer.model_dump()}


def run_assessment(s: Session, **_):
    _need(s)
    return _summary(_assessment(s))


def run_scenario(s: Session, market_move_pct: float, **_):
    _need(s)
    p, c = s.product, s.customer
    r = market_move_pct / 100.0
    v = float(value_fraction(p, r, min(r, 0.0)))
    loss = max(0.0, (1 - v) * 100)
    rules = config.load_rules()
    return {"market_move_pct": market_move_pct, "final_value": round(p.notional * v, 2), "pnl": round(p.notional * (v - 1), 2),
            "pnl_pct": round((v - 1) * 100, 2), "barrier_breached": bool(barrier_breached(p, min(r, 0.0))) if p.product_type == "ELN" else None,
            "customer_loss_tolerance_pct": c.loss_tolerance_pct,
            "loss_rule_status": suit.loss_status(loss, c.loss_tolerance_pct, rules["loss_tolerance_review_multiple"])}


def find_breaking_point(s: Session, **_):
    _need(s)
    bp = _assessment(s)["breaking_point"]
    return {k: bp[k] for k in ("suitable_until_pct", "review_from_pct", "mismatch_from_pct", "blocked_by_other_rules")}


def suggest_repairs(s: Session, **_):
    _need(s)
    return {"repairs": [{"description": r["description"], "changes": r["changes"], "tail_loss_pct_after": r["tail_loss_pct_after"]}
                        for r in _assessment(s)["repairs"]]}


def what_if(s: Session, changes: dict, **_):
    _need(s)
    bad = set(changes) - WHAT_IF_KEYS
    if bad:
        raise ValueError(f"cannot change {sorted(bad)}; allowed: {sorted(WHAT_IF_KEYS)}")
    q = ProductSpec(**{**s.product.model_dump(), **changes})
    return {"changes": changes, **_summary(_assessment(s, q, full=False)), "note": "fast 3000-path simulation"}


def search_knowledge(s: Session, query: str, **_):
    hits = get_kb().search(query, k=3)
    return {"passages": [{"id": h["id"], "title": h["title"], "text": h["text"]} for h in hits]}


IMPL = {"get_context": get_context, "run_assessment": run_assessment, "run_scenario": run_scenario,
        "find_breaking_point": find_breaking_point, "suggest_repairs": suggest_repairs, "what_if": what_if,
        "search_knowledge": search_knowledge}

TOOLS = [
    {"name": "get_context", "description": "Current product terms and customer profile.", "input_schema": {"type": "object", "properties": {}}},
    {"name": "run_assessment", "description": "Full suitability assessment: decision, rules fired, historical replay and Monte Carlo metrics, breaking point.", "input_schema": {"type": "object", "properties": {}}},
    {"name": "run_scenario", "description": "Payoff of the current product if the underlying ends at a given % move (e.g. -25).",
     "input_schema": {"type": "object", "properties": {"market_move_pct": {"type": "number"}}, "required": ["market_move_pct"]}},
    {"name": "find_breaking_point", "description": "Market fall at which the product stops being suitable for this customer.", "input_schema": {"type": "object", "properties": {}}},
    {"name": "suggest_repairs", "description": "Verified product changes (notional, barrier, tenor) that clear the suitability flags.", "input_schema": {"type": "object", "properties": {}}},
    {"name": "what_if", "description": "Re-assess a modified copy of the product (barrier_pct, tenor_months, notional, coupon_pct, ...) without changing the session.",
     "input_schema": {"type": "object", "properties": {"changes": {"type": "object"}}, "required": ["changes"]}},
    {"name": "search_knowledge", "description": "Retrieve product explanations, policy and glossary passages (RAG). Cite ids like [kb:eln#1].",
     "input_schema": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}},
]


def execute(s: Session, name: str, args: dict) -> dict:
    out = IMPL[name](s, **args)
    s.tool_outputs.append(out)
    return out
