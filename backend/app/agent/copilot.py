"""FinVision AI Assistant: Real-time LLM agent with deterministic tool execution and verified numbers."""
from __future__ import annotations
from typing import Optional
from ..llm.client import get_llm
from .grounding import ungrounded_numbers
from .offline import offline_copilot
from .session import Session
from .tools import TOOLS, execute

SYSTEM = """You are FinVision's customer financial-product explanation assistant — Understand Before You Invest.

Your role is to explain the verified results produced by FinVision's financial engines.
You do not provide investment advice.
You do not predict future market prices.
You do not choose products for the customer.
You do not invent financial values.

Core Principles:
1. When a question requires a calculation or verification, USE THE APPROPRIATE FINVISION BACKEND TOOL:
   - run_scenario: for any market movements (e.g., -35%, +10%), calculate exact payout, barrier breach, and rupee loss.
   - rupee_impact: to show exact ₹ money at risk and monthly income multiple.
   - run_assessment / assess_suitability: for suitability status, rules triggered, and tail risk.
   - portfolio_impact: for before/after allocation, concentration change, and stress loss delta.
   - find_breaking_point: to find the market fall % where the product stops being suitable.
   - run_stress_ladder: to view the shock ladder (0% to -50%).
   - suggest_repairs / repair_suitability: to find parameter changes that clear flags.
   - what_if: to evaluate what happens if a parameter is modified (e.g. barrier changed to 65%).
   - historical_twin / historical_replay: for backtest and historical similarity comparisons.
   - get_risk_alerts: to retrieve active risk alerts.
   - get_customer_profile / get_portfolio / get_product: to inspect active data.
   - search_knowledge: for bank policies, regulatory rules (SEBI/RBI), or structured note terminology.
2. Use ONLY verified tool results for financial numbers. Never calculate or invent numbers yourself.
3. Explain structured products in clear, customer-friendly, accessible language. Use simple everyday analogies (e.g. barrier = downside safety net; coupon = fixed interest reward; NIFTY 50 = top 50 Indian companies barometer).
4. If the user asks something unrelated to the available FinVision data, clearly state that the information is outside the available project context.
5. If the user asks whether they should invest, explain the relevant suitability factors and evidence instead of making the decision for them.
6. Always distinguish:
   - historical result
   - stress scenario
   - modeled result
   - actual customer data
7. Never present a scenario as a forecast or prediction.
"""


def ask(s: Session, message: str, mode: str = "client", page_context: Optional[str] = None) -> dict:
    s.tool_outputs = []
    llm = get_llm()

    ctx = f"mode={mode}\npage_viewing={page_context or 'AI Assistant'}\n"
    if s.product:
        ctx += f"active_product={s.product.model_dump()}\n"
    if s.customer:
        ctx += f"active_customer={s.customer.model_dump()}\n"

    if llm is None:
        try:
            text, trace = offline_copilot(s, message, mode, page_context=page_context)
        except ValueError as e:
            text, trace = str(e), []
        engine, warnings = "finvision-deterministic-agent", []
    else:
        try:
            msgs = list(s.history[-8:]) + [{"role": "user", "content": f"Context:\n{ctx}\n\nUser Question: {message}"}]
            text, trace = llm.run_agent(SYSTEM, msgs, TOOLS, lambda n, a: execute(s, n, a))
            bad = ungrounded_numbers(text, s.tool_outputs, extra=ctx + message)
            if bad:
                text = llm.complete(
                    SYSTEM,
                    f"Rewrite this answer so every financial number comes directly from TOOL RESULTS only (remove unsupported numbers).\n"
                    f"TOOL RESULTS: {s.tool_outputs}\nPROPOSED ANSWER: {text}\nUnsupported numbers: {bad}"
                )
                bad = ungrounded_numbers(text, s.tool_outputs, extra=ctx + message)
            engine, warnings = f"finvision-llm-agent ({llm.provider}:{llm.model})", ([f"ungrounded numbers: {bad}"] if bad else [])
        except Exception as e:
            try:
                text, trace = offline_copilot(s, message, mode, page_context=page_context)
            except ValueError as ve:
                text, trace = str(ve), []
            engine, warnings = "finvision-agent-fallback", [f"LLM API error ({type(e).__name__}): falling back to deterministic agent"]

    s.history.append({"role": "user", "content": message})
    s.history.append({"role": "assistant", "content": text})
    return {"answer": text, "engine": engine, "tool_trace": trace, "warnings": warnings}
