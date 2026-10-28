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
            raise ValueError(f"Unknown claim type: {g.claim_type}. Allowed values: {', '.join(CLAIM_TYPES)}")

    active = [a for a in req.accounts if a.status == "ACTIVE"]
    for a in req.accounts:
        if a.status != "ACTIVE":
            explanation.append(f"Account {a.iban} has status {a.status} and is ignored.")
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
        line = f"Account {a.iban} ({a.currency}): balance {balance_ron} RON"
        if a.currency != "RON":
            line += f" (rate {fx} RON/{a.currency})"
        if exempt:
            line += f"; exempt credits (allowances/benefits) of {exempt} RON are fully protected"
        if income:
            line += f"; periodic income (salary/pension) of {income} RON, of which only a fraction can be garnished"
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
        status = "fully covered" if remaining <= 0 else f"partially covered, {remaining} RON outstanding (the garnishment stays active on future credits)"
        explanation.append(
            f"Garnishment {g.id} ({cfg['label']}, rank {cfg['rank']}, max {round(cfg['income_fraction'] * 100)}% of periodic income): "
            f"requested {need} RON, allocated {allocated} RON - {status}.")

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
