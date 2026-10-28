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

CLAIM_TYPES = ["INTRETINERE", "SALARIALA", "FISCALA", "CHIROGRAFARA"]
NULLABLE_STR = {"type": ["string", "null"]}


def bb(case: Case, key: str, required: str | None = None):
    value = case.blackboard.get(key)
    if value is None and required:
        raise ToolError(required)
    return value


def client_id_of(case: Case) -> str:
    ident = bb(case, "identificare", "Clientul nu a fost identificat încă (rulează întâi agentul de identificare).")
    if ident.get("status") != "IDENTIFICAT" or not ident.get("client_id"):
        raise ToolError(f"Identificarea nu este finală (status {ident.get('status')}).")
    return ident["client_id"]


def blackboard_view(case: Case) -> str:
    view = {k: v for k, v in case.blackboard.items() if k != "extragere_text"}
    return json.dumps(view, ensure_ascii=False, indent=2, default=str)


def schema(properties: dict, required: list[str] | None = None) -> dict:
    return {"type": "object", "properties": properties, "required": required or list(properties), "additionalProperties": False}


NO_INPUT = schema({}, [])


# ====================================================================== Agent Citire

async def t_read_document(case: Case, _):
    if not case.document_bytes:
        raise ToolError("Cazul nu are document atașat.")
    r = await docs.extract(case.document_name or "document.pdf", case.document_bytes)
    case.blackboard["extragere_text"] = {"pagini": r["pages"], "strat_text": r["has_text_layer"]}
    if r["has_text_layer"]:
        return f"Document PDF cu {r['pages']} pagini, strat de text prezent.\n\n{r['text']}"
    if not r["page_images_png_b64"]:
        raise ToolError("Documentul nu are text și nu a putut fi randat ca imagine.")
    blocks = [{"type": "text", "text": f"Documentul NU are strat de text (pare scanat, {r['pages']} pagini). "
                                       "Urmează imaginile paginilor: citește-le vizual, cu atenție la cifre."}]
    blocks += [{"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": b64}}
               for b64 in r["page_images_png_b64"]]
    return blocks


async def t_validate_cnp(_case: Case, inp):
    return await rules.validate_cnp(inp["cnp"])


EXTRACTION_SCHEMA = schema({
    "tip_document": {"type": "string", "enum": ["INFIINTARE_POPRIRE", "RIDICARE_POPRIRE", "ALT_DOCUMENT"]},
    "emitent_tip": {"type": "string", "enum": ["EXECUTOR_JUDECATORESC", "ANAF", "PRIMARIE", "ALT_EMITENT"]},
    "emitent_nume": {"type": "string"},
    "numar_dosar": {**NULLABLE_STR, "description": "dosarul de executare / dosarul fiscal"},
    "numar_inregistrare": {**NULLABLE_STR, "description": "numărul adresei"},
    "debitor_nume": NULLABLE_STR,
    "debitor_cnp": {**NULLABLE_STR, "description": "exact cum apare în document; null dacă lipsește sau e ilizibil"},
    "debitor_adresa": NULLABLE_STR,
    "creditor": NULLABLE_STR,
    "suma": {"type": ["number", "null"]},
    "moneda": {"type": "string"},
    "tip_creanta": {"type": "string", "enum": CLAIM_TYPES + ["NECUNOSCUT"]},
    "descriere_creanta": NULLABLE_STR,
    "iban_virare": NULLABLE_STR,
    "referinta_poprire_ridicata": {**NULLABLE_STR, "description": "doar pentru ridicări: adresa/poprirea vizată"},
    "cnp_valid": {"type": ["boolean", "null"]},
    "incredere": {"type": "number", "description": "între 0 și 1"},
    "probleme": {"type": "array", "items": {"type": "string"}},
})

citire = Agent(
    key="document", label="Agent Citire", effort=settings.llm_subagent_effort, result_schema=EXTRACTION_SCHEMA,
    system=f"""Ești AGENTUL DE CITIRE al departamentului de executări silite din {settings.bank_name}.
Primești o adresă oficială trimisă băncii: înființare de poprire, ridicare de poprire sau alt document.

- Folosește citeste_document. Dacă documentul e scanat, vei primi imaginile paginilor: citește-le vizual.
- Extrage câmpurile exact cum apar. Nu completa date lipsă sau ilizibile: pune null și descrie problema în "probleme".
- Validează CNP-ul cu valideaza_cnp și setează cnp_valid. Nu corecta tu CNP-ul.
- Clasifică tipul creanței:
  INTRETINERE = pensie de întreținere/alimentară; SALARIALA = drepturi salariale datorate de debitor;
  FISCALA = ANAF, impozite și taxe locale, alte creanțe bugetare; CHIROGRAFARA = orice altă datorie
  (facturi, credite, contracte); NECUNOSCUT = nu se poate determina.
- "incredere" reflectă cât de sigur ești pe câmpurile critice (debitor, CNP, sumă, dosar).
Încheie apelând trimite_rezultat.""",
    tools=[
        Tool("citeste_document", "Extrage textul documentului primit (sau imaginile paginilor dacă e scanat).", NO_INPUT, t_read_document),
        Tool("valideaza_cnp", "Validează un CNP (structură, dată de naștere, județ, cifră de control).",
             schema({"cnp": {"type": "string"}}), t_validate_cnp),
    ],
)


# ====================================================================== Agent Identificare

async def t_search_cnp(_c, inp):
    return await core.search_cnp(inp["cnp"])


async def t_suggest_cnp(_c, inp):
    return await rules.suggest_cnp(inp["cnp"])


async def t_search_cnps(_c, inp):
    return await core.search_cnps(inp["cnps"])


async def t_search_name(_c, inp):
    return await core.search_name(inp["nume"])


async def t_client_details(_c, inp):
    client = await core.client(inp["client_id"])
    client["cnp_decodat"] = await rules.validate_cnp(client["cnp"])
    return client


IDENTIFICATION_SCHEMA = schema({
    "status": {"type": "string", "enum": ["IDENTIFICAT", "AMBIGUU", "NEGASIT"]},
    "client_id": NULLABLE_STR,
    "candidati": {"type": "array", "items": schema({"client_id": {"type": "string"}, "motiv": {"type": "string"}})},
    "cnp_corectat": {**NULLABLE_STR, "description": "CNP-ul corect, dacă cel din document era greșit"},
    "incredere": {"type": "number"},
    "motivare": {"type": "string"},
})

identificare = Agent(
    key="identificare", label="Agent Identificare", effort=settings.llm_subagent_effort, result_schema=IDENTIFICATION_SCHEMA,
    system="""Ești AGENTUL DE IDENTIFICARE. Stabilești dacă debitorul din document este client al băncii și care anume.

Strategie (adapteaz-o situației, nu o urma mecanic):
1. CNP valid → cauta_dupa_cnp și confirmă că numele se potrivește.
2. CNP invalid (cifră de control greșită) → sugereaza_corectii_cnp, apoi cauta_dupa_lista_cnp cu candidații;
   acceptă doar un candidat al cărui nume și adresă se potrivesc cu documentul.
3. Fără CNP sau fără rezultat → cauta_dupa_nume, apoi compară adresa și data nașterii (detalii_client).

Reguli: nu ghici. Mai mulți candidați plauzibili → AMBIGUU, cu lista candidaților și ce îi diferențiază.
Nimeni nu se potrivește → NEGASIT. Dacă supervizorul îți transmite o confirmare a operatorului uman,
verifică clientul confirmat cu detalii_client și raportează IDENTIFICAT.
Încheie cu trimite_rezultat.""",
    tools=[
        Tool("cauta_dupa_cnp", "Caută clientul după CNP exact.", schema({"cnp": {"type": "string"}}), t_search_cnp),
        Tool("valideaza_cnp", "Validează un CNP.", schema({"cnp": {"type": "string"}}), t_validate_cnp),
        Tool("sugereaza_corectii_cnp", "Generează CNP-uri valide care diferă printr-o singură cifră sau două cifre inversate.",
             schema({"cnp": {"type": "string"}}), t_suggest_cnp),
        Tool("cauta_dupa_lista_cnp", "Caută clienți pentru o listă de CNP-uri.",
             schema({"cnps": {"type": "array", "items": {"type": "string"}}}), t_search_cnps),
        Tool("cauta_dupa_nume", "Caută clienți după nume (fără diacritice, ordinea cuvintelor nu contează).",
             schema({"nume": {"type": "string"}}), t_search_name),
        Tool("detalii_client", "Detaliile unui client (adresă, conturi, CNP decodat).",
             schema({"client_id": {"type": "string"}}), t_client_details),
    ],
)


# ====================================================================== Agent Juridic

async def t_check_duplicate(case: Case, _):
    doc = bb(case, "document", "Documentul nu a fost citit.")
    if not doc.get("numar_dosar"):
        raise ToolError("Documentul nu are număr de dosar; verificarea de duplicat nu e posibilă.")
    found = await core.garnishments_by_case(doc["numar_dosar"])
    cid = (case.blackboard.get("identificare") or {}).get("client_id")
    return {"numar_dosar": doc["numar_dosar"], "popriri_gasite": found,
            "duplicat_activ_acelasi_client": [g["id"] for g in found if g["client_id"] == cid and g["status"] == "ACTIVE"]}


async def t_financial_snapshot(case: Case, _):
    return await core.snapshot(client_id_of(case))


async def t_active_garnishments(case: Case, _):
    return await core.garnishments(client_id_of(case), status="ACTIVE")


async def t_fx(_c, _):
    return await fx.rates()


async def t_find_to_lift(case: Case, _):
    doc = bb(case, "document", "Documentul nu a fost citit.")
    cid = client_id_of(case)
    refs = [r for r in (doc.get("numar_dosar"), doc.get("referinta_poprire_ridicata")) if r]
    found = {}
    for ref in refs:
        for g in await core.garnishments_by_case(ref):
            found[g["id"]] = g
    return {"cautat_dupa": refs, "popriri": list(found.values()),
            "active_ale_clientului": [g["id"] for g in found.values() if g["client_id"] == cid and g["status"] == "ACTIVE"]}


async def t_allocate(case: Case, inp):
    cid = client_id_of(case)
    snap = await core.snapshot(cid)
    fx_data = await fx.rates()
    rates = fx_data["rates"]
    accounts, notes = [], []
    for a in snap["accounts"]:
        rate = 1.0 if a["currency"] == "RON" else rates.get(a["currency"])
        if rate is None:
            notes.append(f"Contul {a['iban']} în {a['currency']} nu are curs BNR și a fost exclus.")
            continue
        accounts.append({"iban": a["iban"], "currency": a["currency"], "balance": a["balance"], "fx_to_ron": rate,
                         "status": a["status"], "inflows": a["inflows"]})

    active = await core.garnishments(cid, status="ACTIVE")
    garnishments = [{"id": g["id"], "claim_type": g["claim_type"], "amount_ron": g["remaining_amount"],
                     "received_at": g["received_at"]} for g in active]

    include_new = inp.get("include_poprirea_noua", False) and not case.blackboard.get("poprire_inregistrata")
    claim_type = inp.get("tip_creanta")
    if include_new:
        doc = bb(case, "document", "Documentul nu a fost citit.")
        if claim_type not in CLAIM_TYPES:
            raise ToolError(f"Specifică tip_creanta pentru poprirea nouă (una din {CLAIM_TYPES}).")
        if not doc.get("suma"):
            raise ToolError("Documentul nu conține suma de poprit.")
        currency = (doc.get("moneda") or "RON").upper()
        rate = 1.0 if currency == "RON" else rates.get(currency)
        if rate is None:
            raise ToolError(f"Nu există curs BNR pentru moneda {currency}.")
        garnishments.append({"id": "NOU", "claim_type": claim_type, "amount_ron": round(doc["suma"] * rate, 2),
                             "received_at": datetime.now().isoformat()})

    if not accounts:
        raise ToolError("Clientul nu are conturi utilizabile.")
    plan = await rules.allocate(accounts, garnishments)
    plan["curs_bnr"] = {"data": fx_data.get("date"), "sursa": fx_data.get("source")}
    plan["note"] = notes
    plan["include_poprirea_noua"] = include_new
    plan["tip_creanta_noua"] = claim_type if include_new else None
    case.blackboard["plan_blocare"] = plan
    return plan


LEGAL_SCHEMA = schema({
    "decizie": {"type": "string", "enum": ["APLICA_POPRIRE", "DUPLICAT", "RIDICARE", "REEVALUARE", "FARA_CONTURI", "NECESITA_OPERATOR"]},
    "tip_creanta": {"type": ["string", "null"], "enum": CLAIM_TYPES + [None]},
    "poprire_de_ridicat": NULLABLE_STR,
    "poprire_duplicat": NULLABLE_STR,
    "rezumat": {"type": "string", "description": "explicație pentru operator: ce e protejat, ce se blochează și de ce"},
    "temei_legal": {"type": "array", "items": {"type": "string"}},
})

juridic = Agent(
    key="juridic", label="Agent Juridic", effort=settings.llm_effort, result_schema=LEGAL_SCHEMA,
    system="""Ești AGENTUL JURIDIC. Decizi ce trebuie făcut legal pentru clientul identificat.
NU calculezi sume: folosești calculeaza_alocare, care apelează un motor de reguli determinist.

- Înființare de poprire: verifica_duplicat (dosar deja activ pentru același client → DUPLICAT, fără alte calcule).
  Apoi situatie_financiara și popriri_active pentru context. Confirmă tipul creanței (poți corecta clasificarea
  agentului de citire dacă textul o justifică). Apoi calculeaza_alocare(include_poprirea_noua=true, tip_creanta=...).
- Ridicare de poprire: gaseste_poprire_de_ridicat. Dacă poprirea aparține clientului și e activă → RIDICARE (cu id).
- Eveniment de încasare (fără document): calculeaza_alocare(include_poprirea_noua=false) → REEVALUARE.
- Fără conturi active → FARA_CONTURI. Situație pe care nu o poți încadra → NECESITA_OPERATOR.

În "rezumat", explică pe înțelesul unui operator: sume protejate (alocații, fracțiunea din salariu),
prioritatea între creditori, ce rămâne neacoperit. Folosește explicațiile returnate de motor.
Încheie cu trimite_rezultat.""",
    tools=[
        Tool("verifica_duplicat", "Caută popriri existente cu același număr de dosar.", NO_INPUT, t_check_duplicate),
        Tool("situatie_financiara", "Conturile clientului: sold, sume deja blocate, încasări din ultimele 30 de zile pe surse.",
             NO_INPUT, t_financial_snapshot),
        Tool("popriri_active", "Popririle active deja înregistrate pentru client.", NO_INPUT, t_active_garnishments),
        Tool("curs_bnr", "Cursurile oficiale BNR ale zilei.", NO_INPUT, t_fx),
        Tool("gaseste_poprire_de_ridicat", "Găsește poprirea vizată de o adresă de ridicare.", NO_INPUT, t_find_to_lift),
        Tool("calculeaza_alocare",
             "Calculează (determinist) planul de blocare pentru TOATE popririle active ale clientului, opțional plus cea nouă din document.",
             schema({"include_poprirea_noua": {"type": "boolean"},
                     "tip_creanta": {"type": ["string", "null"], "enum": CLAIM_TYPES + [None]}}), t_allocate),
    ],
)


# ====================================================================== Agent Acțiune

async def t_register(case: Case, _):
    if case.blackboard.get("poprire_inregistrata"):
        return {"deja_inregistrata": case.blackboard["poprire_inregistrata"]}
    doc = bb(case, "document", "Documentul nu a fost citit.")
    legal = bb(case, "juridic", "Agentul juridic nu a decis încă.")
    if legal.get("decizie") != "APLICA_POPRIRE":
        raise ToolError(f"Decizia juridică este {legal.get('decizie')}, nu APLICA_POPRIRE.")
    plan = bb(case, "plan_blocare", "Nu există plan de blocare calculat.")
    new = next((g for g in plan["garnishments"] if g["id"] == "NOU"), None)
    if new is None:
        raise ToolError("Planul de blocare nu include poprirea nouă; cere recalcularea.")
    g = await core.create_garnishment({
        "client_id": client_id_of(case), "case_ref": doc["numar_dosar"] or doc.get("numar_inregistrare") or case.id,
        "issuer_type": doc["emitent_tip"], "issuer_name": doc["emitent_nume"], "creditor": doc.get("creditor") or "-",
        "claim_type": plan["tip_creanta_noua"], "total_amount": new["requested_ron"], "document_ref": case.id,
    })
    case.blackboard["poprire_inregistrata"] = g
    return g


async def t_apply_plan(case: Case, _):
    plan = bb(case, "plan_blocare", "Nu există plan de blocare calculat.")
    registered = case.blackboard.get("poprire_inregistrata")
    holds = []
    for h in plan["holds"]:
        gid = h["garnishment_id"]
        if gid == "NOU":
            if not registered:
                raise ToolError("Planul conține poprirea nouă: înregistreaz-o întâi (inregistreaza_poprirea).")
            gid = registered["id"]
        if h["amount"] > 0:
            holds.append({"iban": h["iban"], "garnishment_id": gid, "amount": h["amount"], "amount_ron": h["amount_ron"]})
    result = await core.replace_holds(client_id_of(case), holds)
    case.blackboard["blocari_aplicate"] = {"total_ron": plan["total_blocked_ron"], **result}
    return result


async def t_lift(case: Case, inp):
    result = await core.lift_garnishment(inp["id_poprire"])
    case.blackboard["ridicare"] = result
    return result


def _fmt(x: float) -> str:
    return f"{x:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


async def t_letter(case: Case, inp):
    if case.kind == "EVENIMENT":
        raise ToolError("Pentru evenimente de încasare nu se trimite scrisoare emitentului.")
    doc = bb(case, "document", "Documentul nu a fost citit.")
    kind, note = inp["tip"], inp.get("nota_suplimentara")
    adresa = f"adresa dumneavoastră nr. {doc.get('numar_inregistrare') or '-'}"
    dosar = doc.get("numar_dosar") or "-"
    ident = case.blackboard.get("identificare") or {}
    cnp = ident.get("cnp_corectat") or doc.get("debitor_cnp")
    holds_lines, paragraphs = [], []

    if kind == "CONFIRMARE_POPRIRE":
        applied = bb(case, "blocari_aplicate", "Blocările nu au fost aplicate încă.")
        plan = case.blackboard["plan_blocare"]
        registered = case.blackboard.get("poprire_inregistrata") or {}
        mine = [h for h in applied["holds"] if h["garnishment_id"] == registered.get("id")]
        holds_lines = [{"iban": h["iban"], "currency": next((a["currency"] for a in plan["accounts"] if a["iban"] == h["iban"]), "RON"),
                        "amount": h["amount"]} for h in mine]
        total = sum(h["amount_ron"] for h in mine)
        new = next((g for g in plan["garnishments"] if g["id"] == "NOU"), {})
        paragraphs = [f"Ca răspuns la {adresa} privind înființarea popririi în dosarul nr. {dosar}, vă comunicăm că debitorul "
                      f"figurează în evidențele băncii și că poprirea a fost înregistrată sub nr. {registered.get('id', '-')}."]
        if total > 0:
            paragraphs.append(f"Au fost indisponibilizate sumele de mai jos, în total {_fmt(total)} lei (echivalent).")
        else:
            paragraphs.append("La data prezentei, conturile debitorului nu prezintă sume urmăribile disponibile.")
        if new.get("remaining_ron", 0) > 0:
            paragraphs.append(f"Diferența de {_fmt(new['remaining_ron'])} lei va fi indisponibilizată din încasările viitoare, "
                              "în limitele prevăzute de lege, până la concurența sumei din adresă.")
        paragraphs.append("Au fost aplicate limitele legale privind sumele exceptate de la urmărire și fracțiunea urmăribilă "
                          "din veniturile periodice, precum și ordinea de preferință a creanțelor.")
        subject = "CONFIRMARE ÎNFIINȚARE POPRIRE"
    elif kind == "NU_DETINE_CONTURI":
        paragraphs = [f"Ca răspuns la {adresa} în dosarul nr. {dosar}, vă comunicăm că persoana {doc.get('debitor_nume') or '-'}"
                      f"{f', CNP {cnp},' if cnp else ''} nu figurează în evidențele băncii ca titular de conturi active.",
                      "Pe cale de consecință, nu au fost indisponibilizate sume."]
        subject = "RĂSPUNS LA ADRESA DE POPRIRE – DEBITORUL NU DEȚINE CONTURI"
    elif kind == "CONFIRMARE_RIDICARE":
        lift = bb(case, "ridicare", "Poprirea nu a fost ridicată încă.")
        released = sum(h["amount"] for h in lift["released_holds"])
        paragraphs = [f"Urmare {adresa}, vă confirmăm ridicarea popririi {lift['garnishment']['id']} înființate în dosarul "
                      f"nr. {lift['garnishment']['case_ref']}.",
                      f"Au fost deblocate sume în total de {_fmt(released)} (moneda contului), iar conturile debitorului nu mai sunt indisponibilizate pentru acest dosar."]
        subject = "CONFIRMARE RIDICARE POPRIRE"
    elif kind == "INFORMARE_DUPLICAT":
        legal = case.blackboard.get("juridic") or {}
        paragraphs = [f"Vă informăm că {adresa} în dosarul nr. {dosar} a fost deja înregistrată anterior "
                      f"(poprirea {legal.get('poprire_duplicat') or '-'}) și se află în executare.",
                      "Nu au fost efectuate indisponibilizări suplimentare în baza acestui exemplar."]
        subject = "INFORMARE – ADRESĂ DE POPRIRE DEJA ÎNREGISTRATĂ"
    else:
        raise ToolError(f"Tip de scrisoare necunoscut: {kind}")

    if note:
        paragraphs.append(note)
    reference = f"EXS-{case.id}"
    pdf = await docs.render_letter({
        "bank_name": settings.bank_name, "reference": reference, "recipient": doc.get("emitent_nume") or "-",
        "case_ref": dosar, "debtor_name": doc.get("debitor_nume") or "-", "debtor_cnp": cnp, "subject": subject,
        "paragraphs": paragraphs, "holds": holds_lines,
    })
    case.response_pdf = pdf
    case.blackboard["scrisoare"] = {"tip": kind, "referinta": reference, "destinatar": doc.get("emitent_nume"), "paragrafe": paragraphs}
    return {"generat": True, "referinta": reference, "tip": kind, "paragrafe": paragraphs}


ACTION_SCHEMA = schema({
    "actiuni_efectuate": {"type": "array", "items": {"type": "string"}},
    "scrisoare_generata": {"type": "boolean"},
    "probleme": {"type": "array", "items": {"type": "string"}},
    "rezumat": {"type": "string"},
})

actiune = Agent(
    key="actiuni", label="Agent Acțiune", effort=settings.llm_subagent_effort, result_schema=ACTION_SCHEMA,
    system="""Ești AGENTUL DE ACȚIUNE. Execuți în core banking decizia agentului juridic și răspunzi emitentului.
Nu modifici și nu inventezi sume: aplici exact planul calculat de motorul de reguli.

- APLICA_POPRIRE: inregistreaza_poprirea → aplica_planul_de_blocare → genereaza_raspuns(CONFIRMARE_POPRIRE)
- REEVALUARE (eveniment de încasare): aplica_planul_de_blocare; fără scrisoare.
- RIDICARE: ridica_poprirea(id) → genereaza_raspuns(CONFIRMARE_RIDICARE)
- DUPLICAT: nu modifici nimic; genereaza_raspuns(INFORMARE_DUPLICAT)
- Debitor care nu e client / fără conturi: genereaza_raspuns(NU_DETINE_CONTURI)

Dacă o operațiune eșuează, citește eroarea și corectează dacă se poate, altfel raportează problema.
Poți adăuga în scrisoare o notă scurtă (nota_suplimentara), doar dacă aduce o informație utilă emitentului.
Încheie cu trimite_rezultat.""",
    tools=[
        Tool("inregistreaza_poprirea", "Înregistrează poprirea nouă în core banking (din datele documentului și decizia juridică).",
             NO_INPUT, t_register),
        Tool("aplica_planul_de_blocare", "Aplică atomic planul de blocare calculat (înlocuiește blocările active ale clientului).",
             NO_INPUT, t_apply_plan),
        Tool("ridica_poprirea", "Ridică o poprire și deblochează sumele.", schema({"id_poprire": {"type": "string"}}), t_lift),
        Tool("genereaza_raspuns", "Generează scrisoarea oficială de răspuns către emitent (PDF).",
             schema({"tip": {"type": "string", "enum": ["CONFIRMARE_POPRIRE", "NU_DETINE_CONTURI", "CONFIRMARE_RIDICARE", "INFORMARE_DUPLICAT"]},
                     "nota_suplimentara": NULLABLE_STR}), t_letter),
    ],
)


# ====================================================================== Supervizor

SUB_AGENTS = {"agent_citire": citire, "agent_identificare": identificare, "agent_juridic": juridic, "agent_actiune": actiune}


def delegate(agent: Agent):
    async def handler(case: Case, inp):
        instructions = inp.get("instructiuni") or ""
        emit(case, agent.label, "agent_start", instructions=instructions)
        task = (f"Caz {case.id} ({case.kind}).\n\nInstrucțiuni de la supervizor:\n{instructions}\n\n"
                f"Datele curente ale cazului (blackboard):\n```json\n{blackboard_view(case)}\n```")
        try:
            result = await agent.run(case, task)
        except AgentError as e:
            emit(case, agent.label, "error", message=str(e))
            raise ToolError(f"{agent.label} nu a putut finaliza sarcina: {e}")
        case.blackboard[agent.key] = result
        emit(case, agent.label, "agent_result", result=result)
        return result
    return handler


async def t_ask_human(case: Case, inp):
    raise PauseForHuman(inp["intrebare"], inp.get("optiuni") or [], inp.get("context") or "")


OUTCOMES = ["POPRIRE_APLICATA_INTEGRAL", "POPRIRE_APLICATA_PARTIAL", "FARA_FONDURI", "DEBITOR_NECLIENT", "DUPLICAT",
            "POPRIRE_RIDICATA", "REEVALUARE_APLICATA", "RESPINS_DE_OPERATOR", "DOCUMENT_NEPROCESABIL"]

CLOSE_SCHEMA = schema({"rezultat": {"type": "string", "enum": OUTCOMES}, "rezumat": {"type": "string"}})

supervisor = Agent(
    key="supervizor", label="Supervizor", effort=settings.llm_effort, result_schema=CLOSE_SCHEMA, terminal_tool="inchide_caz",
    max_turns=20,
    system=f"""Ești SUPERVIZORUL unui sistem multi-agent care procesează automat adresele de poprire primite de
{settings.bank_name}, în calitate de terț poprit. Coordonezi o echipă de agenți specializați:

- agent_citire: citește documentul și extrage datele structurate.
- agent_identificare: identifică debitorul printre clienții băncii.
- agent_juridic: verifică duplicatele și calculează, prin motorul de reguli determinist, ce se poate bloca legal.
- agent_actiune: înregistrează poprirea, aplică blocările, ridică popriri, generează răspunsul către emitent.
- intreaba_operator: pune o întrebare unui operator uman; cazul intră în pauză până la răspuns.
- inchide_caz: închide cazul cu rezultatul final.

Cum lucrezi:
- Tu decizi pașii în funcție de situație; nu urma orbește un flux fix. Citește critic fiecare rezultat primit.
- Datele cazului (blackboard) sunt vizibile tuturor agenților. Dă-le instrucțiuni clare și semnalează suspiciunile.
- Nu inventa și nu calcula sume. Sumele vin doar din motorul de reguli, prin agent_juridic.
- Escaladează la operator DOAR când identificarea e AMBIGUU sau are încredere sub 0,8, când câmpuri critice ale
  documentului (debitor, sumă, dosar) sunt ilizibile, sau când o unealtă eșuează repetat. Oferă opțiuni concrete.
- Nu escalada pentru încadrări pe care sistemul le stabilește deja: sursa tranzacțiilor (SALARIU, PENSIE, ALOCATIE,
  TRANSFER etc.) este etichetată de core banking și este autoritativă, iar planul motorului de reguli e cel aplicat.
- Debitor NEGASIT → agent_actiune generează răspunsul NU_DETINE_CONTURI, apoi închizi ca DEBITOR_NECLIENT.
- Document care nu e poprire sau ridicare de poprire → nu executa nimic; închide ca DOCUMENT_NEPROCESABIL.
- Caz de tip EVENIMENT (încasare nouă la un debitor cu popriri active): nu există document; clientul e deja
  identificat. Cere agentului juridic reevaluarea, apoi agentului de acțiune aplicarea planului.
- Înainte de a închide un caz cu document, asigură-te că emitentul a primit răspuns (scrisoarea generată).
- Înainte de fiecare delegare, scrie o frază scurtă în română despre ce faci și de ce. Este afișată live.""",
    tools=[
        *[Tool(name, f"Deleagă o sarcină către {a.label}. Rezultatul lui se salvează în blackboard.",
               schema({"instructiuni": {"type": "string"}}), delegate(a)) for name, a in SUB_AGENTS.items()],
        Tool("intreaba_operator", "Pune o întrebare unui operator uman și așteaptă răspunsul (cazul intră în pauză).",
             schema({"intrebare": {"type": "string"}, "optiuni": {"type": "array", "items": {"type": "string"}},
                     "context": {"type": "string"}}), t_ask_human),
    ],
)


def start_message(case: Case) -> str:
    if case.kind == "EVENIMENT":
        t = case.trigger
        return (f"Caz nou {case.id} de tip EVENIMENT: în contul {t['iban']} al clientului {t['client_id']} a intrat suma de "
                f"{t['amount']} {t['currency']} (sursa: {t['source']}). Clientul are popriri active. Reevaluează blocările.")
    return (f"Caz nou {case.id}: pe canalul de executări silite a sosit documentul „{case.document_name}”. "
            "Procesează-l de la cap la coadă.")
