"""Deterministic allocation of a debtor's funds across active garnishments.

Model (per account, everything converted to RON):
  protected(type) = exempt inflows + (1 - income_fraction(type)) * periodic income inflows
  cap(type)       = max(0, balance - protected(type))
Garnishments are served in order of rank, then received date. Caps are cumulative: a lower-ranked
claim with a stricter limit only gets what is left under its own cap after higher-ranked claims.
"""

from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal

from pydantic import BaseModel, Field

from .legal_config import CLAIM_TYPES, DISCLAIMER, EXEMPT_SOURCES, INCOME_SOURCES

CENT = Decimal("0.01")


def money(x) -> Decimal:
    return Decimal(str(x)).quantize(CENT, rounding=ROUND_DOWN)


class AccountIn(BaseModel):
    iban: str
    currency: str = "RON"
    balance: float
    fx_to_ron: float = 1.0
    status: str = "ACTIVE"
    inflows: dict[str, float] = Field(default_factory=dict, description="credits in the protection window, by source")


class GarnishmentIn(BaseModel):
    id: str
    claim_type: str
    amount_ron: float
    received_at: str


class AllocationRequest(BaseModel):
    accounts: list[AccountIn]
    garnishments: list[GarnishmentIn]


def allocate(req: AllocationRequest) -> dict:
    explanation: list[str] = []
    for g in req.garnishments:
        if g.claim_type not in CLAIM_TYPES:
            raise ValueError(f"Tip de creanță necunoscut: {g.claim_type}. Valori permise: {', '.join(CLAIM_TYPES)}")

    active = [a for a in req.accounts if a.status == "ACTIVE"]
    for a in req.accounts:
        if a.status != "ACTIVE":
            explanation.append(f"Contul {a.iban} are statusul {a.status} și este ignorat.")
    active.sort(key=lambda a: (a.currency != "RON", -a.balance * a.fx_to_ron))

    analyses = []
    for a in active:
        fx = Decimal(str(a.fx_to_ron))
        balance_ron = money(Decimal(str(a.balance)) * fx)
        exempt = money(sum((Decimal(str(v)) for s, v in a.inflows.items() if s in EXEMPT_SOURCES), Decimal(0)) * fx)
        income = money(sum((Decimal(str(v)) for s, v in a.inflows.items() if s in INCOME_SOURCES), Decimal(0)) * fx)
        caps = {}
        for ct, cfg in CLAIM_TYPES.items():
            protected = (exempt + (1 - cfg["income_fraction"]) * income).quantize(CENT, rounding=ROUND_HALF_UP)
            caps[ct] = max(Decimal(0), balance_ron - min(balance_ron, protected))
        analyses.append({"iban": a.iban, "currency": a.currency, "fx_to_ron": fx, "balance_ron": balance_ron,
                         "exempt_ron": exempt, "income_ron": income, "caps": caps})
        line = f"Cont {a.iban} ({a.currency}): sold {balance_ron} RON"
        if a.currency != "RON":
            line += f" (curs {fx} RON/{a.currency})"
        if exempt:
            line += f"; sume exceptate (alocații/ajutoare) {exempt} RON protejate integral"
        if income:
            line += f"; venituri periodice (salariu/pensie) {income} RON, din care se poate urmări doar o fracție"
        explanation.append(line + ".")

    used = {an["iban"]: Decimal(0) for an in analyses}
    holds: list[dict] = []
    results: list[dict] = []
    ordered = sorted(req.garnishments, key=lambda g: (CLAIM_TYPES[g.claim_type]["rank"], g.received_at))
    for g in ordered:
        cfg = CLAIM_TYPES[g.claim_type]
        need = money(g.amount_ron)
        allocated = Decimal(0)
        for an in analyses:
            room = an["caps"][g.claim_type] - used[an["iban"]]
            take = min(need - allocated, room)
            if take <= 0:
                continue
            used[an["iban"]] += take
            allocated += take
            amount_orig = (take / an["fx_to_ron"]).quantize(CENT, rounding=ROUND_DOWN)
            holds.append({"iban": an["iban"], "garnishment_id": g.id, "currency": an["currency"],
                          "amount": float(amount_orig), "amount_ron": float(take)})
            if allocated >= need:
                break
        remaining = need - allocated
        results.append({"id": g.id, "claim_type": g.claim_type, "claim_label": cfg["label"], "rank": cfg["rank"],
                        "requested_ron": float(need), "allocated_ron": float(allocated), "remaining_ron": float(remaining),
                        "fully_covered": remaining <= 0, "legal_basis": cfg["legal_basis"]})
        status = "acoperită integral" if remaining <= 0 else f"acoperită parțial, rămân {remaining} RON (poprirea rămâne activă pe încasări viitoare)"
        explanation.append(
            f"Poprirea {g.id} ({cfg['label']}, rang {cfg['rank']}, max. {round(cfg['income_fraction'] * 100)}% din venituri periodice): "
            f"solicitat {need} RON, alocat {allocated} RON – {status}.")

    return {
        "holds": holds,
        "garnishments": results,
        "accounts": [{**{k: v for k, v in an.items() if k not in ("caps", "fx_to_ron")},
                      "fx_to_ron": float(an["fx_to_ron"]), "balance_ron": float(an["balance_ron"]),
                      "exempt_ron": float(an["exempt_ron"]), "income_ron": float(an["income_ron"]),
                      "caps_ron": {k: float(v) for k, v in an["caps"].items()}} for an in analyses],
        "total_blocked_ron": float(sum(used.values(), Decimal(0))),
        "explanation": explanation,
        "disclaimer": DISCLAIMER,
    }
