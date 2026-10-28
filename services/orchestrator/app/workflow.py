"""Case queue and worker. Cases are processed one at a time so two cases can never race on the same accounts."""

import asyncio
import logging

from .agents import start_message, supervisor
from .runtime import PauseForHuman
from .store import Case, emit, store

log = logging.getLogger("orchestrator")
queue: asyncio.Queue[tuple[str, str, str | None]] = asyncio.Queue()


def set_status(case: Case, status: str):
    case.status = status
    emit(case, "Sistem", "status", status=status)


def enqueue_start(case: Case):
    emit(case, "Sistem", "case_created", kind=case.kind, title=case.title)
    queue.put_nowait((case.id, "start", None))


def enqueue_resume(case: Case, answer: str):
    queue.put_nowait((case.id, "resume", answer))


async def _process(case: Case, action: str, answer: str | None):
    if action == "start":
        case.messages = [{"role": "user", "content": start_message(case)}]
    else:
        review = case.review or {}
        emit(case, "Operator", "review_answered", answer=answer)
        results = case.pending_tool_results + [{"type": "tool_result", "tool_use_id": review["tool_use_id"],
                                                "content": f"Răspunsul operatorului uman: {answer}"}]
        case.pending_tool_results = []
        case.review = None
        case.messages.append({"role": "user", "content": results})
    return await supervisor.loop(case, case.messages)


async def worker():
    while True:
        case_id, action, answer = await queue.get()
        case = store.get(case_id)
        if case is None:  # store was reset while the case was queued
            queue.task_done()
            continue
        set_status(case, "IN_LUCRU")
        try:
            result = await _process(case, action, answer)
            case.outcome, case.summary = result["rezultat"], result["rezumat"]
            emit(case, "Supervizor", "case_finished", outcome=case.outcome, summary=case.summary)
            set_status(case, "FINALIZAT")
        except PauseForHuman as p:
            case.review = {"question": p.question, "options": p.options, "context": p.context, "tool_use_id": p.tool_use_id}
            emit(case, "Supervizor", "review_requested", question=p.question, options=p.options, context=p.context)
            set_status(case, "NECESITA_OPERATOR")
        except Exception as e:
            log.exception("Case %s failed", case_id)
            emit(case, "Sistem", "error", message=f"{e.__class__.__name__}: {e}")
            set_status(case, "EROARE")
        finally:
            queue.task_done()
