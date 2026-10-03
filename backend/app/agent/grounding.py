"""Numeric grounding guard: every number in an LLM answer must trace back to engine output."""
from __future__ import annotations
import re

NUM = re.compile(r"(?<![\w.#])-?\d[\d,]*\.?\d*")


def _collect(obj, out: set):
    if isinstance(obj, bool):
        return
    if isinstance(obj, (int, float)):
        out.add(abs(float(obj)))
    elif isinstance(obj, dict):
        for v in obj.values():
            _collect(v, out)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            _collect(v, out)
    elif isinstance(obj, str):
        for t in NUM.findall(obj):
            try:
                out.add(abs(float(t.replace(",", "").rstrip("."))))
            except ValueError:
                pass


def ungrounded_numbers(text: str, *sources, extra: str = "") -> list[str]:
    allowed: set = set()
    for s in sources:
        _collect(s, allowed)
    _collect(extra, allowed)
    clean = re.sub(r"\[kb:[^\]]*\]", "", text)
    clean = re.sub(r"(?m)^\s*\d+[.)]\s", "", clean)
    bad = []
    for tok in NUM.findall(clean):
        t = tok.replace(",", "").rstrip(".")
        try:
            x = abs(float(t))
        except ValueError:
            continue
        if x in (0, 1, 100) or 1990 <= x <= 2100:
            continue
        integer = "." not in t
        tol = 0.51 if integer else 0.051
        near_lakh = any(abs(x - a / 1e5) <= 0.051 or abs(x - a / 1e7) <= 0.0051 for a in allowed if a >= 1e5)
        if not (any(abs(x - a) <= tol for a in allowed) or near_lakh):
            bad.append(tok)
    return bad
