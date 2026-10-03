"""FinVision AI Copilot: LLM orchestration and grounded conversational assistant."""
from __future__ import annotations
from ..llm.client import get_llm
from .grounding import ungrounded_numbers
from .offline import offline_copilot
from .session import Session
from .tools import TOOLS, execute

SYSTEM = """You are FinVision's AI Assistant — Understand Before You Invest.
Your goal is to help investors and Relationship Managers understand structured products with complete clarity.

Guidelines by mode:
1. mode=client (Customer Mode):
   - Use warm, friendly, plain everyday language. Avoid complex Wall Street jargon.
   - Use simple analogies (e.g., barrier = safety net/cushion; NIFTY 50 = India's top 50 companies barometer; coupon = fixed interest reward).
   - Clearly explain what can be gained and what can be lost in simple terms and ₹ amounts.
   - Be helpful, conversational, and direct.

2. mode=rm (Relationship Manager Mode):
   - Professional, precise, reference rule IDs, breaking points, and mathematical repair alternatives.

Hard Grounding Rules:
1. Never state any financial numbers that did not come from tool results.
2. Call run_scenario, run_assessment, find_breaking_point, or search_knowledge to get exact figures.
3. You do not invent numbers; you explain the engine's deterministic calculations.
"""


def ask(s: Session, message: str, mode: str = "client") -> dict:
    s.tool_outputs = []
    llm = get_llm()
    if llm is None:
        try:
            text, trace = offline_copilot(s, message, mode)
        except ValueError as e:
            text, trace = str(e), []
        engine, warnings = "finvision-copilot-offline", []
    else:
        try:
            ctx = f"mode={mode}\nproduct={s.product.model_dump() if s.product else None}\ncustomer={s.customer.model_dump() if s.customer else None}"
            msgs = s.history[-6:] + [{"role": "user", "content": f"{ctx}\n\nQuestion: {message}"}]
            text, trace = llm.run_agent(SYSTEM, msgs, TOOLS, lambda n, a: execute(s, n, a))
            bad = ungrounded_numbers(text, s.tool_outputs, extra=ctx + message)
            if bad:
                text = llm.complete(SYSTEM, f"Rewrite this answer so every number comes from TOOL RESULTS only (drop unsupported numbers).\n"
                                              f"TOOL RESULTS: {s.tool_outputs}\nANSWER: {text}\nUnsupported numbers: {bad}")
                bad = ungrounded_numbers(text, s.tool_outputs, extra=ctx + message)
            engine, warnings = "finvision-llm-agent+rag", ([f"ungrounded numbers: {bad}"] if bad else [])
        except Exception as e:
            try:
                text, trace = offline_copilot(s, message, mode)
            except ValueError as ve:
                text, trace = str(ve), []
            engine, warnings = "finvision-copilot-fallback", [f"LLM unavailable: {type(e).__name__}"]
    s.history += [{"role": "user", "content": message}, {"role": "assistant", "content": text}]
    return {"answer": text, "engine": engine, "tool_trace": trace, "warnings": warnings}
