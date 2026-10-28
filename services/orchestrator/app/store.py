"""In-memory case store and live event bus (per-case subscribers for SSE)."""

import asyncio
import itertools
from dataclasses import dataclass, field
from datetime import datetime


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


@dataclass
class Case:
    id: str
    kind: str  # DOCUMENT | EVENIMENT
    title: str
    created_at: str = field(default_factory=now_iso)
    status: str = "IN_ASTEPTARE"  # IN_ASTEPTARE | IN_LUCRU | NECESITA_OPERATOR | FINALIZAT | EROARE
    document_name: str | None = None
    document_bytes: bytes | None = None
    trigger: dict | None = None
    # Shared state between agents ("blackboard"): each agent reads it and writes its own section
    blackboard: dict = field(default_factory=dict)
    events: list[dict] = field(default_factory=list)
    outcome: str | None = None
    summary: str | None = None
    response_pdf: bytes | None = None
    review: dict | None = None
    # Supervisor conversation, kept append-only so the case can pause for a human and resume
    messages: list = field(default_factory=list)
    pending_tool_results: list = field(default_factory=list)
    usage: dict = field(default_factory=lambda: {"llm_calls": 0, "input_tokens": 0, "output_tokens": 0})
    subscribers: list[asyncio.Queue] = field(default_factory=list, repr=False)

    def summary_dict(self) -> dict:
        return {"id": self.id, "kind": self.kind, "title": self.title, "created_at": self.created_at,
                "status": self.status, "outcome": self.outcome, "document_name": self.document_name,
                "client_id": (self.blackboard.get("identificare") or {}).get("client_id")}

    def detail_dict(self) -> dict:
        return {**self.summary_dict(), "summary": self.summary, "blackboard": self.blackboard, "review": self.review,
                "trigger": self.trigger, "has_response_pdf": self.response_pdf is not None,
                "has_document": self.document_bytes is not None, "usage": self.usage, "events_count": len(self.events)}


class CaseStore:
    def __init__(self):
        self.cases: dict[str, Case] = {}
        self._seq = itertools.count(1)

    def create(self, **kwargs) -> Case:
        case = Case(id=f"CAZ-{next(self._seq):04d}", **kwargs)
        self.cases[case.id] = case
        return case

    def get(self, case_id: str) -> Case | None:
        return self.cases.get(case_id)

    def all(self) -> list[Case]:
        return sorted(self.cases.values(), key=lambda c: c.id, reverse=True)

    def clear(self):
        self.cases.clear()
        self._seq = itertools.count(1)


store = CaseStore()


def emit(case: Case, agent: str, type_: str, **data):
    ev = {"seq": len(case.events) + 1, "ts": now_iso(), "agent": agent, "type": type_, "data": data}
    case.events.append(ev)
    for q in list(case.subscribers):
        q.put_nowait(ev)
    return ev
