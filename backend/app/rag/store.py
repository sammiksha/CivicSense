"""Small, dependency-light RAG store: heading-aware chunking + TF-IDF (1-2 grams) retrieval.
Deterministic and offline.  To upgrade, swap `_vectorize` for an embedding model; the
`search()` contract (id, doc, title, text, score) stays the same."""
from __future__ import annotations
import re
from functools import lru_cache
from pathlib import Path
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import linear_kernel
from .. import config


def chunk_markdown(path: Path) -> list[dict]:
    text = path.read_text(encoding="utf-8")
    doc_title = re.search(r"^# (.+)$", text, re.M)
    doc_title = doc_title.group(1).strip() if doc_title else path.stem
    parts = re.split(r"^## ", text, flags=re.M)[1:]
    chunks = []
    for i, part in enumerate(parts):
        head, _, body = part.partition("\n")
        chunks.append({"id": f"{path.stem}#{i}", "doc": path.stem, "title": f"{doc_title} / {head.strip()}",
                       "text": body.strip()})
    return chunks


class KnowledgeBase:
    def __init__(self, directory: Path):
        self.chunks: list[dict] = []
        for p in sorted(Path(directory).glob("*.md")):
            self.chunks += chunk_markdown(p)
        self.vec = TfidfVectorizer(ngram_range=(1, 2), stop_words="english", sublinear_tf=True)
        self.matrix = self.vec.fit_transform([c["title"] + " " + c["text"] for c in self.chunks])

    def search(self, query: str, k: int = 4, min_score: float = 0.05, docs: list[str] | None = None) -> list[dict]:
        scores = linear_kernel(self.vec.transform([query]), self.matrix).ravel()
        order = scores.argsort()[::-1]
        out = []
        for i in order:
            c = self.chunks[i]
            if docs and c["doc"] not in docs:
                continue
            if scores[i] < min_score:
                break
            out.append({**c, "score": round(float(scores[i]), 3)})
            if len(out) >= k:
                break
        return out


@lru_cache(maxsize=1)
def get_kb() -> KnowledgeBase:
    return KnowledgeBase(config.KNOWLEDGE_DIR)


def retrieve_for_assessment(result: dict, k: int = 5) -> list[dict]:
    """Build a query from what actually fired, so the explanation is grounded in the right policy text."""
    p = result["product"]
    fired = " ".join(r["name"] for r in result["rules"] if r["status"] != "SUITABLE")
    q = f"{p['product_type']} product how it works main risks barrier plain language {fired} repair guidance"
    chunks = get_kb().search(q, k=k)
    kb = get_kb()
    # always include the policy chunk(s) for fired rules
    have = {c["id"] for c in chunks}
    for c in kb.search(f"suitability policy {fired}", k=2, docs=["suitability_policy"]):
        if c["id"] not in have:
            chunks.append(c)
    return chunks
