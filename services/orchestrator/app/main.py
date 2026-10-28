"""Orchestrator API: the only service the dashboard talks to."""

import asyncio
import json
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel

from . import evaluation, workflow
from .config import settings
from .services import ServiceError, core, rules
from .store import Case, store

SAMPLES_DIR = Path(settings.data_dir) / "popriri"
SCENARIOS_FILE = Path(settings.data_dir) / "scenarios.json"


@asynccontextmanager
async def lifespan(_: FastAPI):
    task = asyncio.create_task(workflow.worker())
    yield
    task.cancel()


app = FastAPI(title="Garnishment Agent - Orchestrator", version="0.1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


def get_case(case_id: str) -> Case:
    case = store.get(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    return case


async def proxy(coro):
    try:
        return await coro
    except ServiceError as e:
        raise HTTPException(status_code=e.status, detail=e.detail)


@app.get("/health")
def health():
    return {"status": "ok", "model": settings.llm_model, "region": settings.aws_region}


# ---------------------------------------------------------------- cases

@app.get("/cases")
def list_cases():
    return [c.summary_dict() for c in store.all()]


@app.post("/cases", status_code=201)
async def upload_case(file: UploadFile = File(...)):
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty file")
    case = store.create(kind="DOCUMENT", title=file.filename or "document.pdf", document_name=file.filename, document_bytes=data)
    workflow.enqueue_start(case)
    return case.summary_dict()


class SampleIn(BaseModel):
    file: str


@app.post("/cases/from-sample", status_code=201)
async def case_from_sample(body: SampleIn):
    path = (SAMPLES_DIR / body.file).resolve()
    if path.parent != SAMPLES_DIR.resolve() or not path.is_file():
        raise HTTPException(status_code=404, detail="Sample document not found")
    case = store.create(kind="DOCUMENT", title=body.file, document_name=body.file, document_bytes=path.read_bytes())
    workflow.enqueue_start(case)
    return case.summary_dict()


@app.get("/cases/{case_id}")
def case_detail(case_id: str):
    return get_case(case_id).detail_dict()


@app.get("/cases/{case_id}/events")
def case_events(case_id: str):
    return get_case(case_id).events


@app.get("/cases/{case_id}/stream")
async def case_stream(case_id: str, request: Request):
    case = get_case(case_id)
    q: asyncio.Queue = asyncio.Queue()
    backlog = list(case.events)
    case.subscribers.append(q)  # no await between snapshot and subscribe -> no lost events

    async def gen():
        try:
            for ev in backlog:
                yield f"data: {json.dumps(ev, ensure_ascii=False, default=str)}\n\n"
            while not await request.is_disconnected():
                try:
                    ev = await asyncio.wait_for(q.get(), timeout=15)
                    yield f"data: {json.dumps(ev, ensure_ascii=False, default=str)}\n\n"
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
        finally:
            if q in case.subscribers:
                case.subscribers.remove(q)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.get("/cases/{case_id}/document")
def case_document(case_id: str):
    case = get_case(case_id)
    if not case.document_bytes:
        raise HTTPException(status_code=404, detail="The case has no document")
    return Response(case.document_bytes, media_type="application/pdf")


@app.get("/cases/{case_id}/response.pdf")
def case_response(case_id: str):
    case = get_case(case_id)
    if not case.response_pdf:
        raise HTTPException(status_code=404, detail="The reply letter has not been generated")
    return Response(case.response_pdf, media_type="application/pdf")


class ReviewIn(BaseModel):
    answer: str


@app.post("/cases/{case_id}/review")
async def answer_review(case_id: str, body: ReviewIn):
    case = get_case(case_id)
    if case.status != "NEEDS_REVIEW" or not case.review:
        raise HTTPException(status_code=409, detail="The case is not waiting for an operator")
    if not body.answer.strip():
        raise HTTPException(status_code=400, detail="Empty answer")
    workflow.answer_review(case, body.answer.strip())
    return case.summary_dict()


# ---------------------------------------------------------------- events from core banking

class FundsReceived(BaseModel):
    client_id: str
    iban: str
    amount: float
    currency: str
    source: str


@app.post("/webhooks/funds-received", status_code=202)
async def funds_received(body: FundsReceived):
    case = store.create(kind="EVENT", title=f"Incoming {body.amount:g} {body.currency} - {body.client_id}",
                        trigger=body.model_dump())
    case.blackboard["event"] = body.model_dump()
    case.blackboard["identification"] = {"status": "IDENTIFIED", "client_id": body.client_id, "candidates": [],
                                         "corrected_cnp": None, "confidence": 1.0,
                                         "reasoning": "Client known from the core banking event."}
    workflow.enqueue_start(case)
    return case.summary_dict()


# ---------------------------------------------------------------- demo helpers (proxied to services)

@app.get("/samples")
def samples():
    if not SCENARIOS_FILE.is_file():
        return []
    return json.loads(SCENARIOS_FILE.read_text(encoding="utf-8"))


@app.get("/samples/{name}")
def sample_pdf(name: str):
    path = (SAMPLES_DIR / name).resolve()
    if path.parent != SAMPLES_DIR.resolve() or not path.is_file():
        raise HTTPException(status_code=404, detail="Document not found")
    return Response(path.read_bytes(), media_type="application/pdf")


@app.get("/demo/clients")
async def demo_clients():
    return await proxy(core.clients())


@app.get("/demo/clients/{client_id}")
async def demo_client(client_id: str):
    snapshot = await proxy(core.snapshot(client_id))
    snapshot["garnishments"] = await proxy(core.garnishments(client_id))
    snapshot["holds"] = await proxy(core.holds(client_id))
    return snapshot


class IncomingIn(BaseModel):
    iban: str
    amount: float
    source: str = "SALARY"
    description: str = "Simulated credit (demo)"


@app.post("/demo/incoming")
async def demo_incoming(body: IncomingIn):
    return await proxy(core.simulate_incoming(body.model_dump()))


@app.post("/demo/reset")
async def demo_reset():
    if evaluation.is_running():
        raise HTTPException(status_code=409, detail="An evaluation is running; wait for it to finish")
    await proxy(core.reset())
    store.clear()
    return {"status": "reset"}


# ---------------------------------------------------------------- impact metrics and evaluation

@app.get("/metrics")
def metrics():
    """Live impact of the agents over the cases processed in this session."""
    cases = store.all()
    done = [c for c in cases if c.status == "DONE"]
    n = len(done)
    reviews = sum(c.operator_interventions for c in done)
    automated = sum(1 for c in done if c.operator_interventions == 0)
    return {
        "cases_done": n,
        "in_progress": sum(1 for c in cases if c.status in ("QUEUED", "RUNNING", "NEEDS_REVIEW")),
        "automated": automated,
        "automation_rate": automated / n if n else None,
        "avg_processing_seconds": sum(c.processing_seconds for c in done) / n if n else None,
        "avg_cost_usd": sum(c.cost_usd for c in done) / n if n else None,
        "total_cost_usd": sum(c.cost_usd for c in done),
        "manual_minutes_saved": max(0.0, n * settings.manual_minutes_per_case - reviews * settings.operator_minutes_per_review),
        "frauds_stopped": sum(1 for c in done if c.outcome == "SUSPECTED_FRAUD"),
        "assumptions": {
            "manual_minutes_per_case": settings.manual_minutes_per_case,
            "operator_minutes_per_review": settings.operator_minutes_per_review,
            "price_input_per_mtok": settings.price_input_per_mtok,
            "price_output_per_mtok": settings.price_output_per_mtok,
            "model": settings.llm_model,
        },
    }


@app.post("/eval/run", status_code=202)
async def eval_run():
    if evaluation.is_running():
        raise HTTPException(status_code=409, detail="An evaluation is already running")
    evaluation.start()
    return evaluation.state


@app.get("/eval/status")
def eval_status():
    return evaluation.state


@app.get("/demo/rules")
async def demo_rules():
    return await proxy(rules.rules())
