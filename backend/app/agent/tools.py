"""Deterministic tools the FinVision AI assistant can call.
Every number the agent reports must originate strictly from these tools.
"""
from __future__ import annotations
import json
from pathlib import Path
from .. import config
from ..engines import suitability as suit
from ..engines.payoff import value_fraction, barrier_breached, scenario_table, loss_at_shock
from ..engines.portfolio import portfolio_impact as calc_portfolio_impact, rupee_impact as calc_rupee_impact
from ..engines.stress import stress_ladder as calc_stress_ladder, regime_stress as calc_regime_stress
from ..engines.twin import find_twin
from ..engines.market_data import get_prices
from ..rag.store import get_kb
from ..schemas import ProductSpec, CustomerProfile
from ..services.assessment import assess
from .session import Session
from .. import alerts as alert_store

WHAT_IF_KEYS = {"barrier_pct", "tenor_months", "notional", "coupon_pct", "strike_pct", "protection_pct", "participation_pct"}


def load_customers() -> list[CustomerProfile]:
    raw = json.loads((config.DATA_DIR / "samples" / "customers.json").read_text(encoding="utf-8"))
    return [CustomerProfile(**c) for c in raw]


def find_customer(cid: str) -> CustomerProfile | None:
    return next((c for c in load_customers() if c.id == cid), None)


def _need(s: Session):
    if s.product is None:
        s.product = ProductSpec(product_type="ELN", underlying="NIFTY 50", tenor_months=12, coupon_pct=12, barrier_pct=70, notional=1_000_000)
    if s.customer is None:
        s.customer = find_customer("C101") or CustomerProfile(
            id="C101", name="Rahul Gupta", risk_appetite="conservative", loss_tolerance_pct=5,
            horizon_months=24, portfolio_value=10_000_000, annual_income_inr=3_000_000,
            existing_exposures={"NIFTY 50": 45}
        )


def _assessment(s: Session, p: ProductSpec | None = None, full: bool = True) -> dict:
    _need(s)
    p = p or s.product
    key = (p.model_dump_json(), s.customer.id, full)
    if key not in s.cache:
        s.cache[key] = assess(p, s.customer, n_paths=None if full else 3000, with_repairs=full)
    return s.cache[key]


def _summary(a: dict) -> dict:
    m, bp = a["metrics"], a["breaking_point"]
    return {
        "decision": a["decision"],
        "rules": [{k: r[k] for k in ("rule_id", "status", "message")} for r in a["rules"]],
        "tail_loss_pct": m["tail_loss_pct"],
        "historical": {k: m["historical"][k] for k in ("worst_pct", "best_pct", "avg_pct", "pct_windows_loss", "n_windows")},
        "monte_carlo": {k: m["monte_carlo"][k] for k in ("prob_loss_pct", "prob_barrier_breach_pct", "p5_pct")},
        "breaking_point": {k: bp[k] for k in ("suitable_until_pct", "review_from_pct", "mismatch_from_pct")},
        "data_source": a["data_source"]
    }


# ─── Individual Tool Functions ───────────────────────────────────────────────

def get_context(s: Session, **_):
    _need(s)
    return {"product": s.product.model_dump(), "customer": s.customer.model_dump()}


def get_customer_profile(s: Session, **_):
    _need(s)
    c = s.customer
    return {
        "id": c.id,
        "name": c.name,
        "risk_appetite": c.risk_appetite,
        "loss_tolerance_pct": c.loss_tolerance_pct,
        "horizon_months": c.horizon_months,
        "portfolio_value": c.portfolio_value,
        "annual_income_inr": c.annual_income_inr,
        "liquidity_need": c.liquidity_need,
        "existing_exposures": c.existing_exposures,
    }


def get_portfolio(s: Session, **_):
    _need(s)
    c = s.customer
    return {
        "total_value": c.portfolio_value,
        "existing_exposures": c.existing_exposures,
        "holdings": c.holdings,
    }


def get_product(s: Session, **_):
    _need(s)
    return s.product.model_dump()


def get_assessment(s: Session, **_):
    _need(s)
    return _summary(_assessment(s))


def assess_suitability(s: Session, **_):
    return get_assessment(s)


def run_assessment(s: Session, **_):
    return get_assessment(s)


def run_scenario(s: Session, market_move_pct: float, **_):
    _need(s)
    p, c = s.product, s.customer
    r = market_move_pct / 100.0
    v = float(value_fraction(p, r, min(r, 0.0)))
    loss = max(0.0, (1.0 - v) * 100.0)
    rules = config.load_rules()
    loss_inr = round(p.notional * loss / 100.0)
    final_value = round(p.notional * v, 2)
    pnl = round(p.notional * (v - 1.0), 2)
    pnl_pct = round((v - 1.0) * 100.0, 2)
    return {
        "underlying_change_pct": market_move_pct,
        "barrier_breached": bool(barrier_breached(p, min(r, 0.0))) if p.product_type == "ELN" else False,
        "final_value": final_value,
        "pnl": pnl,
        "pnl_pct": pnl_pct,
        "loss_pct": round(loss, 2),
        "loss_inr": loss_inr,
        "customer_loss_tolerance_pct": c.loss_tolerance_pct,
        "loss_rule_status": suit.loss_status(loss, c.loss_tolerance_pct, rules["loss_tolerance_review_multiple"]),
    }


def calculate_payoff(s: Session, **_):
    _need(s)
    scenarios = scenario_table(s.product)
    return {"product_type": s.product.product_type, "scenarios": scenarios}


def run_stress_ladder(s: Session, **_):
    _need(s)
    rules = config.load_rules()
    ladder = calc_stress_ladder(s.product, s.customer, rules)
    return {"stress_ladder": ladder}


def historical_replay(s: Session, **_):
    _need(s)
    a = _assessment(s)
    return a["metrics"]["historical"]


def historical_twin_tool(s: Session, **_):
    _need(s)
    prices, source = get_prices(s.product.underlying)
    twin = find_twin(s.product, prices)
    return twin


def find_breaking_point(s: Session, **_):
    _need(s)
    bp = _assessment(s)["breaking_point"]
    return {k: bp[k] for k in ("suitable_until_pct", "review_from_pct", "mismatch_from_pct", "blocked_by_other_rules")}


def suggest_repairs(s: Session, **_):
    _need(s)
    return {"repairs": [{"description": r["description"], "changes": r["changes"], "tail_loss_pct_after": r["tail_loss_pct_after"]}
                        for r in _assessment(s)["repairs"]]}


def repair_suitability(s: Session, **_):
    return suggest_repairs(s)


def portfolio_impact(s: Session, stress_shock_pct: float = -35.0, **_):
    _need(s)
    return calc_portfolio_impact(s.customer, s.product, stress_shock_pct=stress_shock_pct)


def rupee_impact(s: Session, **_):
    _need(s)
    a = _assessment(s)
    tail_loss = a["metrics"]["tail_loss_pct"]
    return calc_rupee_impact(s.product.model_dump(), tail_loss, s.customer.model_dump())


def get_risk_alerts(s: Session, **_):
    _need(s)
    alerts = alert_store.get_alerts_for_customer(s.customer.id)
    return {"alerts": alerts}


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


# ─── Tool Registry ──────────────────────────────────────────────────────────

IMPL = {
    "get_context": get_context,
    "get_customer_profile": get_customer_profile,
    "get_portfolio": get_portfolio,
    "get_product": get_product,
    "get_assessment": get_assessment,
    "assess_suitability": assess_suitability,
    "run_assessment": run_assessment,
    "run_scenario": run_scenario,
    "calculate_payoff": calculate_payoff,
    "run_stress_ladder": run_stress_ladder,
    "historical_replay": historical_replay,
    "historical_twin": historical_twin_tool,
    "find_breaking_point": find_breaking_point,
    "suggest_repairs": suggest_repairs,
    "repair_suitability": repair_suitability,
    "portfolio_impact": portfolio_impact,
    "rupee_impact": rupee_impact,
    "get_risk_alerts": get_risk_alerts,
    "what_if": what_if,
    "search_knowledge": search_knowledge,
}

TOOLS = [
    {
        "name": "run_scenario",
        "description": "Calculates the exact maturity payoff, final value in Rupees, net loss/profit in Rupees and %, and barrier breach status if the underlying index (NIFTY/USDINR) moves by a specified percentage (e.g. -35 for a 35% market drop).",
        "parameters": {
            "type": "object",
            "properties": {
                "market_move_pct": {"type": "number", "description": "Market movement percentage, e.g. -35 for 35% decline, +10 for 10% gain."}
            },
            "required": ["market_move_pct"]
        }
    },
    {
        "name": "rupee_impact",
        "description": "Calculates exact Rupee loss figures on the customer's notional amount under modeled tail risk, including equivalence in months of customer annual income.",
        "parameters": {"type": "object", "properties": {}}
    },
    {
        "name": "run_assessment",
        "description": "Executes full suitability assessment: decision (SUITABLE, REVIEW, MISMATCH), rules fired, tail risk loss %, historical replay worst/best, and breaking point.",
        "parameters": {"type": "object", "properties": {}}
    },
    {
        "name": "portfolio_impact",
        "description": "Calculates pre vs post portfolio asset concentration, underlying exposure, and loss delta in Rupees and % under stress shock.",
        "parameters": {
            "type": "object",
            "properties": {
                "stress_shock_pct": {"type": "number", "description": "Market shock percentage to evaluate (default -35%)."}
            }
        }
    },
    {
        "name": "find_breaking_point",
        "description": "Scans market declines to find the exact percentage drop at which the product stops being suitable for this customer and where it becomes a MISMATCH.",
        "parameters": {"type": "object", "properties": {}}
    },
    {
        "name": "run_stress_ladder",
        "description": "Evaluates payoff, loss in rupees, and suitability status across discrete shocks (0%, -5%, -10%, ..., -50%).",
        "parameters": {"type": "object", "properties": {}}
    },
    {
        "name": "suggest_repairs",
        "description": "Suggests mathematically verified product adjustments (e.g., lower barrier, smaller notional, longer tenor) that clear suitability flags.",
        "parameters": {"type": "object", "properties": {}}
    },
    {
        "name": "historical_twin",
        "description": "Finds the historical rolling window (e.g. 2008 crash, 2020 COVID) most similar to current market conditions and reports its outcome.",
        "parameters": {"type": "object", "properties": {}}
    },
    {
        "name": "historical_replay",
        "description": "Backtests the product across all historical rolling windows of tenor length.",
        "parameters": {"type": "object", "properties": {}}
    },
    {
        "name": "calculate_payoff",
        "description": "Returns standard scenario table and payoff calculation for current product parameters.",
        "parameters": {"type": "object", "properties": {}}
    },
    {
        "name": "what_if",
        "description": "Simulates a modified version of the product with altered parameters (e.g. changes={'barrier_pct': 65} or changes={'notional': 500000}) without altering the active session.",
        "parameters": {
            "type": "object",
            "properties": {
                "changes": {"type": "object", "description": "Dictionary of parameters to test (e.g. {'barrier_pct': 65})"}
            },
            "required": ["changes"]
        }
    },
    {
        "name": "get_customer_profile",
        "description": "Retrieves the currently selected customer profile (risk appetite, loss tolerance %, horizon, portfolio value, income).",
        "parameters": {"type": "object", "properties": {}}
    },
    {
        "name": "get_portfolio",
        "description": "Retrieves the customer's portfolio asset breakdown and existing underlying exposure.",
        "parameters": {"type": "object", "properties": {}}
    },
    {
        "name": "get_product",
        "description": "Retrieves the currently active product specification and parameters.",
        "parameters": {"type": "object", "properties": {}}
    },
    {
        "name": "get_risk_alerts",
        "description": "Retrieves active deterministic risk alerts fired for this customer.",
        "parameters": {"type": "object", "properties": {}}
    },
    {
        "name": "search_knowledge",
        "description": "Retrieves bank policies, structured product explainers, and regulatory guidelines (RAG).",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"}
            },
            "required": ["query"]
        }
    }
]


def execute(s: Session, name: str, args: dict) -> dict:
    if name not in IMPL:
        # Fallback aliases
        if name == "assess_suitability": name = "run_assessment"
        elif name == "repair_suitability": name = "suggest_repairs"
        elif name == "historical_twin": name = "historical_twin"
        else: raise ValueError(f"Unknown tool: {name}")
    out = IMPL[name](s, **args)
    s.tool_outputs.append({"tool": name, "output": out})
    return out
