"""Orchestrator API: the only service the dashboard talks to."""

import asyncio
import json
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel

from . import workflow
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


app = FastAPI(title="Poprire Agent – Orchestrator", version="0.1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


def get_case(case_id: str) -> Case:
    case = store.get(case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Caz inexistent")
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
        raise HTTPException(status_code=400, detail="Fișier gol")
    case = store.create(kind="DOCUMENT", title=file.filename or "document.pdf", document_name=file.filename, document_bytes=data)
    workflow.enqueue_start(case)
    return case.summary_dict()


class SampleIn(BaseModel):
    file: str


@app.post("/cases/from-sample", status_code=201)
async def case_from_sample(body: SampleIn):
    path = (SAMPLES_DIR / body.file).resolve()
    if path.parent != SAMPLES_DIR.resolve() or not path.is_file():
        raise HTTPException(status_code=404, detail="Document de test inexistent")
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
        raise HTTPException(status_code=404, detail="Cazul nu are document")
    return Response(case.document_bytes, media_type="application/pdf")


@app.get("/cases/{case_id}/response.pdf")
def case_response(case_id: str):
    case = get_case(case_id)
    if not case.response_pdf:
        raise HTTPException(status_code=404, detail="Răspunsul nu a fost generat")
    return Response(case.response_pdf, media_type="application/pdf")


class ReviewIn(BaseModel):
    answer: str


@app.post("/cases/{case_id}/review")
async def answer_review(case_id: str, body: ReviewIn):
    case = get_case(case_id)
    if case.status != "NECESITA_OPERATOR" or not case.review:
        raise HTTPException(status_code=409, detail="Cazul nu așteaptă răspunsul unui operator")
    if not body.answer.strip():
        raise HTTPException(status_code=400, detail="Răspuns gol")
    workflow.set_status(case, "IN_ASTEPTARE")
    workflow.enqueue_resume(case, body.answer.strip())
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
    case = store.create(kind="EVENIMENT", title=f"Încasare {body.amount:g} {body.currency} – {body.client_id}",
                        trigger=body.model_dump())
    case.blackboard["eveniment"] = body.model_dump()
    case.blackboard["identificare"] = {"status": "IDENTIFICAT", "client_id": body.client_id, "candidati": [],
                                       "cnp_corectat": None, "incredere": 1.0,
                                       "motivare": "Client cunoscut din evenimentul core banking."}
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
        raise HTTPException(status_code=404, detail="Document inexistent")
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
    source: str = "SALARIU"
    description: str = "Încasare simulată (demo)"


@app.post("/demo/incoming")
async def demo_incoming(body: IncomingIn):
    return await proxy(core.simulate_incoming(body.model_dump()))


@app.post("/demo/reset")
async def demo_reset():
    await proxy(core.reset())
    store.clear()
    return {"status": "reset"}


@app.get("/demo/rules")
async def demo_rules():
    return await proxy(rules.rules())
