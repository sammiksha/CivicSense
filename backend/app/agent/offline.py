"""Deterministic intent router used when no API key is configured (same tools, no LLM)."""
from __future__ import annotations
import re
from .session import Session
from .tools import execute


def _fmt(x):
    return "n/a" if x is None else f"{x:g}%"


def offline_copilot(s: Session, message: str, mode: str) -> tuple[str, list]:
    m, trace = message.lower(), []

    def call(name, **a):
        trace.append({"tool": name, "input": a, "ok": True})
        return execute(s, name, a)

    mv = re.search(r"(fall|falls|drop|drops|down|decline|crash|rise|rises|up|gain)\D{0,12}(\d+(?:\.\d+)?)\s*%", m)
    if mv:
        x = float(mv.group(2)) * (1 if mv.group(1) in ("rise", "rises", "up", "gain") else -1)
        r = call("run_scenario", market_move_pct=x)
        verdict = {"SUITABLE": "within", "REVIEW": "slightly above", "MISMATCH": "well above"}[r["loss_rule_status"]]
        breach = " The barrier would be breached." if r["barrier_breached"] else ""
        if mode == "client":
            return (f"If the market moves {x:g}%, your investment would end around {r['final_value']:,.0f} "
                    f"({r['pnl_pct']:g}% change). That is {verdict} the loss you said you are comfortable with ({r['customer_loss_tolerance_pct']:g}%).{breach}"), trace
        return f"Scenario {x:g}%: final value {r['final_value']:,.0f}, P&L {r['pnl_pct']:g}%.{breach} Loss rule: {r['loss_rule_status']} vs tolerance {r['customer_loss_tolerance_pct']:g}%.", trace
    if re.search(r"breaking|stop being suitable|stops? being suitable|how far", m):
        b = call("find_breaking_point")
        return (f"Suitable until about {_fmt(b['suitable_until_pct'])}; review from {_fmt(b['review_from_pct'])}; "
                f"mismatch from {_fmt(b['mismatch_from_pct'])}."), trace
    if re.search(r"repair|fix|reduce|change|make it suitable|alternative", m):
        r = call("suggest_repairs")["repairs"]
        return ("Options that clear the flags: " + "; ".join(x["description"] for x in r) + ".") if r else \
               "No bounded change clears all flags (or the product is already suitable).", trace
    if re.search(r"suitab|suit|should|fit|ok for|good for|assess", m):
        a = call("run_assessment")
        flagged = "; ".join(r["message"] for r in a["rules"] if r["status"] != "SUITABLE") or "no rules flagged"
        return f"Decision: {a['decision']}. Tail loss {a['tail_loss_pct']:g}%. Flags: {flagged}.", trace
    hits = call("search_knowledge", query=message)["passages"]
    if hits:
        return f"{hits[0]['text']} [kb:{hits[0]['id']}]", trace
    return "I can run scenarios, find the breaking point, suggest repairs, or explain the product. Try: 'What happens if NIFTY falls 25%?'", trace
