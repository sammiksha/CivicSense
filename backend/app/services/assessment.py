"""Orchestrates the deterministic engines into one assessment."""
from __future__ import annotations
from .. import config
from ..engines.market_data import get_prices
from ..engines.metrics import compute_metrics
from ..engines import suitability as suit
from ..engines.payoff import scenario_table
from ..engines.repair import suggest_repairs
from ..schemas import ProductSpec, CustomerProfile


def assess(p: ProductSpec, c: CustomerProfile, n_paths: int | None = None, with_repairs: bool = True) -> dict:
    rules = config.load_rules()
    prices, source = get_prices(p.underlying)
    m = compute_metrics(p, prices, n_paths)
    results = suit.evaluate(p, c, m["tail_loss_pct"], rules)
    decision = suit.overall(results)
    return {
        "product": p.model_dump(), "customer": c.model_dump(),
        "data_source": source, "data_window": [str(prices.index[0].date()), str(prices.index[-1].date())],
        "metrics": m, "rules": results, "decision": decision,
        "scenarios": scenario_table(p),
        "breaking_point": suit.breaking_point(p, c, rules),
        "repairs": suggest_repairs(p, c, rules, prices, decision) if with_repairs else [],
    }


def inr(x: float) -> str:
    """Indian digit grouping, e.g. 1000000 -> 'Rs 10,00,000'."""
    s = f"{abs(round(x)):d}"
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        s = ",".join(groups + [tail])
    return ("-" if x < 0 else "") + "Rs " + s


def facts(a: dict) -> dict:
    """Compact fact sheet handed to the LLM: the ONLY numbers it may quote."""
    p, c, m = a["product"], a["customer"], a["metrics"]
    bp = a["breaking_point"]
    return {
        "decision": a["decision"],
        "product": {**p, "notional_text": inr(p["notional"])},
        "customer": {k: c[k] for k in ("id", "risk_appetite", "loss_tolerance_pct", "horizon_months")},
        "rules": [{k: r[k] for k in ("rule_id", "status", "message")} for r in a["rules"]],
        "tail_loss_pct": m["tail_loss_pct"],
        "historical": {k: m["historical"][k] for k in ("n_windows", "best_pct", "worst_pct", "avg_pct", "pct_windows_loss", "worst_window")},
        "monte_carlo": {k: m["monte_carlo"][k] for k in ("n_paths", "prob_loss_pct", "prob_barrier_breach_pct", "p5_pct", "median_pct")},
        "scenarios": a["scenarios"],
        "breaking_point": {k: bp[k] for k in ("suitable_until_pct", "review_from_pct", "mismatch_from_pct", "blocked_by_other_rules")},
        "repairs": [{"description": r["description"], "changes": r["changes"]} for r in a["repairs"]],
        "data_source": a["data_source"], "data_window": a["data_window"],
    }
