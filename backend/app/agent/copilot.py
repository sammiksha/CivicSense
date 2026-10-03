"""Agentic copilot: Claude plans, calls deterministic tools (+RAG search), answer is numerically verified."""
from __future__ import annotations
from ..llm.client import get_llm
from .grounding import ungrounded_numbers
from .offline import offline_copilot
from .session import Session
from .tools import TOOLS, execute

SYSTEM = """You are the StructuraAI copilot for a bank's relationship managers and their customers.
You are an agent: decide which tools to call, call as many as needed, then answer.
Hard rules:
1. Never state a number that did not come from a tool result. Never do your own payoff or risk math - call run_scenario / what_if instead.
2. For concepts, policy or definitions call search_knowledge and cite passages like [kb:eln#1].
3. You do not decide suitability; report the rule engine's decision.
4. If product or customer is missing, say what the user must set first.
5. mode=client: short plain language, no jargon, what can be lost and when. mode=rm: precise, mention rule ids and the repair options.
6. Past performance does not guarantee future results. If data_source is synthetic_fallback say the data is demo data.
Keep answers under 180 words."""


def ask(s: Session, message: str, mode: str = "rm") -> dict:
    s.tool_outputs = []
    llm = get_llm()
    if llm is None:
        try:
            text, trace = offline_copilot(s, message, mode)
        except ValueError as e:
            text, trace = str(e), []
        engine, warnings = "offline-router", []
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
            engine, warnings = "llm-agent+rag", ([f"ungrounded numbers: {bad}"] if bad else [])
        except Exception as e:
            try:
                text, trace = offline_copilot(s, message, mode)
            except ValueError as ve:
                text, trace = str(ve), []
            engine, warnings = "offline-fallback", [f"LLM unavailable: {type(e).__name__}"]
    s.history += [{"role": "user", "content": message}, {"role": "assistant", "content": text}]
    return {"answer": text, "engine": engine, "tool_trace": trace, "warnings": warnings}
