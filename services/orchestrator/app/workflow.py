"""Case queue and worker. Cases are processed one at a time so two cases can never race on the same accounts."""

import asyncio
import logging
import time

from .agents import start_message, supervisor
from .runtime import PauseForHuman
from .store import Case, emit, now_iso, store

log = logging.getLogger("orchestrator")
queue: asyncio.Queue[tuple[str, str, str | None]] = asyncio.Queue()


def set_status(case: Case, status: str):
    case.status = status
    emit(case, "System", "status", status=status)


def enqueue_start(case: Case):
    emit(case, "System", "case_created", kind=case.kind, title=case.title)
    queue.put_nowait((case.id, "start", None))


def answer_review(case: Case, answer: str):
    """Records an operator decision and puts the paused case back in the queue."""
    case.operator_interventions += 1
    set_status(case, "QUEUED")
    queue.put_nowait((case.id, "resume", answer))


async def _process(case: Case, action: str, answer: str | None):
    if action == "start":
        case.messages = [{"role": "user", "content": start_message(case)}]
    else:
        review = case.review or {}
        emit(case, "Operator", "review_answered", answer=answer, text=answer)
        results = case.pending_tool_results + [{"type": "tool_result", "tool_use_id": review["tool_use_id"],
                                                "content": f"Answer from the human operator: {answer}"}]
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
        set_status(case, "RUNNING")
        started = time.monotonic()
        try:
            result = await _process(case, action, answer)
            case.outcome, case.summary = result["outcome"], result["summary"]
            case.processing_seconds += time.monotonic() - started
            case.finished_at = now_iso()
            emit(case, "Supervisor", "case_finished", outcome=case.outcome, summary=case.summary, text=case.summary)
            set_status(case, "DONE")
        except PauseForHuman as p:
            case.processing_seconds += time.monotonic() - started  # the operator's thinking time is not counted
            case.review = {"question": p.question, "options": p.options, "context": p.context, "tool_use_id": p.tool_use_id}
            emit(case, "Supervisor", "review_requested", question=p.question, options=p.options, context=p.context, text=p.question)
            set_status(case, "NEEDS_REVIEW")
        except Exception as e:
            log.exception("Case %s failed", case_id)
            case.processing_seconds += time.monotonic() - started
            case.finished_at = now_iso()
            emit(case, "System", "error", text=f"{e.__class__.__name__}: {e}")
            set_status(case, "FAILED")
        finally:
            queue.task_done()
