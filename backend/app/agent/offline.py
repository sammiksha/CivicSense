"""Dynamic conversational agent for FinVision AI Assistant.
Executes real deterministic tools dynamically based on user intent and active context.
"""
from __future__ import annotations
import re
from typing import Optional
from .session import Session
from .tools import execute
from ..schemas import ProductSpec, CustomerProfile


def _inr(x: float) -> str:
    """Format rupee amounts in Indian currency notation."""
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
    return ("-" if x < 0 else "") + "₹" + s


def _clean_passage(text: str) -> str:
    text = re.sub(r"\[kb:[^\]]+\]", "", text)
    lines = [l.strip() for l in text.splitlines() if l.strip() and not l.startswith("#")]
    joined = " ".join(lines)
    if "Reference asset, reference index" in joined:
        return ("**NIFTY 50** is India's premier stock market benchmark index representing "
                "the top 50 largest and most liquid companies listed on the National Stock Exchange (NSE).")
    return joined


def offline_copilot(s: Session, message: str, mode: str = "client", page_context: Optional[str] = None) -> tuple[str, list]:
    m = message.lower().strip()
    trace = []

    # In RM mode, require customer and product for assessment/scenario/repair queries
    if (s.product is None or s.customer is None) and mode == "rm":
        if re.search(r"(suitab|suit|should|fit|ok for|good for|assess|breaking|repair|scenario|fall|drop|move|shock)", m):
            return "Select a customer and configure a product first.", trace

    # Ensure default fallback product & customer context for exploratory client questions
    p = s.product or ProductSpec(product_type="ELN", underlying="NIFTY 50", tenor_months=12, coupon_pct=12, barrier_pct=70, notional=1_000_000)
    c = s.customer or CustomerProfile(id="C101", name="Rahul Gupta", risk_appetite="conservative", loss_tolerance_pct=5, horizon_months=24, portfolio_value=10_000_000, annual_income_inr=3_000_000)
    if s.product is None:
        s.product = p
    if s.customer is None:
        s.customer = c

    def call(name, **a):
        trace.append({"tool": name, "input": a, "ok": True})
        return execute(s, name, a)

    # ─────────────────────────────────────────────────────────────
    # CONTEXT-AWARE RESOLUTION (based on page_context)
    # ─────────────────────────────────────────────────────────────
    if page_context and re.search(r"\b(why did this|why does this|where does this|what is this|explain this page)\b", m):
        if "portfolio" in page_context.lower():
            pi = call("portfolio_impact", stress_shock_pct=-35.0)
            return (
                f"📊 **Context: Portfolio Impact**\n\n"
                f"You are viewing the **Portfolio Impact** page. Here is why the numbers changed:\n"
                f"• **Exposure Increase**: Your {p.underlying} exposure increases from **{pi['before']['exposures'].get(p.underlying, {}).get('pct', 0)}%** to **{pi['concentration_pct']}%** after adding this {_inr(p.notional)} product.\n"
                f"• **Stress Loss Delta**: In a severe market crash (-35%), your portfolio downside loss increases by **+{pi['delta_loss_pct']}%** ({_inr(pi['delta_loss_inr'])} additional loss).\n"
                f"• **Concentration Status**: The policy limit is **{pi['concentration_limit_pct']}%**, so this product triggers a **{'CONCENTRATION WARNING' if pi['concentration_flag'] else 'SAFE'}** status."
            ), trace
        elif "stress" in page_context.lower():
            bp = call("find_breaking_point")
            return (
                f"⚡ **Context: Stress Ladder & Regimes**\n\n"
                f"You are viewing the **Stress Analysis** page. Here is where the product behavior changes:\n"
                f"• **Safe until**: A market fall of **{abs(bp.get('suitable_until_pct') or 0):g}%**.\n"
                f"• **Review required from**: **{bp.get('review_from_pct')}%** market decline.\n"
                f"• **Mismatch from**: **{bp.get('mismatch_from_pct')}%** drop, where the safety cushion is breached and losses exceed your loss tolerance."
            ), trace

    # ─────────────────────────────────────────────────────────────
    # 1. WHAT-IF PARAMETER CHANGES ("What if barrier is 65% / reduced?")
    # ─────────────────────────────────────────────────────────────
    wi_barrier = re.search(r"barrier\D{0,10}(\d{2})\s*%", m)
    if wi_barrier and re.search(r"\b(what if|change|reduced|set to|increased|lower)\b", m):
        new_bar = float(wi_barrier.group(1))
        res = call("what_if", changes={"barrier_pct": new_bar})
        bp = res.get("breaking_point", {})
        return (
            f"🔄 **What-If Simulation: Barrier changed to {new_bar:g}%**\n\n"
            f"If the barrier is adjusted from **{p.barrier_pct}%** to **{new_bar:g}%**:\n"
            f"• **Safety Buffer**: The market can now drop up to **{100 - new_bar:g}%** before your principal is touched (an extra {p.barrier_pct - new_bar:g}% buffer!).\n"
            f"• **Modeled Tail Loss**: Down to **{res.get('tail_loss_pct', 0):.1f}%**.\n"
            f"• **Suitability Verdict**: **{res.get('decision')}**.\n"
            f"• **Breaking Point**: Remains safe until approximately **{bp.get('suitable_until_pct')}%** market fall."
        ), trace

    # ─────────────────────────────────────────────────────────────
    # 2. DYNAMIC SCENARIO EVALUATION ("What happens if market falls/rises X%?")
    # ─────────────────────────────────────────────────────────────
    mv = re.search(r"(fall|falls|drop|drops|down|decline|crash|rise|rises|up|gain)\D{0,12}(\d+(?:\.\d+)?)\s*%", m)
    if mv:
        pct = float(mv.group(2))
        is_fall = mv.group(1) in ("fall", "falls", "drop", "drops", "down", "decline", "crash")
        move_pct = -pct if is_fall else pct
        r = call("run_scenario", market_move_pct=move_pct)

        notional_txt = _inr(p.notional)
        final_val_txt = _inr(r["final_value"])
        pnl_val_txt = _inr(abs(r["pnl"]))
        verdict = {"SUITABLE": "within", "REVIEW": "slightly above", "MISMATCH": "well above"}.get(r["loss_rule_status"], r["loss_rule_status"])

        if mode == "client":
            if is_fall:
                if not r["barrier_breached"]:
                    return (
                        f"📉 **If NIFTY falls by {pct:g}% at maturity:**\n\n"
                        f"• **Barrier Status**: **Safe!** The market drop of {pct:g}% is within your **{100 - (p.barrier_pct or 70)}% safety buffer** (Barrier at {p.barrier_pct}%).\n"
                        f"• **Your Payout**: You receive your full principal back **PLUS your {p.coupon_pct}% annual coupon**.\n"
                        f"• **Rupee Outcome**: Your **{notional_txt}** investment matures at **{final_val_txt}** ({r['final_value']:,.0f}) (+{pnl_val_txt} profit, **+{r['pnl_pct']}%**).\n"
                        f"• **Suitability**: That is {verdict} the loss you said you are comfortable with ({c.loss_tolerance_pct:g}%)."
                    ), trace
                else:
                    return (
                        f"⚠️ **If NIFTY falls heavily by {pct:g}% at maturity:**\n\n"
                        f"• **Barrier Status**: **Breached!** The market drop of {pct:g}% falls below your **{p.barrier_pct}% safety barrier**.\n"
                        f"• **Your Payout**: Your principal participates in the market loss, offset by your {p.coupon_pct}% coupon payout.\n"
                        f"• **Rupee Outcome**: Your **{notional_txt}** investment reduces to **{final_val_txt}** ({r['final_value']:,.0f}) (a net loss of **{pnl_val_txt}** or **{r['pnl_pct']}%**).\n"
                        f"• **Suitability Alert**: Your stated loss tolerance is **{c.loss_tolerance_pct}%**. A {abs(r['pnl_pct'])}% loss triggers a **{r['loss_rule_status']}** flag."
                    ), trace
            else:
                return (
                    f"📈 **If NIFTY rises by {pct:g}% at maturity:**\n\n"
                    f"• **Your Payout**: You receive your full initial capital back **PLUS your {p.coupon_pct}% annual coupon**.\n"
                    f"• **Rupee Outcome**: Your **{notional_txt}** investment matures at **{final_val_txt}** ({r['final_value']:,.0f}) (+{pnl_val_txt} profit, **+{r['pnl_pct']}%**).\n"
                    f"• *(Note: As an ELN, upside is capped at your {p.coupon_pct}% coupon).* "
                ), trace

        breach = " The barrier would be breached." if r["barrier_breached"] else ""
        return (
            f"Scenario {move_pct:g}%: final value {r['final_value']:,.0f}, P&L {r['pnl_pct']:g}%.{breach} "
            f"Loss rule: {r['loss_rule_status']} vs tolerance {r['customer_loss_tolerance_pct']:g}%."
        ), trace

    # ─────────────────────────────────────────────────────────────
    # 3. 2020 CRASH / HISTORICAL WINDOW QUERY
    # ─────────────────────────────────────────────────────────────
    if re.search(r"\b(2020|covid|crash|historical replay|past crash|crisis)\b", m):
        rep = call("historical_replay")
        twin = call("historical_twin")
        return (
            f"📜 **Historical Market Crash Analysis**\n\n"
            f"• **Historical Replay**: Backtested over **{rep.get('n_windows', 0)}** rolling windows of {p.tenor_months} months.\n"
            f"• **Worst-Case Historical Window**: {rep.get('worst_window', ['2020-01', '2021-01'])[0]} to {rep.get('worst_window', ['2020-01', '2021-01'])[1]}.\n"
            f"• **Worst Historical Loss**: **{rep.get('worst_pct', 0):g}%** (Loss-making windows: **{rep.get('pct_windows_loss', 0):g}%**).\n"
            f"• **Best Historical Window**: **+{rep.get('best_pct', 0):g}%**.\n"
            f"• **Historical Twin**: The most similar historical regime scored **{twin.get('twin', {}).get('similarity_score', 0.85):.2f}** similarity with product return of **{twin.get('twin', {}).get('product_pnl_pct', 12)}%**.\n\n"
            f"💡 *Note: Past performance does not guarantee future results. Used strictly for stress assessment.*"
        ), trace

    # ─────────────────────────────────────────────────────────────
    # 4. CONCENTRATION & PORTFOLIO IMPACT
    # ─────────────────────────────────────────────────────────────
    if re.search(r"\b(concentration|portfolio impact|why.*concentration|exposure high|asset allocation)\b", m):
        pi = call("portfolio_impact", stress_shock_pct=-35.0)
        return (
            f"📁 **Portfolio Concentration Analysis**\n\n"
            f"• **Why concentration is high**: Prior to this note, your portfolio had **{pi['before']['exposures'].get(p.underlying, {}).get('pct', 0)}%** exposure to {p.underlying}. Adding this {_inr(p.notional)} note raises it to **{pi['concentration_pct']}%**.\n"
            f"• **Policy Limit**: Bank suitability policy caps single-underlying exposure at **{pi['concentration_limit_pct']}%**.\n"
            f"• **Stress Loss Impact**: In a -35% crash, your portfolio loss increases from {pi['before']['loss_pct']}% to **{pi['after']['loss_pct']}%** (+{pi['delta_loss_pct']}% delta or {_inr(pi['delta_loss_inr'])}).\n"
            f"• **Solution**: Reduce the product investment ticket (e.g. from ₹10L to ₹5L) to stay within the 50% limit."
        ), trace

    # ─────────────────────────────────────────────────────────────
    # 5. WHY MARKED REVIEW / MISMATCH
    # ─────────────────────────────────────────────────────────────
    if re.search(r"\b(why.*review|why.*mismatch|why.*not suitable|explain.*verdict|rules fired|flags)\b", m):
        a = call("run_assessment")
        flagged_rules = [r for r in a.get("rules", []) if r.get("status") != "SUITABLE"]
        rule_lines = "\n".join([f"• **{r['rule_id']} ({r['name']})**: {r['message']}" for r in flagged_rules]) or "All suitability rules passed."
        return (
            f"🔍 **Why this product is marked '{a.get('decision')}'**\n\n"
            f"FinVision's deterministic rule engine evaluated your investment profile against this note:\n\n"
            f"{rule_lines}\n\n"
            f"• **Modeled Tail Risk Loss**: **{a.get('tail_loss_pct', 0):.1f}%** vs your configured comfort limit of **{c.loss_tolerance_pct}%**.\n"
            f"• **Relationship Manager Action**: Discuss adjusting the barrier or notional using the Repair tool."
        ), trace

    # ─────────────────────────────────────────────────────────────
    # 6. HOW MUCH COULD I LOSE IN RUPEES? / RUPEE IMPACT
    # ─────────────────────────────────────────────────────────────
    if re.search(r"\b(how much.*lose|rupee loss|loss in rupees|worst case|rupee impact|maximum loss|tail loss)\b", m):
        a = call("run_assessment")
        tail_loss = a["tail_loss_pct"]
        loss_inr = round(p.notional * tail_loss / 100.0)
        income_info = ""
        if c.annual_income_inr:
            monthly = c.annual_income_inr / 12.0
            months = round(loss_inr / monthly, 1) if monthly else 1.0
            income_info = f"\n• **Income Context**: This modeled loss represents **~{months} months of your annual income**."

        return (
            f"💰 **Rupee Impact & Worst-Case Risk Analysis**\n\n"
            f"• **Investment Amount**: **{_inr(p.notional)}**\n"
            f"• **Modeled Tail Risk Loss**: **{tail_loss:.1f}%**\n"
            f"• **Rupee Amount at Risk**: **{_inr(loss_inr)}**{income_info}\n\n"
            f"🔍 **Why this matters**: You configured a maximum loss tolerance of **{c.loss_tolerance_pct}%** ({_inr(p.notional * c.loss_tolerance_pct / 100)}). "
            f"Because the product's modeled loss of {tail_loss:.1f}% exceeds your {c.loss_tolerance_pct}% limit, the platform marked this as **{a['decision']}**."
        ), trace

    # ─────────────────────────────────────────────────────────────
    # 7. BREAKING POINT SCANNER
    # ─────────────────────────────────────────────────────────────
    if re.search(r"\b(breaking|stop being suitable|stops? being suitable|how far|when do i lose|tolerance limit)\b", m):
        b = call("find_breaking_point")
        until = b.get("suitable_until_pct")
        if mode == "client":
            if until is not None:
                return (
                    f"🛡️ **Your Breaking Point Analysis**\n\n"
                    f"• **Safe Buffer**: The product remains fully protected until NIFTY falls by **{abs(until):g}%**.\n"
                    f"• **Review Threshold**: Between **{b.get('review_from_pct')}%** and **{b.get('mismatch_from_pct')}%**, risk warnings are triggered.\n"
                    f"• **Mismatch Trigger**: If NIFTY falls beyond **{b.get('mismatch_from_pct')}%**, your safety barrier is breached and your capital takes losses exceeding your comfort level."
                ), trace
        def _f(x): return "n/a" if x is None else f"{x:g}%"
        return (
            f"Suitable until about {_f(b['suitable_until_pct'])}; review from {_f(b['review_from_pct'])}; "
            f"mismatch from {_f(b['mismatch_from_pct'])}."
        ), trace

    # ─────────────────────────────────────────────────────────────
    # 8. DATE, TIME & MARKET HOURS
    # ─────────────────────────────────────────────────────────────
    if re.search(r"\b(current time|what time|time is it|time now|todays? date|what date|date today|current date|today is|date)\b", m) and not re.search(r"\b(barrier|coupon|tenor|product|maturity)\b", m):
        import datetime
        now = datetime.datetime.now()
        dt_str = now.strftime("%A, %d %B %Y")
        tm_str = now.strftime("%I:%M %p")
        weekday = now.weekday()
        is_market_day = weekday < 5
        market_status = "🟢 Market session active" if is_market_day and (9 <= now.hour < 15 or (now.hour == 15 and now.minute <= 30)) else "⚪ Indian markets (NSE/BSE) are currently closed"

        return (
            f"🕒 **Current Date & Time**\n\n"
            f"• **Date**: **{dt_str}**\n"
            f"• **Time**: **{tm_str}**\n"
            f"• **Market Status**: {market_status} *(Regular Trading: 9:15 AM – 3:30 PM IST, Mon–Fri)*\n\n"
            f"Let me know if you would like to analyze market movements or check product scenarios!"
        ), trace

    # ─────────────────────────────────────────────────────────────
    # 9. GREETINGS & GENERAL CONVERSATIONAL RESPONSES
    # ─────────────────────────────────────────────────────────────
    if re.search(r"^(hi|hello|hey|greetings|who are you|help|what can you do)\b", m):
        cust_name = c.name if c else "Investor"
        return (
            f"Hello {cust_name}! 👋 I am your **FinVision AI Guide**.\n\n"
            "I'm here to help you understand structured investments in simple, everyday language before you make any decisions.\n\n"
            "Here are some questions you can ask me:\n"
            "• **'What is NIFTY 50?'** — Learn what the market index represents.\n"
            "• **'How does an ELN / Barrier work?'** — Understand how your safety buffer protects you.\n"
            "• **'What happens if the market falls 35%?'** — See your exact return and rupee outcome.\n"
            "• **'Why is this product marked Review?'** — View exact suitability factors.\n"
            "• **'How much could I lose in Rupees?'** — View worst-case scenarios in real ₹ Lakhs.\n\n"
            "What would you like to explore today?"
        ), trace

    if re.search(r"\b(thank you|thanks|great|awesome|helpful)\b", m):
        return (
            "You're very welcome! 😊 I am always here to help you understand your investments and protect your wealth. Feel free to ask any other questions anytime!"
        ), trace

    if re.search(r"\b(how are you|how are u)\b", m):
        return (
            "I'm doing great, thank you! Ready to help you explore your portfolio, understand structured products, or run stress test scenarios. How can I assist you today?"
        ), trace

    # ─────────────────────────────────────────────────────────────
    # 10. CORE FINANCIAL CONCEPTS (PLAIN LANGUAGE EXPLAINERS)
    # ─────────────────────────────────────────────────────────────
    if re.search(r"\b(what is|what's|explain|tell me about|define|meaning of)\b.*\b(nifty|nifty 50|index|nse)\b", m) or m in ("nifty", "nifty 50", "what is nifty", "what is nifty?", "what is nifty 50", "what is nifty 50?"):
        return (
            "**What is the NIFTY 50?**\n\n"
            "Think of the **NIFTY 50** as a **barometer or health check for India's economy**.\n\n"
            "• It tracks the **50 largest and most established companies** in India (such as Reliance, TCS, HDFC Bank, Infosys, and ICICI Bank).\n"
            "• When news channels say *'the Indian stock market is up 1%'*, they usually mean the NIFTY 50 has gone up.\n"
            "• In your structured product, your investment payout is linked to the performance of this NIFTY 50 basket rather than a single risky stock."
        ), trace

    if re.search(r"\b(what is|what's|explain|tell me about)\b.*\b(usdinr|usd/inr|dollar|currency|exchange rate)\b", m) or m in ("usdinr", "usd/inr", "what is usdinr", "what is usdinr?"):
        return (
            "**What is USD/INR?**\n\n"
            "**USD/INR** is the exchange rate between the **US Dollar ($)** and the **Indian Rupee (₹)**.\n\n"
            "• For example, if USD/INR is at 83.50, it means 1 US Dollar costs ₹83.50.\n"
            "• In currency-linked products (like Dual Currency Deposits), your yield is boosted, but if the rupee strengthens or weakens past a preset level, your repayment may convert to the alternate currency."
        ), trace

    if re.search(r"\b(what is|what's|explain|tell me about|how does.*work)\b.*\b(eln|equity linked note|structured product|note)\b", m) or m in ("eln", "what is eln", "what is eln?"):
        return (
            "**What is an Equity-Linked Note (ELN)?**\n\n"
            "An **Equity-Linked Note (ELN)** is a wealth product that offers a **high fixed coupon (interest)** with built-in downside protection.\n\n"
            "Here is how it works in 3 simple parts:\n"
            f"1. **Fixed Reward (Coupon)**: You receive an attractive annual return (e.g. **{p.coupon_pct}%**).\n"
            f"2. **Safety Cushion (Barrier)**: As long as the market does not fall below your safety line (e.g. **{p.barrier_pct}%** of starting level, which is a {100 - p.barrier_pct}% drop buffer), you get **100% of your invested capital back + your coupon**.\n"
            f"3. **Downside Risk**: Only if the market experiences a severe crash beyond your {100 - p.barrier_pct}% buffer do you start sharing the loss with the market."
        ), trace

    if re.search(r"\b(what is|what's|explain|how does|tell me about)\b.*\b(barrier|knock in|safety net|cushion|buffer)\b", m) or m in ("barrier", "what is barrier", "what is a barrier", "what is barrier?"):
        buffer_pct = 100 - (p.barrier_pct or 70)
        return (
            "**What is a Barrier?**\n\n"
            f"A **Barrier** is your **downside safety net or airbag**.\n\n"
            f"• In your current product, the barrier is set at **{p.barrier_pct}%**.\n"
            f"• This means the market can fall by up to **{buffer_pct}%** during the investment term, and your principal is **100% safe and intact**.\n"
            f"• If the market drops *more* than {buffer_pct}%, the barrier is breached, and your capital is no longer protected against market declines."
        ), trace

    if re.search(r"\b(what is|what's|explain|tell me about)\b.*\b(coupon|interest|payout|yield|gain)\b", m) or m in ("coupon", "what is coupon", "what is coupon?"):
        inr_coupon = round(p.notional * p.coupon_pct / 100)
        return (
            "**What is a Coupon?**\n\n"
            "A **Coupon** is the **fixed annual interest** paid to you for investing in the structured note.\n\n"
            f"• For this product, the coupon rate is **{p.coupon_pct}% per year**.\n"
            f"• On an investment of **{_inr(p.notional)}**, this equals **{_inr(inr_coupon)}** in interest payout over the tenor."
        ), trace

    if re.search(r"\b(can i lose|is my money safe|is principal safe|risk of loss|guaranteed|capital safe|lose money|protected)\b", m):
        buffer_pct = 100 - (p.barrier_pct or 70)
        return (
            "**Is your principal protected if NIFTY falls?**\n\n"
            f"• **Protected Zone**: If NIFTY stays above the **{p.barrier_pct}% barrier** (meaning it does not fall more than {buffer_pct}%), **100% of your principal is returned**, PLUS your **{p.coupon_pct}% annual coupon**!\n"
            f"• **Loss Zone**: If NIFTY experiences a deep crash beyond **{buffer_pct}%**, the barrier is breached. At that point, your principal participates in the market decline (e.g. at -35%, final value is {_inr(p.notional * 0.77)} after coupon).\n"
            f"• **Suitability Status**: Because your profile has a conservative **{c.loss_tolerance_pct}% loss tolerance**, our suitability engine flagged this for RM review."
        ), trace

    # ─────────────────────────────────────────────────────────────
    # 11. REPAIR / HOW TO FIX / ALTERNATIVE OPTIONS
    # ─────────────────────────────────────────────────────────────
    if re.search(r"\b(repair|fix|make.*suitable|alternative|how to solve|what should i change|options|reduce|change)\b", m):
        rep = call("suggest_repairs").get("repairs", [])
        if rep:
            if mode == "client":
                lines = [f"{i+1}. **{r['description']}** (Reduces tail loss to {r['tail_loss_pct_after']}%)" for i, r in enumerate(rep)]
                return (
                    "🔧 **Recommended Repair Options**\n\n"
                    "To make this product suitable for your conservative profile, the engine identified these mathematically verified adjustments:\n\n"
                    + "\n".join(lines) + "\n\n"
                    "You can ask your Relationship Manager to apply any of these modified parameters in the Product Studio."
                ), trace
            return ("Options that clear the flags: " + "; ".join(x["description"] for x in rep) + "."), trace
        return (
            "No bounded change clears all flags (or the product is already suitable)."
        ), trace

    # ─────────────────────────────────────────────────────────────
    # 12. SUITABILITY ASSESSMENT & PROFILE MATCH
    # ─────────────────────────────────────────────────────────────
    if re.search(r"\b(suitab|suit|should|fit|ok for|good for|assess|verdict)\b", m):
        a = call("run_assessment")
        dec = a["decision"]
        if mode == "client":
            dec_badge = "✅ SUITABLE" if dec == "SUITABLE" else ("⚠️ REVIEW REQUIRED" if dec == "REVIEW" else "❌ SUITABILITY MISMATCH")
            flagged = [r["message"] for r in a["rules"] if r["status"] != "SUITABLE"]
            flag_text = ("\n• " + "\n• ".join(flagged)) if flagged else "All rules satisfied."
            return (
                f"📋 **Suitability Assessment for {c.name}**\n\n"
                f"**Overall Verdict**: **{dec_badge}**\n\n"
                f"• **Customer Risk Appetite**: {c.risk_appetite.title()} (Max {c.loss_tolerance_pct}% loss tolerance)\n"
                f"• **Modeled Tail Loss**: {a['tail_loss_pct']:.1f}%\n"
                f"• **Flagged Considerations**:{flag_text}\n\n"
                f"💡 *Recommendation: Discuss the repair options or alternative capital-protected notes with your RM.*"
            ), trace

        flagged = "; ".join(r["message"] for r in a["rules"] if r["status"] != "SUITABLE") or "no rules flagged"
        return f"Decision: {a['decision']}. Tail loss {a['tail_loss_pct']:g}%. Flags: {flagged}.", trace

    # ─────────────────────────────────────────────────────────────
    # 13. RAG KNOWLEDGE SEARCH (FALLBACK)
    # ─────────────────────────────────────────────────────────────
    if len(m.split()) >= 2 or any(k in m for k in ["nifty", "eln", "dcd", "cpn", "barrier", "coupon", "tenor", "strike", "suitab", "risk", "loss", "bank", "policy", "sebi", "rbi"]):
        hits = call("search_knowledge", query=message).get("passages", [])
        if hits:
            if mode == "client":
                cleaned = _clean_passage(hits[0]["text"])
                return (
                    f"**Here is what you need to know:**\n\n"
                    f"{cleaned}\n\n"
                    f"Feel free to ask if you'd like me to run a scenario or calculate your rupee impact!"
                ), trace
            return f"{hits[0]['text']} [kb:{hits[0]['id']}]", trace

    # ─────────────────────────────────────────────────────────────
    # 14. GENERAL DEFAULT HELPER
    # ─────────────────────────────────────────────────────────────
    return (
        "I am your FinVision AI Assistant. I can explain any product terms, calculate rupee outcomes, evaluate stress scenarios, or check suitability factors in simple language!\n\n"
        "Try asking:\n"
        "• *'What happens if NIFTY falls 35%?'*\n"
        "• *'Why is this product marked Review?'*\n"
        "• *'How much money could I lose in rupees?'*\n"
        "• *'What happens if the barrier is reduced to 65%?'*\n"
        "• *'How does this product affect my portfolio?'*\n"
        "• *'What is my breaking point?'*"
    ), trace
