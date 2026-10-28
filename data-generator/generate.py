"""Generates the synthetic dataset for the demo.

Outputs (in DATA_DIR, default /data):
  seed.json        - clients, accounts, transactions, existing garnishments and holds (core-banking seed)
  popriri/*.pdf    - incoming garnishment documents, one per demo scenario
  scenarios.json   - scenario catalogue shown in the dashboard

Dates are relative to today, so the "last 30 days" income window always matches the demo.
"""

import io
import json
import os
import random
import shutil
from datetime import date, datetime, timedelta
from pathlib import Path

import pypdfium2 as pdfium
from PIL import Image
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

OUT = Path(os.environ.get("DATA_DIR", "/data"))
DOCS = OUT / "popriri"
TODAY = date.today()
BANK_NAME = "BANCA DEMO S.A."
BANK_CODE = "DEMO"

random.seed(42)

FONT_DIR = Path("/usr/share/fonts/truetype/dejavu")
pdfmetrics.registerFont(TTFont("DejaVu", str(FONT_DIR / "DejaVuSans.ttf")))
pdfmetrics.registerFont(TTFont("DejaVu-Bold", str(FONT_DIR / "DejaVuSans-Bold.ttf")))

STYLE = ParagraphStyle("body", fontName="DejaVu", fontSize=10, leading=14, spaceAfter=6)
SMALL = ParagraphStyle("small", parent=STYLE, fontSize=8, leading=10, textColor=colors.grey)
HEADER = ParagraphStyle("header", parent=STYLE, fontName="DejaVu-Bold", fontSize=11, leading=14)
TITLE = ParagraphStyle("title", parent=STYLE, fontName="DejaVu-Bold", fontSize=13, alignment=1, spaceBefore=10, spaceAfter=10)


# ---------------------------------------------------------------- identifiers

CNP_KEY = "279146358279"


def cnp_control(first12: str) -> int:
    r = sum(int(a) * int(b) for a, b in zip(first12, CNP_KEY)) % 11
    return 1 if r == 10 else r


def make_cnp(sex: str, birth: date, county: int, seq: int) -> str:
    century = {18: (3, 4), 19: (1, 2), 20: (5, 6)}[birth.year // 100]
    s = century[0] if sex == "M" else century[1]
    first12 = f"{s}{birth:%y%m%d}{county:02d}{seq:03d}"
    return first12 + str(cnp_control(first12))


def corrupt_cnp(cnp: str) -> str:
    """Changes one digit so the checksum no longer matches (simulates an OCR/typing error)."""
    for pos in (8, 9, 10, 7):
        for d in "0123456789":
            if d == cnp[pos]:
                continue
            cand = cnp[:pos] + d + cnp[pos + 1:]
            if cnp_control(cand[:12]) != int(cand[12]):
                return cand
    raise RuntimeError("could not corrupt CNP")


def make_iban(n: int) -> str:
    bban = BANK_CODE + f"{n:016d}"
    rearranged = bban + "RO00"
    numeric = "".join(str(int(c, 36)) for c in rearranged)
    check = 98 - int(numeric) % 97
    return f"RO{check:02d}{bban}"


def ro_amount(x: float) -> str:
    s = f"{x:,.2f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


# ---------------------------------------------------------------- core banking data

clients, accounts, transactions, garnishments, holds = [], [], [], [], []
_iban_seq = [1000]


def add_client(cid, first, last, sex, birth, county, seq, address):
    c = {
        "id": cid, "cnp": make_cnp(sex, birth, county, seq), "first_name": first, "last_name": last,
        "birth_date": birth.isoformat(), "address": address,
    }
    clients.append(c)
    return c


def add_account(client_id, currency="RON", product="Cont curent", status="ACTIVE"):
    _iban_seq[0] += 1
    acc = {"iban": make_iban(_iban_seq[0]), "client_id": client_id, "currency": currency,
           "product": product, "status": status, "balance": 0.0}
    accounts.append(acc)
    return acc


def tx(acc, days_ago, amount, source, description, direction="CREDIT"):
    booked = datetime.combine(TODAY - timedelta(days=days_ago), datetime.min.time()) + timedelta(hours=10)
    transactions.append({"iban": acc["iban"], "booked_at": booked.isoformat(), "amount": round(amount, 2),
                         "direction": direction, "source": source, "description": description})
    acc["balance"] = round(acc["balance"] + (amount if direction == "CREDIT" else -amount), 2)


def debit(acc, days_ago, amount, description):
    tx(acc, days_ago, amount, "PLATA", description, direction="DEBIT")


# Scenario clients (fixed so the demo is deterministic)
ion = add_client("CL001", "Ion", "Popescu", "M", date(1985, 3, 12), 42, 15, "Str. Mihai Eminescu nr. 14, Sector 2, București")
a = add_account("CL001")
tx(a, 45, 9000, "TRANSFER", "Sold reportat")
tx(a, 20, 4200, "TRANSFER", "Încasare factură servicii IT")
debit(a, 10, 750, "Plată card POS")
b = add_account("CL001", product="Cont economii")
tx(b, 50, 3000, "TRANSFER", "Depunere economii")
add_account("CL001", product="Cont curent (închis)", status="CLOSED")

maria = add_client("CL002", "Maria", "Ionescu", "F", date(1990, 7, 23), 12, 87, "Str. Memorandumului nr. 5, Cluj-Napoca, jud. Cluj")
a = add_account("CL002")
tx(a, 45, 1500, "TRANSFER", "Sold reportat")
tx(a, 15, 6500, "SALARIU", "Salariu - SC SOFTCLUJ SRL")
debit(a, 5, 1200, "Plată chirie")

elena = add_client("CL003", "Elena", "Dumitrescu", "F", date(1988, 11, 2), 22, 41, "Bd. Independenței nr. 30, Iași, jud. Iași")
a = add_account("CL003")
tx(a, 45, 300, "TRANSFER", "Sold reportat")
tx(a, 12, 4200, "SALARIU", "Salariu - SC MOLDOVA RETAIL SRL")
tx(a, 8, 719, "ALOCATIE", "Alocație de stat pentru copii - AJPIS Iași")

gheorghe = add_client("CL004", "Gheorghe", "Stan", "M", date(1979, 5, 17), 43, 102, "Str. Fizicienilor nr. 8, Sector 3, București")
a_gh = add_account("CL004")
tx(a_gh, 50, 300, "TRANSFER", "Sold reportat")
tx(a_gh, 14, 4500, "SALARIU", "Salariu - SC CONSTRUCT GRUP SRL")

popa1 = add_client("CL005", "Andrei", "Popa", "M", date(1992, 4, 15), 43, 33, "Str. Florilor nr. 12, Sector 3, București")
a = add_account("CL005")
tx(a, 40, 3200, "TRANSFER", "Sold reportat")
popa2 = add_client("CL006", "Andrei", "Popa", "M", date(1987, 9, 30), 43, 58, "Str. Florilor nr. 17, Sector 3, București")
a = add_account("CL006")
tx(a, 40, 5100, "TRANSFER", "Sold reportat")

vasile = add_client("CL007", "Vasile", "Georgescu", "M", date(1970, 1, 25), 42, 77, "Calea Moșilor nr. 101, Sector 2, București")
a_va = add_account("CL007")
tx(a_va, 60, 7300, "TRANSFER", "Sold reportat")

ana = add_client("CL008", "Ana", "Constantinescu", "F", date(1983, 6, 9), 41, 64, "Str. Aviatorilor nr. 3, Sector 1, București")
a = add_account("CL008", currency="EUR", product="Cont curent EUR")
tx(a, 40, 3000, "TRANSFER", "Sold reportat")

mihai = add_client("CL009", "Mihai", "Radu", "M", date(1995, 12, 1), 35, 19, "Str. Lugojului nr. 9, Timișoara, jud. Timiș")
a = add_account("CL009")
tx(a, 45, 650, "TRANSFER", "Sold reportat")
debit(a, 20, 500, "Plată rată telefon")

ioana = add_client("CL010", "Ioana", "Stoica", "F", date(1991, 2, 14), 13, 90, "Bd. Tomis nr. 120, Constanța, jud. Constanța")
a = add_account("CL010")
tx(a, 40, 2600, "TRANSFER", "Sold reportat")

# Not a client of the bank (scenario 7)
cristian = {"first_name": "Cristian", "last_name": "Marin", "cnp": make_cnp("M", date(1982, 8, 19), 46, 21),
            "address": "Str. Turnu Măgurele nr. 22, Sector 4, București"}

# Filler clients so searches are not trivial
FIRST_M = ["Alexandru", "Florin", "Bogdan", "Cătălin", "Dan", "Radu", "Sorin", "Marius"]
FIRST_F = ["Ioana", "Andreea", "Cristina", "Simona", "Raluca", "Georgiana", "Larisa", "Diana"]
LAST = ["Popescu", "Ionescu", "Pop", "Dumitru", "Stoica", "Gheorghe", "Matei", "Ilie", "Munteanu", "Lazăr", "Moldovan"]
CITIES = [(12, "Cluj-Napoca, jud. Cluj"), (22, "Iași, jud. Iași"), (35, "Timișoara, jud. Timiș"),
          (41, "Sector 1, București"), (44, "Sector 4, București"), (8, "Brașov, jud. Brașov")]
for i in range(11, 31):
    sex = random.choice("MF")
    first = random.choice(FIRST_M if sex == "M" else FIRST_F)
    county, city = random.choice(CITIES)
    birth = date(random.randint(1960, 2001), random.randint(1, 12), random.randint(1, 28))
    c = add_client(f"CL{i:03d}", first, random.choice(LAST), sex, birth, county, random.randint(1, 999),
                   f"Str. {random.choice(['Libertății', 'Unirii', 'Victoriei', 'Republicii'])} nr. {random.randint(1, 120)}, {city}")
    acc = add_account(c["id"])
    tx(acc, 45, random.randint(200, 9000), "TRANSFER", "Sold reportat")
    if random.random() < 0.7:
        tx(acc, random.randint(3, 25), random.randint(3000, 9000), "SALARIU", "Salariu")
    if random.random() < 0.2:
        tx(acc, random.randint(3, 25), 719, "ALOCATIE", "Alocație de stat pentru copii")
    debit(acc, random.randint(1, 20), random.randint(50, 400), "Plată card POS")

# Existing garnishments already registered at the bank
received_30 = (datetime.combine(TODAY - timedelta(days=30), datetime.min.time()) + timedelta(hours=9)).isoformat()
garnishments.append({
    "id": "GR-0001", "client_id": "CL004", "case_ref": "DGRFPB-S3/4471/2026", "issuer_type": "ANAF",
    "issuer_name": "ANAF - Administrația Sector 3 a Finanțelor Publice", "creditor": "Statul român prin ANAF",
    "claim_type": "FISCALA", "total_amount": 6000.0, "received_at": received_30, "status": "ACTIVE",
})
holds.append({"iban": a_gh["iban"], "garnishment_id": "GR-0001", "amount": 1800.0, "amount_ron": 1800.0})
garnishments.append({
    "id": "GR-0002", "client_id": "CL007", "case_ref": "877/2025", "issuer_type": "EXECUTOR_JUDECATORESC",
    "issuer_name": "BEJ Ionescu Adrian", "creditor": "SC Credit Rapid IFN SA",
    "claim_type": "CHIROGRAFARA", "total_amount": 2000.0, "received_at": received_30, "status": "ACTIVE",
})
holds.append({"iban": a_va["iban"], "garnishment_id": "GR-0002", "amount": 2000.0, "amount_ron": 2000.0})


# ---------------------------------------------------------------- PDF templates

def doc_date(days_ago=1) -> str:
    return (TODAY - timedelta(days=days_ago)).strftime("%d.%m.%Y")


def kv_table(rows):
    t = Table([[Paragraph(f"<b>{k}</b>", STYLE), Paragraph(v, STYLE)] for k, v in rows], colWidths=[45 * mm, 120 * mm])
    t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.4, colors.grey), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    return t


def render(flowables) -> bytes:
    buf = io.BytesIO()
    SimpleDocTemplate(buf, pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm, topMargin=18 * mm, bottomMargin=18 * mm).build(flowables)
    return buf.getvalue()


def executor_doc(*, bej, bej_address, case_ref, reg_no, debtor, cnp, address, amount, creditor, title, claim_desc,
                 creditor_iban, banner=None, lift_of=None):
    f = []
    if banner:
        f.append(Paragraph(banner, SMALL))
    f += [
        Paragraph(f"BIROUL EXECUTORULUI JUDECĂTORESC {bej.upper()}", HEADER),
        Paragraph(f"Sediul: {bej_address} · Tel. 021 300 00 00 · bej@example.ro", SMALL),
        Spacer(1, 6),
        Paragraph(f"Dosar de executare nr. <b>{case_ref}</b>", STYLE),
        Paragraph(f"Nr. {reg_no} din {doc_date()}", STYLE),
        Paragraph(f"Către: <b>{BANK_NAME}</b> – în calitate de terț poprit, Departamentul Executări Silite", STYLE),
    ]
    if lift_of:
        f += [
            Paragraph("ADRESĂ DE RIDICARE A POPRIRII", TITLE),
            Paragraph(
                f"Prin prezenta vă comunicăm că debitorul <b>{debtor}</b>, CNP <b>{cnp}</b>, domiciliat în {address}, "
                f"a achitat integral debitul datorat creditorului {creditor} în dosarul de executare nr. {case_ref}.", STYLE),
            Paragraph(
                f"În consecință, dispunem <b>ridicarea popririi</b> înființate prin adresa nr. {lift_of} asupra conturilor "
                "debitorului și vă solicităm deblocarea sumelor indisponibilizate.", STYLE),
        ]
    else:
        f += [
            Paragraph("ADRESĂ DE ÎNFIINȚARE A POPRIRII", TITLE),
            Paragraph(
                f"În temeiul art. 781 și următoarele din Codul de procedură civilă, în baza titlului executoriu reprezentat de "
                f"{title}, la cererea creditorului <b>{creditor}</b>, vă comunicăm înființarea popririi asupra sumelor de bani "
                "datorate debitorului:", STYLE),
            kv_table([("Debitor", debtor), ("CNP", cnp), ("Domiciliu", address)]),
            Spacer(1, 6),
            Paragraph(
                f"până la concurența sumei de <b>{ro_amount(amount)} lei</b>, reprezentând {claim_desc}.", STYLE),
            Paragraph(
                "Vă solicităm să indisponibilizați sumele existente și pe cele viitoare, în limitele prevăzute de lege, "
                f"și să le virați în contul de consemnare <b>{creditor_iban}</b>, cu mențiunea numărului dosarului de executare. "
                "Fac excepție sumele exceptate de la urmărire potrivit legii.", STYLE),
            Paragraph("Vă rugăm să ne comunicați, în termenul legal, dacă debitorul deține conturi și sumele indisponibilizate.", STYLE),
        ]
    f += [Spacer(1, 16), Paragraph(f"Executor judecătoresc,<br/><b>{bej}</b><br/>(semnătură și ștampilă)", STYLE)]
    return render(f)


def anaf_doc(*, unit, case_ref, reg_no, debtor, cnp, address, amount, title, treasury_iban):
    f = [
        Paragraph("MINISTERUL FINANȚELOR", SMALL),
        Paragraph("AGENȚIA NAȚIONALĂ DE ADMINISTRARE FISCALĂ", HEADER),
        Paragraph("Direcția Generală Regională a Finanțelor Publice", STYLE),
        Paragraph(unit, STYLE),
        Spacer(1, 4),
        Paragraph(f"Nr. înregistrare: <b>{reg_no}</b> / {doc_date(2)} · Dosar fiscal: <b>{case_ref}</b>", STYLE),
        Paragraph(f"Către: {BANK_NAME}", STYLE),
        Paragraph("ADRESĂ DE ÎNFIINȚARE A POPRIRII ASUPRA DISPONIBILITĂȚILOR BĂNEȘTI", TITLE),
        Paragraph(
            "În temeiul art. 236 din Legea nr. 207/2015 privind Codul de procedură fiscală, cu modificările și completările "
            "ulterioare, vă comunicăm înființarea popririi asupra disponibilităților bănești ale contribuabilului:", STYLE),
        kv_table([("Contribuabil", debtor), ("CNP/CIF", cnp), ("Domiciliu fiscal", address),
                  ("Titlu executoriu", title), ("Suma totală datorată", f"{ro_amount(amount)} lei")]),
        Spacer(1, 6),
        Paragraph(
            f"Sumele indisponibilizate se vor vira în contul <b>{treasury_iban}</b> deschis la Trezoreria Statului. "
            "Poprirea se extinde și asupra sumelor viitoare provenite din încasările zilnice în conturi, până la achitarea integrală.", STYLE),
        Spacer(1, 16),
        Paragraph("Șef administrație,<br/>(semnătură și ștampilă)", STYLE),
    ]
    return render(f)


def primarie_doc(*, sector, case_ref, reg_no, debtor, cnp, address, amount, details, iban):
    f = [
        Paragraph(f"PRIMĂRIA SECTORULUI {sector} AL MUNICIPIULUI BUCUREȘTI", HEADER),
        Paragraph("Direcția Generală de Impozite și Taxe Locale – Serviciul Executare Silită", STYLE),
        Paragraph(f"Adresa nr. {reg_no} din {doc_date(3)} · Dosar executare: <b>{case_ref}</b>", STYLE),
        Paragraph(f"Către: {BANK_NAME}", STYLE),
        Paragraph("ADRESĂ DE POPRIRE", TITLE),
        Paragraph(
            "Având în vedere prevederile Legii nr. 207/2015 privind Codul de procedură fiscală, vă comunicăm înființarea "
            f"popririi asupra conturilor deschise la unitatea dumneavoastră de către {debtor}, pentru neplata obligațiilor "
            "fiscale locale, după cum urmează:", STYLE),
        kv_table([("Debitor", debtor), ("Cod numeric personal", cnp), ("Adresa", address),
                  ("Obligații restante", details), ("TOTAL", f"{ro_amount(amount)} lei")]),
        Spacer(1, 6),
        Paragraph(f"Sumele vor fi virate în contul <b>{iban}</b> al bugetului local.", STYLE),
        Spacer(1, 16),
        Paragraph("Director executiv,<br/>(semnătură și ștampilă)", STYLE),
    ]
    return render(f)


def scanned(pdf_bytes: bytes) -> bytes:
    """Rasterises a PDF and degrades it like a scan: no text layer, slight rotation, noise."""
    page = pdfium.PdfDocument(pdf_bytes)[0]
    img = page.render(scale=1.6).to_pil().convert("L")
    noise = Image.effect_noise(img.size, 60)
    img = Image.blend(img, noise, 0.10)
    img = img.rotate(1.1, expand=True, fillcolor=255)
    buf = io.BytesIO()
    img.save(buf, "PDF", resolution=115)
    return buf.getvalue()


# ---------------------------------------------------------------- scenarios

BEJ_M = dict(bej="Marinescu Ovidiu", bej_address="Str. Doamnei nr. 9, Sector 3, București")
CONSEMNARE = "RO49AAAA1B31007593840000"
scenarios = []

if DOCS.exists():
    shutil.rmtree(DOCS)
DOCS.mkdir(parents=True)


def scenario(file, title, description, expected, pdf: bytes):
    (DOCS / file).write_bytes(pdf)
    scenarios.append({"file": file, "title": title, "description": description, "expected": expected})


def full(c):
    return f"{c['first_name']} {c['last_name']}"


scenario("01_executor_simplu.pdf", "Poprire simplă – executor judecătoresc",
         "Ion Popescu, datorie la o firmă de telefonie. Are bani suficienți în cont.",
         "Se blochează integral 5.000 lei și se trimite confirmarea către executor.",
         executor_doc(**BEJ_M, case_ref="1234/2026", reg_no="5521", debtor=full(ion), cnp=ion["cnp"], address=ion["address"],
                      amount=5000, creditor="SC TelcoNet Romania SA", title="contractul de abonament nr. 88412/2024, învestit cu formulă executorie",
                      claim_desc="facturi de telefonie neachitate", creditor_iban=CONSEMNARE))

scenario("02_anaf_cnp_gresit.pdf", "ANAF – CNP greșit cu o cifră",
         "Poprire fiscală pentru Maria Ionescu, dar CNP-ul din document are o cifră greșită.",
         "Agentul detectează cifra de control invalidă, găsește clientul corect și aplică poprirea (2.300 lei).",
         anaf_doc(unit="Administrația Județeană a Finanțelor Publice Cluj", case_ref="AJFP-CJ/90321/2026", reg_no="CJ-77120",
                  debtor=full(maria), cnp=corrupt_cnp(maria["cnp"]), address=maria["address"], amount=2300,
                  title="decizia de impunere nr. 4410/2025", treasury_iban="RO12TREZ2165067XXX012345"))

scenario("03_salariu_si_alocatie.pdf", "Cont cu salariu + alocație",
         "Elena Dumitrescu are în cont salariul și alocația copilului. Datorie de 4.000 lei.",
         "Alocația e protejată integral, din salariu se ia max. 1/3. Blocare parțială (~1.700 lei); poprirea rămâne activă.",
         executor_doc(**BEJ_M, case_ref="2210/2026", reg_no="5530", debtor=full(elena), cnp=elena["cnp"], address=elena["address"],
                      amount=4000, creditor="SC Mobila Expres SRL", title="sentința civilă nr. 1022/2025 a Judecătoriei Iași",
                      claim_desc="contravaloare bunuri cumpărate în rate și neachitate", creditor_iban=CONSEMNARE))

scenario("04_pensie_alimentara.pdf", "A doua poprire – pensie alimentară (prioritate)",
         "Gheorghe Stan are deja o poprire ANAF activă. Vine o poprire pentru pensie de întreținere a copilului.",
         "Pensia alimentară are prioritate față de creanța fiscală: blocările se recalculează pentru ambele popriri.",
         executor_doc(bej="Vasilescu Maria", bej_address="Bd. Unirii nr. 45, Sector 3, București", case_ref="3105/2026", reg_no="1180",
                      debtor=full(gheorghe), cnp=gheorghe["cnp"], address=gheorghe["address"], amount=3000,
                      creditor="Stan Larisa, în numele minorului Stan David", title="sentința civilă nr. 5512/2025 a Judecătoriei Sectorului 3",
                      claim_desc="pensie de întreținere restantă pentru copilul minor", creditor_iban=CONSEMNARE))

scenario("05_omonim_ambiguu.pdf", "Omonimi – identificare ambiguă",
         "Poprire pentru „Andrei Popa”, fără CNP lizibil. Banca are doi clienți cu acest nume pe aceeași stradă.",
         "Agentul nu poate decide singur și cere confirmarea unui operator uman.",
         executor_doc(**BEJ_M, case_ref="2987/2026", reg_no="5544", debtor="Andrei Popa", cnp="[indescifrabil]",
                      address="Str. Florilor nr. 1[?], Sector 3, București", amount=1200, creditor="SC Energie Plus SA",
                      title="contractul de furnizare nr. 55120/2023", claim_desc="facturi de energie electrică neachitate",
                      creditor_iban=CONSEMNARE))

scenario("06_ridicare_poprire.pdf", "Ridicare de poprire",
         "Executorul anunță că Vasile Georgescu a plătit datoria și cere deblocarea conturilor.",
         "Agentul recunoaște tipul de document, găsește poprirea GR-0002 și eliberează cei 2.000 lei blocați.",
         executor_doc(bej="Ionescu Adrian", bej_address="Str. Polonă nr. 12, Sector 1, București", case_ref="877/2025", reg_no="9012",
                      debtor=full(vasile), cnp=vasile["cnp"], address=vasile["address"], amount=2000,
                      creditor="SC Credit Rapid IFN SA", title="", claim_desc="", creditor_iban="", lift_of="7745/2025"))

scenario("07_debitor_inexistent.pdf", "Debitorul nu este client",
         "Poprire pentru Cristian Marin, care nu are conturi la bancă.",
         "Agentul confirmă că persoana nu e client și generează răspunsul „nu deține conturi”.",
         executor_doc(**BEJ_M, case_ref="3320/2026", reg_no="5561", debtor=full(cristian), cnp=cristian["cnp"], address=cristian["address"],
                      amount=8700, creditor="SC Auto Leasing SA", title="contractul de leasing nr. 3390/2022",
                      claim_desc="rate de leasing restante", creditor_iban=CONSEMNARE))

scenario("08_primarie_cont_euro.pdf", "Primărie – cont în euro",
         "Poprire de 6.000 lei pentru impozite locale; clienta Ana Constantinescu are doar cont în EUR.",
         "Agentul ia cursul BNR al zilei și blochează echivalentul în EUR.",
         primarie_doc(sector=1, case_ref="DGITL-S1/12004/2026", reg_no="44018", debtor=full(ana), cnp=ana["cnp"], address=ana["address"],
                      amount=6000, details="Impozit pe clădiri 2024–2025, taxă auto, majorări de întârziere",
                      iban="RO77TREZ7015007XXX008899"))

scenario("09_fonduri_insuficiente.pdf", "Fonduri insuficiente + încasare viitoare",
         "Mihai Radu are doar 150 lei. Datorie de 3.500 lei.",
         "Se blochează 150 lei, poprirea rămâne activă. Apoi: „Simulează încasare” salariu 5.000 lei → agentul se reactivează singur.",
         executor_doc(**BEJ_M, case_ref="3401/2026", reg_no="5570", debtor=full(mihai), cnp=mihai["cnp"], address=mihai["address"],
                      amount=3500, creditor="SC Fitness Club SRL", title="sentința civilă nr. 220/2026 a Judecătoriei Timișoara",
                      claim_desc="abonamente neachitate și penalități", creditor_iban=CONSEMNARE))

scenario("10_scanat.pdf", "Document scanat (fără text)",
         "Poprire pentru Ioana Stoica primită ca scan (imagine), ușor rotit și cu zgomot.",
         "Extragerea de text eșuează; agentul trece automat pe citire vizuală (imagine) și continuă.",
         scanned(executor_doc(**BEJ_M, case_ref="3455/2026", reg_no="5583", debtor=full(ioana), cnp=ioana["cnp"], address=ioana["address"],
                              amount=1500, creditor="SC Clinica Medicală Mare SRL", title="sentința civilă nr. 870/2026 a Judecătoriei Constanța",
                              claim_desc="servicii medicale neachitate", creditor_iban=CONSEMNARE)))

scenario("11_duplicat_email.pdf", "Duplicat (aceeași poprire, primită și pe e-mail)",
         "Copia trimisă pe e-mail a popririi din scenariul 1. Rulați-l DUPĂ scenariul 1.",
         "Agentul detectează dosarul deja înregistrat și nu blochează banii a doua oară.",
         executor_doc(**BEJ_M, case_ref="1234/2026", reg_no="5521", debtor=full(ion), cnp=ion["cnp"], address=ion["address"],
                      amount=5000, creditor="SC TelcoNet Romania SA", title="contractul de abonament nr. 88412/2024, învestit cu formulă executorie",
                      claim_desc="facturi de telefonie neachitate", creditor_iban=CONSEMNARE,
                      banner="COPIE – document transmis și prin e-mail la executari@bancademo.ro"))


def main():
    seed = {"generated_at": datetime.now().isoformat(timespec="seconds"), "bank": BANK_NAME, "clients": clients,
            "accounts": accounts, "transactions": transactions, "garnishments": garnishments, "holds": holds}
    (OUT / "seed.json").write_text(json.dumps(seed, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT / "scenarios.json").write_text(json.dumps(scenarios, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Generated {len(clients)} clients, {len(accounts)} accounts, {len(transactions)} transactions, {len(scenarios)} documents in {OUT}")


if __name__ == "__main__":
    main()
