"""Teach-Back Check: 3 deterministic questions with engine-verified correct answers.
LLM may rephrase questions, but NEVER determines correctness.
"""
from __future__ import annotations


def get_questions(product: dict, assessment: dict) -> list[dict]:
    """Return teach-back questions with deterministic correct answers."""
    ptype = product.get("product_type", "ELN")
    barrier = product.get("barrier_pct")
    coupon = product.get("coupon_pct", 0)
    bp = assessment.get("breaking_point", {})
    suitable_until = bp.get("suitable_until_pct")
    decision = assessment.get("decision", "REVIEW")

    questions = []

    if ptype == "ELN":
        questions.append({
            "id": "Q1",
            "question": f"If the market falls significantly and the {barrier}% barrier is breached, can your principal fall?",
            "options": ["Yes, principal can be reduced", "No, principal is always protected", "Only the coupon is affected"],
            "correct_index": 0,
            "explanation": f"For an ELN: if the barrier ({barrier}%) is breached AND the final level is below the strike, principal is reduced proportionally.",
        })
        questions.append({
            "id": "Q2",
            "question": f"The product offers a {coupon}% annual coupon. Does this mean you cannot lose principal?",
            "options": ["No — the coupon is paid, but principal can still be reduced if the barrier is breached", "Yes — if coupon is paid, principal is safe", "Coupon guarantees full principal return"],
            "correct_index": 0,
            "explanation": "Coupon and principal protection are separate. Coupon is typically paid regardless, but principal is at risk if the barrier is breached.",
        })
    elif ptype == "DCD":
        questions.append({
            "id": "Q1",
            "question": "In a Dual Currency Deposit, what happens if the exchange rate moves past the conversion level?",
            "options": ["Your deposit is converted to the other currency at the strike rate", "You receive extra interest only", "Nothing changes"],
            "correct_index": 0,
            "explanation": "If the spot rate breaches the conversion level, repayment is in the alternate currency at the configured rate — potentially worth less in home currency.",
        })
        questions.append({
            "id": "Q2",
            "question": "Is the enhanced interest on a DCD a guarantee of no currency loss?",
            "options": ["No — the interest is earned, but currency conversion can reduce the overall return", "Yes — interest protects against currency loss", "Interest is not paid if conversion occurs"],
            "correct_index": 0,
            "explanation": "Interest is paid regardless, but if currency converts unfavorably, overall value in home currency may be lower.",
        })
    else:  # CPN
        questions.append({
            "id": "Q1",
            "question": "If the market falls, what does the Capital Protected Note protect?",
            "options": [f"The configured protection % ({product.get('protection_pct', 100)}%) of your principal", "All upside and downside", "Only the coupon payments"],
            "correct_index": 0,
            "explanation": f"A CPN protects only the configured % of principal (here: {product.get('protection_pct', 100)}%). The rest may participate in losses if protection < 100%.",
        })
        questions.append({
            "id": "Q2",
            "question": "If the market rises, do you get the full market return?",
            "options": ["Only the configured participation % of the return", "Yes, full market return", "You get a fixed return regardless"],
            "correct_index": 0,
            "explanation": f"Participation is capped at {product.get('participation_pct', 100)}% of the market return.",
        })

    # Q3: breaking point — always included
    if suitable_until is not None:
        q3_text = f"At approximately what market movement does this product stop being suitable under your current profile?"
        q3_opts = [
            f"Around {suitable_until:g}% market fall",
            "It is always suitable regardless of market conditions",
            "The product has no suitability limit",
        ]
        q3_correct = 0
        q3_exp = f"Based on the configured suitability rules, the loss rule changes status at approximately {suitable_until:g}% market movement."
    else:
        q3_text = "If you have a 5% loss tolerance and the product's modeled loss exceeds 5%, what suitability flag would be raised?"
        q3_opts = ["REVIEW or MISMATCH — the loss exceeds the tolerance", "SUITABLE — tolerances are just guidelines", "No flag — only absolute losses matter"]
        q3_correct = 0
        q3_exp = "The suitability rules compare modeled tail loss against your configured loss tolerance. Exceeding it triggers REVIEW or MISMATCH."

    questions.append({
        "id": "Q3",
        "question": q3_text,
        "options": q3_opts,
        "correct_index": q3_correct,
        "explanation": q3_exp,
    })

    return questions


def score_answers(questions: list[dict], answers: list[int]) -> dict:
    """Score answers deterministically. Returns score and flags."""
    correct = 0
    details = []
    for q, ans in zip(questions, answers):
        is_correct = (ans == q["correct_index"])
        if is_correct:
            correct += 1
        details.append({
            "id": q["id"],
            "correct": is_correct,
            "selected_index": ans,
            "correct_index": q["correct_index"],
            "explanation": q["explanation"],
        })
    total = len(questions)
    score = correct
    flag = score < total  # any wrong answer → understanding flag
    return {
        "score": score,
        "total": total,
        "score_text": f"{score}/{total}",
        "understanding_flag": flag,
        "flag_message": "Customer understanding flag: additional explanation may be required." if flag else "Customer demonstrated satisfactory understanding.",
        "details": details,
    }
