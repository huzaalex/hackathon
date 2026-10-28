"""Agent team: a supervisor that plans the case and four specialised sub-agents.

Data flows through the case blackboard, never through the LLM copying numbers around:
tools read inputs from the blackboard and write their outputs back to it.
"""

import json
from datetime import datetime

from .config import settings
from .runtime import Agent, AgentError, PauseForHuman, Tool, ToolError
from .services import core, docs, fx, rules
from .store import Case, emit

CLAIM_TYPES = ["CHILD_SUPPORT", "WAGE", "TAX", "UNSECURED"]
NULLABLE_STR = {"type": ["string", "null"]}

LANGUAGE_RULE = ("Write everything (reasoning, messages, instructions, results) in clear English. "
                 "Source documents are in Romanian: copy names, addresses and reference numbers exactly as written, "
                 "but describe them in English. Never use emojis.")

CLAIM_LABEL = {"CHILD_SUPPORT": "child support", "WAGE": "wage claim", "TAX": "tax claim", "UNSECURED": "other (unsecured) claim",
               "UNKNOWN": "unknown claim type"}
DOC_TYPE_LABEL = {"GARNISHMENT_ORDER": "Garnishment order", "GARNISHMENT_RELEASE": "Garnishment release",
                  "OTHER_DOCUMENT": "Other document"}
DECISION_LABEL = {"APPLY_GARNISHMENT": "apply the garnishment", "DUPLICATE": "duplicate, do nothing", "RELEASE": "release the garnishment",
                  "REEVALUATE": "re-evaluate the holds", "NO_ACCOUNTS": "no accounts to garnish",
                  "NEEDS_OPERATOR": "needs a human operator"}
LETTER_LABEL = {"GARNISHMENT_CONFIRMATION": "garnishment confirmation", "NO_ACCOUNTS": "debtor has no accounts",
                "RELEASE_CONFIRMATION": "release confirmation", "DUPLICATE_NOTICE": "duplicate notice"}


def money(x, currency="RON") -> str:
    return f"{x:,.2f} {currency}" if isinstance(x, (int, float)) else "-"


def pct(x) -> str:
    return f"{round(x * 100)}%" if isinstance(x, (int, float)) else "-"


def bb(case: Case, key: str, required: str | None = None):
    value = case.blackboard.get(key)
    if value is None and required:
        raise ToolError(required)
    return value


def client_id_of(case: Case) -> str:
    ident = bb(case, "identification", "The client has not been identified yet (run the identification agent first).")
    if ident.get("status") != "IDENTIFIED" or not ident.get("client_id"):
        raise ToolError(f"Identification is not final (status {ident.get('status')}).")
    return ident["client_id"]


def blackboard_view(case: Case) -> str:
    view = {k: v for k, v in case.blackboard.items() if k != "text_extraction"}
    return json.dumps(view, ensure_ascii=False, indent=2, default=str)


def schema(properties: dict, required: list[str] | None = None) -> dict:
    return {"type": "object", "properties": properties, "required": required or list(properties), "additionalProperties": False}


def clients_found(result) -> str:
    if not result:
        return "No matching client found."
    return f"Found {len(result)} client(s): " + "; ".join(f"{c['id']} {c['full_name']}, {c['address']}" for c in result)


NO_INPUT = schema({}, [])


# ====================================================================== Reader agent

async def t_read_document(case: Case, _):
    if not case.document_bytes:
        raise ToolError("The case has no document attached.")
    r = await docs.extract(case.document_name or "document.pdf", case.document_bytes)
    case.blackboard["text_extraction"] = {"pages": r["pages"], "text_layer": r["has_text_layer"]}
    if r["has_text_layer"]:
        return f"PDF document with {r['pages']} page(s), text layer present.\n\n{r['text']}"
    if not r["page_images_png_b64"]:
        raise ToolError("The document has no text and could not be rendered as an image.")
    blocks = [{"type": "text", "text": f"The document has NO text layer (it looks scanned, {r['pages']} page(s)). "
                                       "The page images follow: read them visually, paying close attention to digits."}]
    blocks += [{"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": b64}}
               for b64 in r["page_images_png_b64"]]
    return blocks


async def t_validate_cnp(_case: Case, inp):
    return await rules.validate_cnp(inp["cnp"])


def summarize_cnp(r) -> str:
    if r.get("valid"):
        return f"The CNP is valid (born {r.get('birth_date')}, {r.get('county')})."
    return "The CNP is invalid: " + "; ".join(r.get("errors") or ["unknown reason"]) + "."


def describe_document(d: dict) -> str:
    parts = [f"{DOC_TYPE_LABEL.get(d.get('document_type'), 'Document')} from {d.get('issuer_name') or 'an unknown issuer'}."]
    debtor = d.get("debtor_name") or "unknown"
    cnp = d.get("debtor_cnp")
    parts.append(f"Debtor: {debtor}" + (f", CNP {cnp}" + (" (invalid)" if d.get("cnp_valid") is False else "") if cnp else ", no readable CNP") + ".")
    if d.get("amount"):
        parts.append(f"Amount: {money(d['amount'], d.get('currency') or 'RON')}.")
    if d.get("case_number"):
        parts.append(f"Case number {d['case_number']}.")
    parts.append(f"Claim type: {CLAIM_LABEL.get(d.get('claim_type'), d.get('claim_type'))}. Confidence {pct(d.get('confidence'))}.")
    if d.get("issues"):
        parts.append("Issues: " + "; ".join(d["issues"]))
    return " ".join(parts)


EXTRACTION_SCHEMA = schema({
    "document_type": {"type": "string", "enum": ["GARNISHMENT_ORDER", "GARNISHMENT_RELEASE", "OTHER_DOCUMENT"]},
    "issuer_type": {"type": "string", "enum": ["BAILIFF", "TAX_AUTHORITY", "LOCAL_TAX_AUTHORITY", "OTHER"]},
    "issuer_name": {"type": "string"},
    "case_number": {**NULLABLE_STR, "description": "enforcement case / tax file number"},
    "registration_number": {**NULLABLE_STR, "description": "number of the letter itself"},
    "debtor_name": NULLABLE_STR,
    "debtor_cnp": {**NULLABLE_STR, "description": "exactly as written; null if missing or unreadable"},
    "debtor_address": NULLABLE_STR,
    "creditor": NULLABLE_STR,
    "amount": {"type": ["number", "null"]},
    "currency": {"type": "string"},
    "claim_type": {"type": "string", "enum": CLAIM_TYPES + ["UNKNOWN"]},
    "claim_description": {**NULLABLE_STR, "description": "short description in English"},
    "payment_iban": NULLABLE_STR,
    "released_reference": {**NULLABLE_STR, "description": "for releases only: the garnishment/letter being released"},
    "cnp_valid": {"type": ["boolean", "null"]},
    "confidence": {"type": "number", "description": "between 0 and 1"},
    "issues": {"type": "array", "items": {"type": "string"}, "description": "in English"},
})

reader = Agent(
    key="document", label="Reader Agent", effort=settings.llm_subagent_effort, result_schema=EXTRACTION_SCHEMA,
    describe_result=describe_document,
    system=f"""You are the READER AGENT of the enforcement department of {settings.bank_name}, a Romanian bank.
You receive an official letter sent to the bank: a garnishment order (adresă de înființare a popririi),
a garnishment release (adresă de ridicare a popririi) or some other document.

- Use read_document. If the document is scanned you will receive page images: read them visually.
- Extract the fields exactly as they appear. Never fill in missing or unreadable data: use null and describe the
  problem in "issues".
- Validate the CNP (Romanian personal numeric code) with validate_cnp and set cnp_valid. Do not correct the CNP yourself.
- Classify the claim:
  CHILD_SUPPORT = child support / maintenance (pensie de întreținere, pensie alimentară);
  WAGE = wages owed by the debtor; TAX = ANAF, local taxes and other budget claims;
  UNSECURED = any other debt (invoices, loans, contracts); UNKNOWN = cannot be determined.
- "confidence" reflects how sure you are about the critical fields (debtor, CNP, amount, case number).
{LANGUAGE_RULE}
Finish by calling submit_result.""",
    tools=[
        Tool("read_document", "Extract the text of the received document (or the page images if it is scanned).", NO_INPUT,
             t_read_document, describe=lambda _: "Reading the received document.",
             summarize=lambda r: ("Extracted the text layer of the PDF." if isinstance(r, str)
                                  else "No text layer found (scanned document); reading the page images visually.")),
        Tool("validate_cnp", "Validate a CNP (structure, birth date, county, check digit).",
             schema({"cnp": {"type": "string"}}), t_validate_cnp,
             describe=lambda i: f"Validating CNP {i.get('cnp')}.", summarize=summarize_cnp),
    ],
)


# ====================================================================== Identification agent

async def t_search_cnp(_c, inp):
    return await core.search_cnp(inp["cnp"])


async def t_suggest_cnp(_c, inp):
    return await rules.suggest_cnp(inp["cnp"])


async def t_search_cnps(_c, inp):
    return await core.search_cnps(inp["cnps"])


async def t_search_name(_c, inp):
    return await core.search_name(inp["name"])


async def t_client_details(_c, inp):
    client = await core.client(inp["client_id"])
    client["decoded_cnp"] = await rules.validate_cnp(client["cnp"])
    return client


def describe_identification(r: dict) -> str:
    status = r.get("status")
    if status == "IDENTIFIED":
        text = f"Debtor identified as client {r.get('client_id')} (confidence {pct(r.get('confidence'))})."
        if r.get("corrected_cnp"):
            text += f" Corrected CNP: {r['corrected_cnp']}."
    elif status == "AMBIGUOUS":
        ids = ", ".join(c["client_id"] for c in r.get("candidates", []))
        text = f"Ambiguous: {len(r.get('candidates', []))} possible clients ({ids})."
    else:
        text = "The debtor is not a client of the bank."
    return f"{text} {r.get('reasoning', '')}".strip()


IDENTIFICATION_SCHEMA = schema({
    "status": {"type": "string", "enum": ["IDENTIFIED", "AMBIGUOUS", "NOT_FOUND"]},
    "client_id": NULLABLE_STR,
    "candidates": {"type": "array", "items": schema({"client_id": {"type": "string"}, "reason": {"type": "string"}})},
    "corrected_cnp": {**NULLABLE_STR, "description": "the correct CNP, if the one in the document was wrong"},
    "confidence": {"type": "number"},
    "reasoning": {"type": "string"},
})

identification = Agent(
    key="identification", label="Identification Agent", effort=settings.llm_subagent_effort, result_schema=IDENTIFICATION_SCHEMA,
    describe_result=describe_identification,
    system=f"""You are the IDENTIFICATION AGENT. You determine whether the debtor in the document is a client of the bank, and which one.

Strategy (adapt it to the situation, do not follow it mechanically):
1. Valid CNP: search_by_cnp and confirm the name matches.
2. Invalid CNP (wrong check digit): suggest_cnp_corrections, then search_by_cnp_list with the candidates;
   accept only a candidate whose name and address match the document.
3. No CNP or no result: search_by_name, then compare address and birth date (client_details).

Rules: never guess. Several plausible candidates: AMBIGUOUS, listing the candidates and what tells them apart.
Nobody matches: NOT_FOUND. If the supervisor passes on a confirmation from the human operator, verify the
confirmed client with client_details and report IDENTIFIED.
{LANGUAGE_RULE}
Finish by calling submit_result.""",
    tools=[
        Tool("search_by_cnp", "Search the client by exact CNP.", schema({"cnp": {"type": "string"}}), t_search_cnp,
             describe=lambda i: f"Searching clients by CNP {i.get('cnp')}.", summarize=clients_found),
        Tool("validate_cnp", "Validate a CNP.", schema({"cnp": {"type": "string"}}), t_validate_cnp,
             describe=lambda i: f"Validating CNP {i.get('cnp')}.", summarize=summarize_cnp),
        Tool("suggest_cnp_corrections", "Generate valid CNPs that differ by a single digit or two swapped adjacent digits.",
             schema({"cnp": {"type": "string"}}), t_suggest_cnp,
             describe=lambda i: f"Generating possible corrections for CNP {i.get('cnp')}.",
             summarize=lambda r: f"Found {len(r['candidates'])} valid CNP(s) that differ by one digit or one swap."),
        Tool("search_by_cnp_list", "Search clients for a list of CNPs.",
             schema({"cnps": {"type": "array", "items": {"type": "string"}}}), t_search_cnps,
             describe=lambda i: f"Searching clients for {len(i.get('cnps', []))} candidate CNP(s).", summarize=clients_found),
        Tool("search_by_name", "Search clients by name (diacritics and word order do not matter).",
             schema({"name": {"type": "string"}}), t_search_name,
             describe=lambda i: f"Searching clients by name \"{i.get('name')}\".", summarize=clients_found),
        Tool("client_details", "Client details (address, accounts, decoded CNP).",
             schema({"client_id": {"type": "string"}}), t_client_details,
             describe=lambda i: f"Loading the details of client {i.get('client_id')}.",
             summarize=lambda c: f"{c['full_name']}, born {c['birth_date']}, {c['address']}; {len(c['accounts'])} account(s)."),
    ],
)


# ====================================================================== Legal agent

async def t_check_duplicate(case: Case, _):
    doc = bb(case, "document", "The document has not been read yet.")
    if not doc.get("case_number"):
        raise ToolError("The document has no case number; the duplicate check is not possible.")
    found = await core.garnishments_by_case(doc["case_number"])
    cid = (case.blackboard.get("identification") or {}).get("client_id")
    return {"case_number": doc["case_number"], "garnishments_found": found,
            "active_duplicates_same_client": [g["id"] for g in found if g["client_id"] == cid and g["status"] == "ACTIVE"]}


def summarize_duplicate(r) -> str:
    if r["active_duplicates_same_client"]:
        return f"Already registered and active for this client: {', '.join(r['active_duplicates_same_client'])}."
    if r["garnishments_found"]:
        return f"Case number found {len(r['garnishments_found'])} time(s), but not as an active garnishment of this client."
    return "No existing garnishment with this case number."


async def t_financial_snapshot(case: Case, _):
    return await core.snapshot(client_id_of(case))


def summarize_snapshot(s) -> str:
    parts = []
    for a in s["accounts"]:
        line = f"{a['product']} ({a['status'].lower()}): balance {money(a['balance'], a['currency'])}"
        if a["held"]:
            line += f", already held {money(a['held'], a['currency'])}"
        if a["inflows"]:
            line += ", recent credits: " + ", ".join(f"{k.lower().replace('_', ' ')} {money(v, a['currency'])}" for k, v in a["inflows"].items())
        parts.append(line)
    return f"{len(s['accounts'])} account(s). " + "; ".join(parts) + "."


async def t_active_garnishments(case: Case, _):
    return await core.garnishments(client_id_of(case), status="ACTIVE")


def summarize_garnishments(gs) -> str:
    if not gs:
        return "No other active garnishments."
    return "Active: " + "; ".join(f"{g['id']} ({CLAIM_LABEL.get(g['claim_type'], g['claim_type'])}, {money(g['remaining_amount'])}, "
                                  f"from {g['issuer_name']})" for g in gs) + "."


async def t_fx(_c, _):
    return await fx.rates()


async def t_find_to_release(case: Case, _):
    doc = bb(case, "document", "The document has not been read yet.")
    cid = client_id_of(case)
    refs = [r for r in (doc.get("case_number"), doc.get("released_reference")) if r]
    found = {}
    for ref in refs:
        for g in await core.garnishments_by_case(ref):
            found[g["id"]] = g
    return {"searched_for": refs, "garnishments": list(found.values()),
            "active_for_this_client": [g["id"] for g in found.values() if g["client_id"] == cid and g["status"] == "ACTIVE"]}


async def t_allocate(case: Case, inp):
    cid = client_id_of(case)
    snap = await core.snapshot(cid)
    fx_data = await fx.rates()
    rates = fx_data["rates"]
    accounts, notes = [], []
    for a in snap["accounts"]:
        rate = 1.0 if a["currency"] == "RON" else rates.get(a["currency"])
        if rate is None:
            notes.append(f"Account {a['iban']} in {a['currency']} has no exchange rate and was excluded.")
            continue
        accounts.append({"iban": a["iban"], "currency": a["currency"], "balance": a["balance"], "fx_to_ron": rate,
                         "status": a["status"], "inflows": a["inflows"]})

    active = await core.garnishments(cid, status="ACTIVE")
    garnishments = [{"id": g["id"], "claim_type": g["claim_type"], "amount_ron": g["remaining_amount"],
                     "received_at": g["received_at"]} for g in active]

    include_new = inp.get("include_new_order", False) and not case.blackboard.get("registered_garnishment")
    claim_type = inp.get("claim_type")
    if include_new:
        doc = bb(case, "document", "The document has not been read yet.")
        if claim_type not in CLAIM_TYPES:
            raise ToolError(f"Specify claim_type for the new order (one of {CLAIM_TYPES}).")
        if not doc.get("amount"):
            raise ToolError("The document does not contain the amount to garnish.")
        currency = (doc.get("currency") or "RON").upper()
        rate = 1.0 if currency == "RON" else rates.get(currency)
        if rate is None:
            raise ToolError(f"No exchange rate for currency {currency}.")
        garnishments.append({"id": "NEW", "claim_type": claim_type, "amount_ron": round(doc["amount"] * rate, 2),
                             "received_at": datetime.now().isoformat()})

    if not accounts:
        raise ToolError("The client has no usable accounts.")
    plan = await rules.allocate(accounts, garnishments)
    plan["fx"] = {"date": fx_data.get("date"), "source": fx_data.get("source")}
    plan["notes"] = notes
    plan["includes_new_order"] = include_new
    plan["new_order_claim_type"] = claim_type if include_new else None
    case.blackboard["allocation_plan"] = plan
    return plan


def summarize_plan(p) -> str:
    lines = [f"Total to hold: {money(p['total_blocked_ron'])}."]
    for g in p["garnishments"]:
        name = "The new order" if g["id"] == "NEW" else g["id"]
        lines.append(f"{name}: {money(g['allocated_ron'])} of {money(g['requested_ron'])}"
                     + ("" if g["fully_covered"] else f" ({money(g['remaining_ron'])} outstanding)") + ".")
    return " ".join(lines)


def describe_allocate(i) -> str:
    if i.get("include_new_order"):
        return f"Running the rules engine to compute what can legally be held, including the new {CLAIM_LABEL.get(i.get('claim_type'), 'order')} order."
    return "Running the rules engine to re-evaluate the holds for the existing garnishments."


LEGAL_SCHEMA = schema({
    "decision": {"type": "string", "enum": ["APPLY_GARNISHMENT", "DUPLICATE", "RELEASE", "REEVALUATE", "NO_ACCOUNTS", "NEEDS_OPERATOR"]},
    "claim_type": {"type": ["string", "null"], "enum": CLAIM_TYPES + [None]},
    "garnishment_to_release": NULLABLE_STR,
    "duplicate_of": NULLABLE_STR,
    "summary": {"type": "string", "description": "plain-English explanation for the operator: what is protected, what is held and why"},
    "legal_basis": {"type": "array", "items": {"type": "string"}},
})

legal = Agent(
    key="legal", label="Legal Agent", effort=settings.llm_effort, result_schema=LEGAL_SCHEMA,
    describe_result=lambda r: f"Decision: {DECISION_LABEL.get(r.get('decision'), r.get('decision'))}. {r.get('summary', '')}",
    system=f"""You are the LEGAL AGENT. You decide what must legally be done for the identified client.
You do NOT compute amounts: you use compute_allocation, which calls a deterministic rules engine.

- Garnishment order: check_duplicate (case already active for the same client: DUPLICATE, no further calculation).
  Then financial_snapshot and active_garnishments for context. Confirm the claim type (you may correct the reader's
  classification if the text justifies it). Then compute_allocation(include_new_order=true, claim_type=...).
- Garnishment release: find_garnishment_to_release. If it belongs to the client and is active: RELEASE (with its id).
- Incoming payment event (no document): compute_allocation(include_new_order=false), then REEVALUATE.
- No active accounts: NO_ACCOUNTS. A situation you cannot classify: NEEDS_OPERATOR.

In "summary", explain in plain English for an operator: protected amounts (allowances, the protected share of the
salary), the ranking between creditors, and what remains uncovered. Use the explanations returned by the engine.
{LANGUAGE_RULE}
Finish by calling submit_result.""",
    tools=[
        Tool("check_duplicate", "Look for existing garnishments with the same case number.", NO_INPUT, t_check_duplicate,
             describe=lambda _: "Checking whether this case number is already registered.", summarize=summarize_duplicate),
        Tool("financial_snapshot", "The client's accounts: balance, amounts already held, credits of the last 30 days by source.",
             NO_INPUT, t_financial_snapshot,
             describe=lambda _: "Loading the client's accounts, balances and recent credits.", summarize=summarize_snapshot),
        Tool("active_garnishments", "Active garnishments already registered for the client.", NO_INPUT, t_active_garnishments,
             describe=lambda _: "Loading the client's active garnishments.", summarize=summarize_garnishments),
        Tool("exchange_rates", "Official exchange rates of the day.", NO_INPUT, t_fx,
             describe=lambda _: "Fetching the official exchange rates.",
             summarize=lambda r: f"1 EUR = {r['rates'].get('EUR')} RON on {r.get('date')} (source: {r.get('source')})."),
        Tool("find_garnishment_to_release", "Find the garnishment referenced by a release letter.", NO_INPUT, t_find_to_release,
             describe=lambda _: "Looking up the garnishment referenced by the release letter.",
             summarize=lambda r: (f"Matching active garnishment(s) of this client: {', '.join(r['active_for_this_client'])}."
                                  if r["active_for_this_client"] else "No matching active garnishment found for this client.")),
        Tool("compute_allocation",
             "Compute (deterministically) the hold plan for ALL active garnishments of the client, optionally plus the new one from the document.",
             schema({"include_new_order": {"type": "boolean"},
                     "claim_type": {"type": ["string", "null"], "enum": CLAIM_TYPES + [None]}}), t_allocate,
             describe=describe_allocate, summarize=summarize_plan),
    ],
)


# ====================================================================== Action agent

async def t_register(case: Case, _):
    if case.blackboard.get("registered_garnishment"):
        return {"already_registered": case.blackboard["registered_garnishment"]}
    doc = bb(case, "document", "The document has not been read yet.")
    decision = bb(case, "legal", "The legal agent has not decided yet.")
    if decision.get("decision") != "APPLY_GARNISHMENT":
        raise ToolError(f"The legal decision is {decision.get('decision')}, not APPLY_GARNISHMENT.")
    plan = bb(case, "allocation_plan", "No hold plan has been computed.")
    new = next((g for g in plan["garnishments"] if g["id"] == "NEW"), None)
    if new is None:
        raise ToolError("The hold plan does not include the new order; ask for it to be recomputed.")
    g = await core.create_garnishment({
        "client_id": client_id_of(case), "case_ref": doc["case_number"] or doc.get("registration_number") or case.id,
        "issuer_type": doc["issuer_type"], "issuer_name": doc["issuer_name"], "creditor": doc.get("creditor") or "-",
        "claim_type": plan["new_order_claim_type"], "total_amount": new["requested_ron"], "document_ref": case.id,
    })
    case.blackboard["registered_garnishment"] = g
    return g


async def t_apply_plan(case: Case, _):
    plan = bb(case, "allocation_plan", "No hold plan has been computed.")
    registered = case.blackboard.get("registered_garnishment")
    holds = []
    for h in plan["holds"]:
        gid = h["garnishment_id"]
        if gid == "NEW":
            if not registered:
                raise ToolError("The plan contains the new order: register it first (register_garnishment).")
            gid = registered["id"]
        if h["amount"] > 0:
            holds.append({"iban": h["iban"], "garnishment_id": gid, "amount": h["amount"], "amount_ron": h["amount_ron"]})
    result = await core.replace_holds(client_id_of(case), holds)
    case.blackboard["applied_holds"] = {"total_ron": plan["total_blocked_ron"], **result}
    return result


async def t_release(case: Case, inp):
    result = await core.lift_garnishment(inp["garnishment_id"])
    case.blackboard["release"] = result
    return result


def _ro_amount(x: float) -> str:
    return f"{x:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


async def t_letter(case: Case, inp):
    """Builds the official reply. It is addressed to a Romanian authority, so the letter itself is in Romanian."""
    if case.kind == "EVENT":
        raise ToolError("No letter is sent to the issuer for incoming payment events.")
    doc = bb(case, "document", "The document has not been read yet.")
    kind, note = inp["letter_type"], inp.get("extra_note_ro")
    ref_letter = f"adresa dumneavoastră nr. {doc.get('registration_number') or '-'}"
    case_no = doc.get("case_number") or "-"
    ident = case.blackboard.get("identification") or {}
    cnp = ident.get("corrected_cnp") or doc.get("debtor_cnp")
    holds_lines, paragraphs = [], []

    if kind == "GARNISHMENT_CONFIRMATION":
        applied = bb(case, "applied_holds", "The holds have not been applied yet.")
        plan = case.blackboard["allocation_plan"]
        registered = case.blackboard.get("registered_garnishment") or {}
        mine = [h for h in applied["holds"] if h["garnishment_id"] == registered.get("id")]
        holds_lines = [{"iban": h["iban"], "currency": next((a["currency"] for a in plan["accounts"] if a["iban"] == h["iban"]), "RON"),
                        "amount": h["amount"]} for h in mine]
        total = sum(h["amount_ron"] for h in mine)
        new = next((g for g in plan["garnishments"] if g["id"] == "NEW"), {})
        paragraphs = [f"Ca răspuns la {ref_letter} privind înființarea popririi în dosarul nr. {case_no}, vă comunicăm că debitorul "
                      f"figurează în evidențele băncii și că poprirea a fost înregistrată sub nr. {registered.get('id', '-')}."]
        if total > 0:
            paragraphs.append(f"Au fost indisponibilizate sumele de mai jos, în total {_ro_amount(total)} lei (echivalent).")
        else:
            paragraphs.append("La data prezentei, conturile debitorului nu prezintă sume urmăribile disponibile.")
        if new.get("remaining_ron", 0) > 0:
            paragraphs.append(f"Diferența de {_ro_amount(new['remaining_ron'])} lei va fi indisponibilizată din încasările viitoare, "
                              "în limitele prevăzute de lege, până la concurența sumei din adresă.")
        paragraphs.append("Au fost aplicate limitele legale privind sumele exceptate de la urmărire și fracțiunea urmăribilă "
                          "din veniturile periodice, precum și ordinea de preferință a creanțelor.")
        subject = "CONFIRMARE ÎNFIINȚARE POPRIRE"
    elif kind == "NO_ACCOUNTS":
        paragraphs = [f"Ca răspuns la {ref_letter} în dosarul nr. {case_no}, vă comunicăm că persoana {doc.get('debtor_name') or '-'}"
                      f"{f', CNP {cnp},' if cnp else ''} nu figurează în evidențele băncii ca titular de conturi active.",
                      "Pe cale de consecință, nu au fost indisponibilizate sume."]
        subject = "RĂSPUNS LA ADRESA DE POPRIRE – DEBITORUL NU DEȚINE CONTURI"
    elif kind == "RELEASE_CONFIRMATION":
        lift = bb(case, "release", "The garnishment has not been released yet.")
        released = sum(h["amount"] for h in lift["released_holds"])
        paragraphs = [f"Urmare {ref_letter}, vă confirmăm ridicarea popririi {lift['garnishment']['id']} înființate în dosarul "
                      f"nr. {lift['garnishment']['case_ref']}.",
                      f"Au fost deblocate sume în total de {_ro_amount(released)} (moneda contului), iar conturile debitorului nu mai sunt "
                      "indisponibilizate pentru acest dosar."]
        subject = "CONFIRMARE RIDICARE POPRIRE"
    elif kind == "DUPLICATE_NOTICE":
        decision = case.blackboard.get("legal") or {}
        paragraphs = [f"Vă informăm că {ref_letter} în dosarul nr. {case_no} a fost deja înregistrată anterior "
                      f"(poprirea {decision.get('duplicate_of') or '-'}) și se află în executare.",
                      "Nu au fost efectuate indisponibilizări suplimentare în baza acestui exemplar."]
        subject = "INFORMARE – ADRESĂ DE POPRIRE DEJA ÎNREGISTRATĂ"
    else:
        raise ToolError(f"Unknown letter type: {kind}")

    if note:
        paragraphs.append(note)
    reference = f"EXS-{case.id}"
    pdf = await docs.render_letter({
        "bank_name": settings.bank_name, "reference": reference, "recipient": doc.get("issuer_name") or "-",
        "case_ref": case_no, "debtor_name": doc.get("debtor_name") or "-", "debtor_cnp": cnp, "subject": subject,
        "paragraphs": paragraphs, "holds": holds_lines,
    })
    case.response_pdf = pdf
    case.blackboard["letter"] = {"type": kind, "reference": reference, "recipient": doc.get("issuer_name"), "language": "Romanian",
                                 "holds": holds_lines}
    return {"generated": True, "reference": reference, "type": kind,
            "note": "Official letter generated in Romanian (it is addressed to a Romanian authority)."}


ACTION_SCHEMA = schema({
    "actions_taken": {"type": "array", "items": {"type": "string"}},
    "letter_generated": {"type": "boolean"},
    "issues": {"type": "array", "items": {"type": "string"}},
    "summary": {"type": "string"},
})

action = Agent(
    key="actions", label="Action Agent", effort=settings.llm_subagent_effort, result_schema=ACTION_SCHEMA,
    describe_result=lambda r: r.get("summary", "") + (" Issues: " + "; ".join(r["issues"]) if r.get("issues") else ""),
    system=f"""You are the ACTION AGENT. You execute the legal agent's decision in core banking and reply to the issuer.
You never change or invent amounts: you apply exactly the plan computed by the rules engine.

- APPLY_GARNISHMENT: register_garnishment, then apply_hold_plan, then generate_response_letter(GARNISHMENT_CONFIRMATION)
- REEVALUATE (incoming payment event): apply_hold_plan; no letter.
- RELEASE: release_garnishment(id), then generate_response_letter(RELEASE_CONFIRMATION)
- DUPLICATE: change nothing; generate_response_letter(DUPLICATE_NOTICE)
- Debtor not a client / no accounts: generate_response_letter(NO_ACCOUNTS)

If an operation fails, read the error and fix it if you can, otherwise report the problem.
The letter is official and written in Romanian. You may add a short extra_note_ro (in Romanian) only if it gives
the issuer useful information.
{LANGUAGE_RULE}
Finish by calling submit_result.""",
    tools=[
        Tool("register_garnishment", "Register the new garnishment in core banking (from the document data and the legal decision).",
             NO_INPUT, t_register, describe=lambda _: "Registering the new garnishment in core banking.",
             summarize=lambda r: (f"Already registered as {r['already_registered']['id']}." if "already_registered" in r
                                  else f"Registered as {r['id']}.")),
        Tool("apply_hold_plan", "Atomically apply the computed hold plan (replaces the client's active holds).",
             NO_INPUT, t_apply_plan, describe=lambda _: "Applying the hold plan in core banking.",
             summarize=lambda r: f"{r['created']} hold(s) created, {r['released']} previous hold(s) released."),
        Tool("release_garnishment", "Release a garnishment and unblock its amounts.", schema({"garnishment_id": {"type": "string"}}),
             t_release, describe=lambda i: f"Releasing garnishment {i.get('garnishment_id')}.",
             summarize=lambda r: f"Garnishment {r['garnishment']['id']} released; {len(r['released_holds'])} hold(s) unblocked."),
        Tool("generate_response_letter", "Generate the official reply letter to the issuer (PDF, in Romanian).",
             schema({"letter_type": {"type": "string", "enum": list(LETTER_LABEL)},
                     "extra_note_ro": {**NULLABLE_STR, "description": "optional extra paragraph, in Romanian"}}), t_letter,
             describe=lambda i: f"Generating the official reply letter ({LETTER_LABEL.get(i.get('letter_type'), 'reply')}).",
             summarize=lambda r: f"Letter {r['reference']} generated (in Romanian, addressed to the issuer)."),
    ],
)


# ====================================================================== Supervisor

SUB_AGENTS = {"reader_agent": reader, "identification_agent": identification, "legal_agent": legal, "action_agent": action}


def delegate(agent: Agent):
    async def handler(case: Case, inp):
        instructions = inp.get("instructions") or ""
        emit(case, agent.label, "agent_start", text=f"{agent.label} started working.")
        task = (f"Case {case.id} ({case.kind}).\n\nInstructions from the supervisor:\n{instructions}\n\n"
                f"Current case data (blackboard):\n```json\n{blackboard_view(case)}\n```")
        try:
            result = await agent.run(case, task)
        except AgentError as e:
            emit(case, agent.label, "error", text=str(e))
            raise ToolError(f"{agent.label} could not finish the task: {e}")
        case.blackboard[agent.key] = result
        emit(case, agent.label, "agent_result", result=result,
             text=agent.describe_result(result) if agent.describe_result else "Result submitted.")
        return result
    return handler


async def t_ask_human(case: Case, inp):
    raise PauseForHuman(inp["question"], inp.get("options") or [], inp.get("context") or "")


OUTCOMES = ["GARNISHMENT_APPLIED_FULL", "GARNISHMENT_APPLIED_PARTIAL", "NO_FUNDS", "DEBTOR_NOT_CLIENT", "DUPLICATE",
            "GARNISHMENT_RELEASED", "REEVALUATION_APPLIED", "REJECTED_BY_OPERATOR", "DOCUMENT_NOT_PROCESSABLE"]

CLOSE_SCHEMA = schema({"outcome": {"type": "string", "enum": OUTCOMES}, "summary": {"type": "string"}})

supervisor = Agent(
    key="supervisor", label="Supervisor", effort=settings.llm_effort, result_schema=CLOSE_SCHEMA, terminal_tool="close_case",
    max_turns=20,
    system=f"""You are the SUPERVISOR of a multi-agent system that automatically processes garnishment orders
(popriri) received by {settings.bank_name}, a Romanian bank acting as garnishee. You coordinate specialised agents:

- reader_agent: reads the document and extracts structured data.
- identification_agent: identifies the debtor among the bank's clients.
- legal_agent: checks for duplicates and computes, through the deterministic rules engine, what can legally be held.
- action_agent: registers the garnishment, applies holds, releases garnishments, generates the reply to the issuer.
- ask_operator: asks a human operator a question; the case pauses until they answer.
- close_case: closes the case with its final outcome.

How you work:
- You decide the steps based on the situation; do not blindly follow a fixed pipeline. Read every result critically.
- The case data (blackboard) is visible to all agents. Give them clear instructions and flag anything suspicious.
- Never invent or compute amounts. Amounts only come from the rules engine, through legal_agent.
- Ask the operator ONLY when identification is AMBIGUOUS or below 0.8 confidence, when critical fields of the
  document (debtor, amount, case number) are unreadable, or when a tool fails repeatedly. Offer concrete options,
  each one a short, self-contained sentence (for example "CL005 - Andrei Popa, Str. Florilor nr. 12").
- Do not ask about things the system already decides: transaction sources (SALARY, PENSION, CHILD_ALLOWANCE,
  TRANSFER, ...) are labelled by core banking and are authoritative, and the rules engine's plan is the one applied.
- Debtor NOT_FOUND: action_agent generates the NO_ACCOUNTS reply, then close as DEBTOR_NOT_CLIENT.
- A document that is neither a garnishment order nor a release: execute nothing; close as DOCUMENT_NOT_PROCESSABLE.
- EVENT case (new incoming payment for a debtor with active garnishments): there is no document and the client is
  already identified. Ask legal_agent to re-evaluate, then action_agent to apply the plan.
- Before closing a case that has a document, make sure the issuer got a reply (letter generated).
- Before each delegation, write one short sentence saying what you are doing and why. It is shown live to operators.
{LANGUAGE_RULE}""",
    tools=[
        *[Tool(name, f"Delegate a task to the {a.label}. Its result is saved on the blackboard.",
               schema({"instructions": {"type": "string"}}), delegate(a),
               describe=(lambda label: lambda i: f"Assigns a task to the {label}: {i.get('instructions', '')}")(a.label),
               quiet=True) for name, a in SUB_AGENTS.items()],
        Tool("ask_operator", "Ask a human operator a question and wait for the answer (the case pauses).",
             schema({"question": {"type": "string"}, "options": {"type": "array", "items": {"type": "string"}},
                     "context": {"type": "string"}}), t_ask_human,
             describe=lambda _: "Pauses the case to ask a human operator for a decision."),
    ],
)


def start_message(case: Case) -> str:
    if case.kind == "EVENT":
        t = case.trigger
        return (f"New case {case.id} of type EVENT: account {t['iban']} of client {t['client_id']} received "
                f"{t['amount']} {t['currency']} (source: {t['source']}). The client has active garnishments. Re-evaluate the holds.")
    return (f"New case {case.id}: the document \"{case.document_name}\" arrived on the enforcement channel. "
            "Process it end to end.")
