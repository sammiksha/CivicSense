"""Bounded search for the smallest change that clears the suitability flags."""
from __future__ import annotations
from .metrics import compute_metrics
from .suitability import evaluate, overall
from ..schemas import ProductSpec, CustomerProfile
from .. import config

FAST_PATHS = 3000
TENORS = (3, 6, 9, 12, 18, 24, 36)


def _describe(ch: dict, p: ProductSpec) -> str:
    parts = []
    if "notional" in ch:
        parts.append(f"reduce notional to {ch['notional']:,.0f}")
    if "barrier_pct" in ch:
        parts.append(f"lower barrier to {ch['barrier_pct']:g}%")
    if "tenor_months" in ch:
        parts.append(f"shorten tenor to {ch['tenor_months']} months")
    return ", and ".join(parts).capitalize()


def suggest_repairs(p: ProductSpec, c: CustomerProfile, rules: dict, prices, current_decision: str, top: int = 3) -> list[dict]:
    if current_decision == "SUITABLE":
        return []
    cache: dict = {}

    def metrics_for(q: ProductSpec, n: int):
        key = (q.barrier_pct, q.tenor_months, n)
        if key not in cache:
            cache[key] = compute_metrics(q, prices, n)
        return cache[key]

    barrier_opts = [None]
    if p.product_type == "ELN":
        b = p.barrier_pct - 5
        while b >= 40:
            barrier_opts.append(b)
            b -= 5
    tenor_opts = [None] + [t for t in TENORS if t < p.tenor_months]
    mults = [None] + [round(1 - 0.05 * i, 2) for i in range(1, 18)]
    found = []
    for b in barrier_opts:
        for t in tenor_opts:
            for m in mults:
                ch = {}
                if b is not None: ch["barrier_pct"] = b
                if t is not None: ch["tenor_months"] = t
                if m is not None: ch["notional"] = round(p.notional * m, -4)
                if not ch:
                    continue
                q = p.model_copy(update=ch)
                met = metrics_for(q, FAST_PATHS)
                if overall(evaluate(q, c, met["tail_loss_pct"], rules)) != "SUITABLE":
                    continue
                score = ((p.barrier_pct - b) / p.barrier_pct if b is not None else 0) \
                    + ((p.tenor_months - t) / p.tenor_months if t is not None else 0) \
                    + (1 - m if m is not None else 0)
                found.append((len(ch), score, ch, q))
    found.sort(key=lambda x: (x[0], x[1]))
    out = []
    for _, _, ch, q in found:
        met = compute_metrics(q, prices, config.MC_PATHS)  # re-verify with full simulation
        if overall(evaluate(q, c, met["tail_loss_pct"], rules)) == "SUITABLE":
            out.append({"changes": ch, "description": _describe(ch, p), "decision_after": "SUITABLE",
                        "tail_loss_pct_after": met["tail_loss_pct"]})
        if len(out) >= top:
            break
    return out
