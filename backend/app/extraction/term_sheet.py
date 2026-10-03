"""Term-sheet extraction: PDF/text -> (RAG glossary + LLM forced-tool JSON | regex fallback) -> validation.
Missing fields are reported for the RM to confirm; they are never guessed."""
from __future__ import annotations
import re
from typing import Optional
from pydantic import BaseModel, ValidationError
from ..llm.client import get_llm
from ..rag.store import get_kb
from ..schemas import ProductSpec, UNDERLYINGS


class ExtractedTerms(BaseModel):
    product_type: Optional[str] = None        # ELN | DCD | CPN
    underlying: Optional[str] = None          # NIFTY 50 | USDINR
    tenor_months: Optional[int] = None
    coupon_pct: Optional[float] = None        # annual %
    barrier_pct: Optional[float] = None
    strike_pct: Optional[float] = None
    protection_pct: Optional[float] = None
    participation_pct: Optional[float] = None
    notional: Optional[float] = None          # plain rupees
    currency: Optional[str] = None
    evidence: Optional[dict[str, str]] = None  # short source quote per field


REQUIRED = {"ELN": ["coupon_pct", "barrier_pct"], "DCD": ["coupon_pct", "strike_pct"], "CPN": ["protection_pct", "participation_pct"]}
BASE_REQUIRED = ["product_type", "underlying", "tenor_months", "notional"]


def pdf_to_text(data: bytes) -> str:
    import fitz  # PyMuPDF
    doc = fitz.open(stream=data, filetype="pdf")
    text = "\n".join(page.get_text() for page in doc)
    if len(text.strip()) < 40:  # likely scanned -> OCR
        try:
            import io, pytesseract
            from PIL import Image
            parts = []
            for page in doc:
                pix = page.get_pixmap(dpi=200)
                parts.append(pytesseract.image_to_string(Image.open(io.BytesIO(pix.tobytes("png")))))
            text = "\n".join(parts)
        except Exception:
            pass
    return text


def file_to_text(filename: str, data: bytes) -> str:
    return pdf_to_text(data) if filename.lower().endswith(".pdf") else data.decode("utf-8", errors="ignore")


# ---------- offline heuristic ----------
_WORDS = {"one": 1, "two": 2, "three": 3, "five": 5}


def _num(pattern: str, text: str) -> Optional[float]:
    m = re.search(pattern, text, re.I)
    return float(m.group(1).replace(",", "")) if m else None


def heuristic_extract(text: str) -> dict:
    t = text.replace("\u20b9", "Rs ")
    d: dict = {}
    low = t.lower()
    if "equity linked" in low or re.search(r"\beln\b", low): d["product_type"] = "ELN"
    elif "dual currency" in low or re.search(r"\bdcd\b", low): d["product_type"] = "DCD"
    elif "capital protected" in low or re.search(r"\bcpn\b", low): d["product_type"] = "CPN"
    if "nifty" in low: d["underlying"] = "NIFTY 50"
    elif re.search(r"usd[/\- ]?inr", low): d["underlying"] = "USDINR"
    m = re.search(r"(?:tenor|maturity|term|period)[^0-9a-z]{0,10}(\d+)\s*(month|year)", t, re.I) or \
        re.search(r"(\d+|one|two|three|five)[- ]\s*(month|year)", t, re.I)
    if m:
        n = int(m.group(1)) if m.group(1).isdigit() else _WORDS[m.group(1).lower()]
        d["tenor_months"] = n * (12 if m.group(2).lower() == "year" else 1)
    pct = r"[^0-9\n]{0,25}(\d+(?:\.\d+)?)\s*%"
    for key, pat in {"coupon_pct": r"(?:coupon|interest rate|enhanced interest)", "barrier_pct": r"(?:knock[- ]?in|barrier|trigger)",
                     "strike_pct": r"(?:strike|conversion)", "protection_pct": r"(?:capital protection|protected amount|principal protection)",
                     "participation_pct": r"(?:participation)"}.items():
        v = _num(pat + pct, t)
        if v is not None: d[key] = v
    if d.get("protection_pct") is None and re.search(r"capital protection\s*:?\s*none", low):
        pass
    m = re.search(r"(?:notional|investment amount|face value|principal amount|deposit)[^0-9]{0,20}(?:rs\.?|inr)?\s*([\d,]+(?:\.\d+)?)\s*(lakh|lac|crore|cr|l)?\b", t, re.I)
    if m:
        v = float(m.group(1).replace(",", ""))
        unit = (m.group(2) or "").lower()
        d["notional"] = v * (1e5 if unit in ("lakh", "lac", "l") else 1e7 if unit in ("crore", "cr") else 1)
    return d


def _llm_extract(text: str, feedback: str = "") -> dict:
    llm = get_llm()
    gloss = get_kb().search("term sheet synonyms " + text[:600], k=3, docs=["term_sheet_glossary", "eln", "dcd", "cpn"])
    ctx = "\n".join(c["text"] for c in gloss)
    system = ("Extract structured-product terms from the term sheet into the tool. Use ONLY what the document states. "
              "If a field is not stated, leave it null - never guess. product_type is ELN, DCD or CPN. underlying is 'NIFTY 50' or 'USDINR'. "
              "coupon_pct is annual percent. notional in plain rupees (convert lakh/crore). Put a short verbatim quote per extracted field in evidence.")
    user = f"GLOSSARY:\n{ctx}\n\nTERM SHEET:\n{text[:12000]}" + (f"\n\nPrevious attempt had problems: {feedback}. Re-read the document and fix." if feedback else "")
    return llm.force_tool(system, user, "submit_term_sheet", "Submit extracted terms", ExtractedTerms.model_json_schema())


def validate(terms: dict) -> dict:
    clean = {k: v for k, v in terms.items() if v is not None and k != "evidence"}
    missing = [k for k in BASE_REQUIRED if k not in clean]
    if clean.get("product_type") in REQUIRED:
        missing += [k for k in REQUIRED[clean["product_type"]] if k not in clean]
    assumed = []
    if clean.get("product_type") == "ELN" and "strike_pct" not in clean:
        assumed.append("strike_pct = 100 (assumed, please confirm)")
    errors, product = [], None
    if clean.get("underlying") and clean["underlying"] not in UNDERLYINGS:
        errors.append(f"unsupported underlying '{clean['underlying']}' (supported: {list(UNDERLYINGS)})")
    if not missing and not errors:
        try:
            product = ProductSpec(**clean).model_dump()
        except ValidationError as e:
            errors += [f"{'.'.join(map(str, x['loc']))}: {x['msg']}" for x in e.errors()]
        except Exception as e:
            errors.append(str(e))
    return {"terms": clean, "evidence": terms.get("evidence"), "missing": missing, "assumed": assumed, "errors": errors,
            "valid": product is not None, "product": product, "needs_confirmation": missing + assumed}


def extract_product(text: str) -> dict:
    llm = get_llm()
    method, terms = "heuristic", None
    if llm is not None:
        try:
            feedback = ""
            for _ in range(3):  # extract -> validate -> self-repair loop
                terms = _llm_extract(text, feedback)
                res = validate(terms)
                if not res["errors"]:
                    break
                feedback = "; ".join(res["errors"])
            method = "llm+rag"
        except Exception:
            terms = None
    if terms is None:
        terms = heuristic_extract(text)
    res = validate(terms)
    res["method"] = method
    return res
