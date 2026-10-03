"""LLM explanation grounded by RAG context + numeric grounding check.  Offline template fallback."""
from __future__ import annotations
from ..agent.grounding import ungrounded_numbers
from ..llm.client import get_llm
from ..rag.store import retrieve_for_assessment
from .assessment import facts, inr

SYSTEM = """You explain structured-product suitability results.
Rules:
- The deterministic engines already computed everything. Use ONLY numbers that appear in FACTS. Never calculate new numbers or invent any.
- Use the KNOWLEDGE passages for concepts and policy wording; cite them like [kb:eln#1] right after the sentence they support.
- You do not decide suitability; restate the decision from FACTS.
- mode=client: short plain sentences, no jargon, say what can be lost and when, never promise returns, mention past results do not guarantee future results.
- mode=rm: precise terms, list rules that fired with status, data window/source, then 2-3 talking points and the repair options.
- If data_source is synthetic_fallback, say clearly this is demo data.
Keep it under 220 words."""


def _fmt_shock(x):
    return "n/a" if x is None else f"{x:g}%"


def offline_explanation(a: dict, mode: str, kb: list[dict]) -> str:
    f = facts(a)
    d, bp = f["decision"], f["breaking_point"]
    cites = " ".join(f"[kb:{c['id']}]" for c in kb[:3])
    demo = " (demo data: synthetic fallback)" if f["data_source"] == "synthetic_fallback" else ""
    flagged = [r for r in f["rules"] if r["status"] != "SUITABLE"]
    rep = f["repairs"]
    if mode == "client":
        lines = [f"Result: {d}.",
                 f"If the market falls a lot, you can lose part of your money. In our worst modeled case you could lose about {f['tail_loss_pct']:g}% of the amount invested.",
                 f"Past results do not guarantee future results."]
        if flagged:
            lines.append("Why it needs attention: " + "; ".join(r["message"] for r in flagged) + ".")
        if bp["suitable_until_pct"] is not None:
            lines.append(f"This note stays within your comfort until the market falls about {_fmt_shock(bp['suitable_until_pct'])}.")
        if rep:
            lines.append("A safer version: " + rep[0]["description"] + ".")
        return " ".join(lines) + f" {cites}"
    lines = [f"Decision: {d}{demo}. Data window {f['data_window'][0]} to {f['data_window'][1]}.",
             "Rules: " + " | ".join(f"{r['rule_id']}={r['status']} ({r['message']})" for r in f["rules"]),
             f"Tail loss {f['tail_loss_pct']:g}%; historical worst {f['historical']['worst_pct']:g}%, loss-making windows {f['historical']['pct_windows_loss']:g}%; "
             f"Monte Carlo P(loss) {f['monte_carlo']['prob_loss_pct']:g}%, P(barrier breach) {f['monte_carlo']['prob_barrier_breach_pct']:g}%, 5th percentile {f['monte_carlo']['p5_pct']:g}%.",
             f"Breaking point: suitable until {_fmt_shock(bp['suitable_until_pct'])}, review from {_fmt_shock(bp['review_from_pct'])}, mismatch from {_fmt_shock(bp['mismatch_from_pct'])}."]
    if rep:
        lines.append("Repair options: " + "; ".join(r["description"] for r in rep) + ".")
    return "\n".join(lines) + f"\n{cites}"


def explain(a: dict, mode: str = "rm") -> dict:
    kb = retrieve_for_assessment(a)
    f = facts(a)
    llm = get_llm()
    if llm is None:
        return {"text": offline_explanation(a, mode, kb), "engine": "offline-template", "sources": [c["id"] for c in kb], "warnings": []}
    ctx = "\n\n".join(f"[kb:{c['id']}] {c['title']}\n{c['text']}" for c in kb)
    user = f"mode={mode}\n\nFACTS:\n{f}\n\nKNOWLEDGE:\n{ctx}"
    try:
        text = llm.complete(SYSTEM, user)
        bad = ungrounded_numbers(text, f, extra=str(f["product"]))
        if bad:  # one corrective retry
            text = llm.complete(SYSTEM, user + f"\n\nYour previous draft used numbers not in FACTS: {bad}. Rewrite without them.")
            bad = ungrounded_numbers(text, f, extra=str(f["product"]))
        return {"text": text, "engine": "llm+rag", "sources": [c["id"] for c in kb],
                "warnings": [f"ungrounded numbers: {bad}"] if bad else []}
    except Exception as e:
        return {"text": offline_explanation(a, mode, kb), "engine": "offline-fallback", "sources": [c["id"] for c in kb],
                "warnings": [f"LLM unavailable: {type(e).__name__}"]}
