from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
from ..schemas import ProductSpec, CustomerProfile


@dataclass
class Session:
    id: str
    product: Optional[ProductSpec] = None
    customer: Optional[CustomerProfile] = None
    history: list = field(default_factory=list)       # [{"role","content"}] text-only turns
    cache: dict = field(default_factory=dict)         # assessment cache
    tool_outputs: list = field(default_factory=list)  # for numeric grounding


_SESSIONS: dict[str, Session] = {}


def get_session(sid: str) -> Session:
    return _SESSIONS.setdefault(sid, Session(sid))
