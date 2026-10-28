"""Evaluation run: replays the golden scenario set end to end and scores the agents against the expected results.

Every scenario in scenarios.json carries an "eval" block (expected outcome, client, amount held and, where the case
needs a human, the scripted operator answer). The run resets the demo bank first so results are reproducible.
"""

import asyncio
import json
import logging
import time
from pathlib import Path

from . import workflow
from .config import settings
from .services import core
from .store import Case, now_iso, store

log = logging.getLogger("evaluation")
SCENARIOS_FILE = Path(settings.data_dir) / "scenarios.json"
SAMPLES_DIR = Path(settings.data_dir) / "popriri"
CASE_TIMEOUT_S = 8 * 60
MAX_OPERATOR_ANSWERS = 3
DEFAULT_OPERATOR_ANSWER = "Proceed with the option you recommend; the document was confirmed with the issuer through an official channel."

state: dict = {"status": "IDLE", "started_at": None, "finished_at": None, "items": [], "summary": None, "error": None}
_task: asyncio.Task | None = None


def is_running() -> bool:
    return state["status"] == "RUNNING"


def _held_for_new_order(case: Case) -> float:
    if not case.blackboard.get("registered_garnishment"):
        return 0.0
    plan = case.blackboard.get("allocation_plan") or {}
    new = next((g for g in plan.get("garnishments", []) if g["id"] == "NEW"), None)
    return float(new["allocated_ron"]) if new else 0.0


def _score(case: Case, expected: dict) -> list[dict]:
    checks = [{"name": "Outcome", "passed": case.outcome in expected["outcomes"],
               "expected": " or ".join(expected["outcomes"]), "actual": case.outcome or case.status}]
    if "client" in expected:
        ident = case.blackboard.get("identification") or {}
        actual = ident.get("client_id") if ident.get("status") == "IDENTIFIED" else None
        checks.append({"name": "Client", "passed": actual == expected["client"],
                       "expected": expected["client"] or "not a client", "actual": actual or "not a client"})
    if "held_ron" in expected:
        actual = _held_for_new_order(case)
        checks.append({"name": "Amount held", "passed": abs(actual - expected["held_ron"]) <= 1.0,
                       "expected": expected["held_ron"], "actual": round(actual, 2)})
    return checks


async def _run_case(item: dict, scenario: dict):
    case = store.create(kind="DOCUMENT", title=scenario["file"], document_name=scenario["file"],
                        document_bytes=(SAMPLES_DIR / scenario["file"]).read_bytes())
    item.update(case_id=case.id, status="RUNNING")
    workflow.enqueue_start(case)
    deadline = time.monotonic() + CASE_TIMEOUT_S
    while case.status not in ("DONE", "FAILED"):
        if time.monotonic() > deadline:
            item["status"] = "TIMEOUT"
            break
        # Act as the human operator when the case pauses, with the scenario's scripted answer
        if case.status == "NEEDS_REVIEW" and case.review and len(item["operator_questions"]) < MAX_OPERATOR_ANSWERS:
            answer = scenario["eval"].get("operator_answer") or DEFAULT_OPERATOR_ANSWER
            item["operator_questions"].append({"question": case.review["question"], "answer": answer})
            workflow.answer_review(case, answer)
        await asyncio.sleep(1.0)

    checks = _score(case, scenario["eval"])
    if item["status"] != "TIMEOUT":
        item["status"] = "ERROR" if case.status == "FAILED" else "PASS" if all(c["passed"] for c in checks) else "FAIL"
    item.update(checks=checks, outcome=case.outcome, processing_seconds=round(case.processing_seconds, 1),
                cost_usd=round(case.cost_usd, 4), llm_calls=case.usage["llm_calls"],
                operator_interventions=case.operator_interventions)


def summarize(items: list[dict]) -> dict:
    done = [i for i in items if i["status"] in ("PASS", "FAIL", "ERROR", "TIMEOUT")]
    n = len(done)
    if not n:
        return {"completed": 0, "total": len(items)}
    all_checks = [c for i in done for c in i["checks"]]
    outcome_checks = [c for c in all_checks if c["name"] == "Outcome"]
    return {
        "completed": n,
        "total": len(items),
        "scenarios_passed": sum(1 for i in done if i["status"] == "PASS"),
        "outcome_accuracy": sum(c["passed"] for c in outcome_checks) / len(outcome_checks),
        "checks_passed": sum(c["passed"] for c in all_checks),
        "checks_total": len(all_checks),
        "automation_rate": sum(1 for i in done if i.get("operator_interventions", 0) == 0) / n,
        "avg_processing_seconds": sum(i.get("processing_seconds", 0) for i in done) / n,
        "avg_cost_usd": sum(i.get("cost_usd", 0) for i in done) / n,
        "total_cost_usd": sum(i.get("cost_usd", 0) for i in done),
        "total_llm_calls": sum(i.get("llm_calls", 0) for i in done),
    }


async def _run():
    state.update(status="RUNNING", started_at=now_iso(), finished_at=None, items=[], summary=None, error=None)
    try:
        await core.reset()
        store.clear()
        scenarios = [s for s in json.loads(SCENARIOS_FILE.read_text(encoding="utf-8")) if s.get("eval")]
        state["items"] = [{"file": s["file"], "title": s["title"], "expected": s["eval"], "status": "PENDING",
                           "case_id": None, "checks": [], "operator_questions": []} for s in scenarios]
        for item, scenario in zip(state["items"], scenarios):
            await _run_case(item, scenario)
            state["summary"] = summarize(state["items"])
        state["status"] = "DONE"
    except Exception as e:  # keep partial results visible
        log.exception("Evaluation failed")
        state.update(status="FAILED", error=f"{e.__class__.__name__}: {e}")
    finally:
        state["finished_at"] = now_iso()
        state["summary"] = summarize(state["items"])


def start():
    global _task
    _task = asyncio.create_task(_run())
