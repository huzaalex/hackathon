"""Simulated core banking system: clients, accounts, transactions, garnishments and holds.

It is the system of record and enforces its own safety checks (e.g. holds can never exceed the
balance), independently of what the AI agents decide.
"""

import json
import logging
import os
import time
import unicodedata
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

import httpx
from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from .db import Account, Base, Client, Garnishment, Hold, SessionLocal, Transaction, engine

log = logging.getLogger("core-banking")
SEED_PATH = Path(os.environ.get("SEED_PATH", "/data/seed.json"))
ORCHESTRATOR_URL = os.environ.get("ORCHESTRATOR_URL", "http://orchestrator:8000")
PROTECTION_WINDOW_DAYS = 30


# ---------------------------------------------------------------- setup

def wait_for_db(retries: int = 30):
    for _ in range(retries):
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return
        except Exception:
            time.sleep(1)
    raise RuntimeError("Database not reachable")


def load_seed(db: Session):
    seed = json.loads(SEED_PATH.read_text(encoding="utf-8"))
    db.add_all(Client(**c) for c in seed["clients"])
    db.flush()
    db.add_all(Account(**{**a, "balance": Decimal(str(a["balance"]))}) for a in seed["accounts"])
    db.flush()
    db.add_all(Transaction(**{**t, "amount": Decimal(str(t["amount"])), "booked_at": datetime.fromisoformat(t["booked_at"])})
               for t in seed["transactions"])
    for g in seed["garnishments"]:
        db.add(Garnishment(**{**g, "total_amount": Decimal(str(g["total_amount"])), "case_ref_norm": norm_ref(g["case_ref"]),
                              "received_at": datetime.fromisoformat(g["received_at"]), "transferred_amount": Decimal(0)}))
    db.flush()
    for h in seed["holds"]:
        db.add(Hold(iban=h["iban"], garnishment_id=h["garnishment_id"], amount=Decimal(str(h["amount"])),
                    amount_ron=Decimal(str(h["amount_ron"])), status="ACTIVE", created_at=datetime.now()))
    db.commit()


def reset_database():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        load_seed(db)


@asynccontextmanager
async def lifespan(_: FastAPI):
    wait_for_db()
    # Fresh, deterministic state on every start (the generator re-creates the seed each `docker compose up`)
    reset_database()
    yield


app = FastAPI(title="Core Banking (simulated)", version="0.1.0", lifespan=lifespan)


def get_db():
    with SessionLocal() as db:
        yield db


# ---------------------------------------------------------------- helpers

def norm_text(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    return "".join(c for c in s if not unicodedata.combining(c)).lower().strip()


def norm_ref(s: str) -> str:
    return "".join((s or "").split()).upper()


def f2(x) -> float:
    return float(x or 0)


def client_out(c: Client) -> dict:
    return {"id": c.id, "cnp": c.cnp, "first_name": c.first_name, "last_name": c.last_name,
            "full_name": f"{c.first_name} {c.last_name}", "birth_date": c.birth_date, "address": c.address}


def held_by_iban(db: Session, ibans: list[str]) -> dict[str, Decimal]:
    rows = db.execute(select(Hold.iban, func.sum(Hold.amount)).where(Hold.iban.in_(ibans), Hold.status == "ACTIVE")
                      .group_by(Hold.iban)).all()
    return {iban: amount for iban, amount in rows}


def garnishment_out(db: Session, g: Garnishment) -> dict:
    held_ron = db.scalar(select(func.sum(Hold.amount_ron)).where(Hold.garnishment_id == g.id, Hold.status == "ACTIVE"))
    return {"id": g.id, "client_id": g.client_id, "case_ref": g.case_ref, "issuer_type": g.issuer_type,
            "issuer_name": g.issuer_name, "creditor": g.creditor, "claim_type": g.claim_type,
            "total_amount": f2(g.total_amount), "transferred_amount": f2(g.transferred_amount),
            "remaining_amount": f2(g.total_amount - g.transferred_amount), "held_ron": f2(held_ron),
            "received_at": g.received_at.isoformat(), "status": g.status, "document_ref": g.document_ref}


def get_client_or_404(db: Session, client_id: str) -> Client:
    c = db.get(Client, client_id)
    if not c:
        raise HTTPException(status_code=404, detail=f"Client {client_id} not found")
    return c


# ---------------------------------------------------------------- clients

@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/clients")
def list_clients(db: Session = Depends(get_db)):
    clients = db.scalars(select(Client).order_by(Client.id)).all()
    accounts = db.scalars(select(Account)).all()
    by_client: dict[str, list] = {}
    for a in accounts:
        by_client.setdefault(a.client_id, []).append(
            {"iban": a.iban, "currency": a.currency, "product": a.product, "status": a.status, "balance": f2(a.balance)})
    return [{**client_out(c), "accounts": by_client.get(c.id, [])} for c in clients]


@app.get("/clients/search")
def search_clients(cnp: str | None = None, name: str | None = None, db: Session = Depends(get_db)):
    if not cnp and not name:
        raise HTTPException(status_code=400, detail="Provide cnp or name")
    if cnp:
        return [client_out(c) for c in db.scalars(select(Client).where(Client.cnp == cnp.strip())).all()]
    tokens = norm_text(name).split()
    found = []
    for c in db.scalars(select(Client)).all():
        full = norm_text(f"{c.first_name} {c.last_name}").split()
        if all(t in full for t in tokens):
            found.append(client_out(c))
    return found


class CnpList(BaseModel):
    cnps: list[str]


@app.post("/clients/search-by-cnps")
def search_by_cnps(body: CnpList, db: Session = Depends(get_db)):
    if not body.cnps:
        return []
    return [client_out(c) for c in db.scalars(select(Client).where(Client.cnp.in_(body.cnps))).all()]


@app.get("/clients/{client_id}")
def get_client(client_id: str, db: Session = Depends(get_db)):
    c = get_client_or_404(db, client_id)
    accounts = db.scalars(select(Account).where(Account.client_id == client_id)).all()
    return {**client_out(c), "accounts": [{"iban": a.iban, "currency": a.currency, "product": a.product,
                                           "status": a.status} for a in accounts]}


@app.get("/clients/{client_id}/snapshot")
def snapshot(client_id: str, days: int = PROTECTION_WINDOW_DAYS, db: Session = Depends(get_db)):
    """Accounts with balances, active holds and credits in the protection window grouped by source."""
    c = get_client_or_404(db, client_id)
    accounts = db.scalars(select(Account).where(Account.client_id == client_id)).all()
    ibans = [a.iban for a in accounts]
    held = held_by_iban(db, ibans)
    since = datetime.now() - timedelta(days=days)
    inflow_rows = db.execute(
        select(Transaction.iban, Transaction.source, func.sum(Transaction.amount))
        .where(Transaction.iban.in_(ibans), Transaction.direction == "CREDIT", Transaction.booked_at >= since)
        .group_by(Transaction.iban, Transaction.source)).all()
    inflows: dict[str, dict[str, float]] = {}
    for iban, source, amount in inflow_rows:
        inflows.setdefault(iban, {})[source] = f2(amount)
    return {
        "client": client_out(c),
        "window_days": days,
        "accounts": [{
            "iban": a.iban, "currency": a.currency, "product": a.product, "status": a.status,
            "balance": f2(a.balance), "held": f2(held.get(a.iban)), "available": f2(a.balance - held.get(a.iban, 0)),
            "inflows": inflows.get(a.iban, {}),
        } for a in accounts],
    }


@app.get("/clients/{client_id}/transactions")
def client_transactions(client_id: str, db: Session = Depends(get_db)):
    get_client_or_404(db, client_id)
    rows = db.scalars(select(Transaction).join(Account).where(Account.client_id == client_id)
                      .order_by(Transaction.booked_at.desc())).all()
    return [{"iban": t.iban, "booked_at": t.booked_at.isoformat(), "amount": f2(t.amount), "direction": t.direction,
             "source": t.source, "description": t.description} for t in rows]


# ---------------------------------------------------------------- garnishments

@app.get("/clients/{client_id}/garnishments")
def client_garnishments(client_id: str, status: str | None = None, db: Session = Depends(get_db)):
    get_client_or_404(db, client_id)
    q = select(Garnishment).where(Garnishment.client_id == client_id)
    if status:
        q = q.where(Garnishment.status == status)
    return [garnishment_out(db, g) for g in db.scalars(q.order_by(Garnishment.received_at)).all()]


@app.get("/garnishments")
def find_garnishments(case_ref: str, db: Session = Depends(get_db)):
    rows = db.scalars(select(Garnishment).where(Garnishment.case_ref_norm == norm_ref(case_ref))).all()
    return [garnishment_out(db, g) for g in rows]


class GarnishmentIn(BaseModel):
    client_id: str
    case_ref: str
    issuer_type: str
    issuer_name: str
    creditor: str
    claim_type: str
    total_amount: float
    document_ref: str | None = None


@app.post("/garnishments", status_code=201)
def create_garnishment(body: GarnishmentIn, db: Session = Depends(get_db)):
    get_client_or_404(db, body.client_id)
    dup = db.scalar(select(Garnishment).where(Garnishment.case_ref_norm == norm_ref(body.case_ref),
                                              Garnishment.client_id == body.client_id,
                                              Garnishment.status == "ACTIVE"))
    if dup:
        raise HTTPException(status_code=409, detail=f"An active garnishment {dup.id} already exists for case {dup.case_ref}")
    count = db.scalar(select(func.count()).select_from(Garnishment)) or 0
    g = Garnishment(id=f"GR-{count + 1:04d}", client_id=body.client_id, case_ref=body.case_ref,
                    case_ref_norm=norm_ref(body.case_ref), issuer_type=body.issuer_type, issuer_name=body.issuer_name,
                    creditor=body.creditor, claim_type=body.claim_type, total_amount=Decimal(str(body.total_amount)),
                    transferred_amount=Decimal(0), received_at=datetime.now(), status="ACTIVE", document_ref=body.document_ref)
    db.add(g)
    db.commit()
    return garnishment_out(db, g)


@app.post("/garnishments/{garnishment_id}/lift")
def lift_garnishment(garnishment_id: str, db: Session = Depends(get_db)):
    g = db.get(Garnishment, garnishment_id)
    if not g:
        raise HTTPException(status_code=404, detail=f"Garnishment {garnishment_id} not found")
    if g.status != "ACTIVE":
        raise HTTPException(status_code=409, detail=f"Garnishment {garnishment_id} has status {g.status}")
    released = []
    for h in db.scalars(select(Hold).where(Hold.garnishment_id == g.id, Hold.status == "ACTIVE")).all():
        h.status, h.released_at = "RELEASED", datetime.now()
        released.append({"iban": h.iban, "amount": f2(h.amount)})
    g.status = "LIFTED"
    db.commit()
    return {"garnishment": garnishment_out(db, g), "released_holds": released}


# ---------------------------------------------------------------- holds

@app.get("/clients/{client_id}/holds")
def client_holds(client_id: str, db: Session = Depends(get_db)):
    get_client_or_404(db, client_id)
    rows = db.scalars(select(Hold).join(Account).where(Account.client_id == client_id, Hold.status == "ACTIVE")).all()
    return [{"id": h.id, "iban": h.iban, "garnishment_id": h.garnishment_id, "amount": f2(h.amount),
             "amount_ron": f2(h.amount_ron), "created_at": h.created_at.isoformat()} for h in rows]


class HoldIn(BaseModel):
    iban: str
    garnishment_id: str
    amount: float
    amount_ron: float


class HoldPlan(BaseModel):
    holds: list[HoldIn]


@app.put("/clients/{client_id}/holds")
def replace_holds(client_id: str, plan: HoldPlan, db: Session = Depends(get_db)):
    """Atomically replaces all active holds of a client with a new allocation plan."""
    get_client_or_404(db, client_id)
    accounts = {a.iban: a for a in db.scalars(select(Account).where(Account.client_id == client_id)).all()}
    active_g = {g.id for g in db.scalars(select(Garnishment).where(Garnishment.client_id == client_id,
                                                                   Garnishment.status == "ACTIVE")).all()}
    per_iban: dict[str, Decimal] = {}
    for h in plan.holds:
        acc = accounts.get(h.iban)
        if not acc or acc.status != "ACTIVE":
            raise HTTPException(status_code=422, detail=f"Account {h.iban} does not belong to the client or is not active")
        if h.garnishment_id not in active_g:
            raise HTTPException(status_code=422, detail=f"Garnishment {h.garnishment_id} is not active for this client")
        if h.amount <= 0:
            raise HTTPException(status_code=422, detail="Held amounts must be positive")
        per_iban[h.iban] = per_iban.get(h.iban, Decimal(0)) + Decimal(str(h.amount))
    for iban, total in per_iban.items():
        if total > accounts[iban].balance:
            raise HTTPException(status_code=422, detail=f"A hold of {total} exceeds the balance of account {iban} ({accounts[iban].balance})")

    now = datetime.now()
    released = 0
    for h in db.scalars(select(Hold).where(Hold.iban.in_(list(accounts)), Hold.status == "ACTIVE")).all():
        h.status, h.released_at = "RELEASED", now
        released += 1
    for h in plan.holds:
        db.add(Hold(iban=h.iban, garnishment_id=h.garnishment_id, amount=Decimal(str(h.amount)),
                    amount_ron=Decimal(str(h.amount_ron)), status="ACTIVE", created_at=now))
    db.commit()
    return {"released": released, "created": len(plan.holds), "holds": client_holds(client_id, db)}


# ---------------------------------------------------------------- demo / simulation

class IncomingIn(BaseModel):
    iban: str
    amount: float
    source: str = "SALARY"
    description: str = "Simulated credit"


def notify_orchestrator(payload: dict):
    try:
        httpx.post(f"{ORCHESTRATOR_URL}/webhooks/funds-received", json=payload, timeout=5.0)
    except Exception as e:
        log.warning("Could not notify orchestrator: %s", e)


@app.post("/simulate/incoming")
def simulate_incoming(body: IncomingIn, background: BackgroundTasks, db: Session = Depends(get_db)):
    acc = db.get(Account, body.iban)
    if not acc or acc.status != "ACTIVE":
        raise HTTPException(status_code=404, detail="Account not found or inactive")
    if body.amount <= 0:
        raise HTTPException(status_code=422, detail="Amount must be positive")
    amount = Decimal(str(body.amount))
    db.add(Transaction(iban=acc.iban, booked_at=datetime.now(), amount=amount, direction="CREDIT",
                       source=body.source, description=body.description))
    acc.balance += amount
    db.commit()
    active = db.scalar(select(func.count()).select_from(Garnishment)
                       .where(Garnishment.client_id == acc.client_id, Garnishment.status == "ACTIVE")) or 0
    if active:
        background.add_task(notify_orchestrator, {"client_id": acc.client_id, "iban": acc.iban, "amount": body.amount,
                                                  "currency": acc.currency, "source": body.source})
    return {"iban": acc.iban, "new_balance": f2(acc.balance), "active_garnishments": active, "orchestrator_notified": bool(active)}


@app.post("/admin/reset")
def admin_reset():
    reset_database()
    return {"status": "reset"}
