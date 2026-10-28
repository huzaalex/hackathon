"""Rules engine: deterministic legal computations. No LLM here, by design."""

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from . import cnp
from .allocation import AllocationRequest, allocate
from .legal_config import CLAIM_TYPES, DISCLAIMER, EXEMPT_SOURCES, INCOME_SOURCES, SAME_RANK_STRATEGY

app = FastAPI(title="Rules Engine", version="0.1.0")


class CnpIn(BaseModel):
    cnp: str


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/cnp/validate")
def validate_cnp(body: CnpIn):
    return cnp.validate(body.cnp)


@app.post("/cnp/suggest")
def suggest_cnp(body: CnpIn):
    return {"input": body.cnp, "candidates": cnp.suggest_corrections(body.cnp)}


@app.post("/allocate")
def allocate_funds(body: AllocationRequest):
    try:
        return allocate(body)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@app.get("/rules")
def rules():
    return {
        "claim_types": {k: {**v, "income_fraction": float(v["income_fraction"])} for k, v in CLAIM_TYPES.items()},
        "exempt_sources": EXEMPT_SOURCES,
        "income_sources": INCOME_SOURCES,
        "same_rank_strategy": SAME_RANK_STRATEGY,
        "disclaimer": DISCLAIMER,
    }
