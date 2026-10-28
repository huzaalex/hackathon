"""Deterministic authenticity checks for incoming garnishment documents.

Forged garnishment / release letters are a known fraud vector against banks. These checks are the
non-negotiable part of the authenticity review; the AI agent adds judgement on the text on top of them.
"""

import re
import unicodedata
from datetime import date, datetime

# Subset of Romanian IBAN bank identifiers (characters 5-8 of a RO IBAN)
BANK_CODES = {
    "TREZ": "State Treasury (Trezoreria Statului)",
    "CECE": "CEC Bank",
    "BTRL": "Banca Transilvania",
    "BRDE": "BRD - Groupe Societe Generale",
    "RNCB": "Banca Comerciala Romana (BCR)",
    "INGB": "ING Bank",
    "RZBR": "Raiffeisen Bank",
    "BACX": "UniCredit Bank",
    "OTPV": "OTP Bank",
    "BREL": "Libra Internet Bank",
    "CARP": "Patria Bank",
    "WBAN": "Intesa Sanpaolo Bank",
    "PIRB": "First Bank",
    "DEMO": "Banca Demo S.A. (this bank)",
}

# SIMULATED snapshot of the public register of bailiffs (UNEJ), for the demo only.
BAILIFF_REGISTRY = [
    {"name": "Marinescu Ovidiu", "chamber": "Bucuresti", "office": "Str. Doamnei nr. 9, Sector 3, Bucuresti", "status": "ACTIVE"},
    {"name": "Vasilescu Maria", "chamber": "Bucuresti", "office": "Bd. Unirii nr. 45, Sector 3, Bucuresti", "status": "ACTIVE"},
    {"name": "Ionescu Adrian", "chamber": "Bucuresti", "office": "Str. Polona nr. 12, Sector 1, Bucuresti", "status": "ACTIVE"},
    {"name": "Dobre Cristina", "chamber": "Bucuresti", "office": "Calea Victoriei nr. 120, Sector 1, Bucuresti", "status": "ACTIVE"},
    {"name": "Muresan Ioan", "chamber": "Cluj", "office": "Str. Horea nr. 3, Cluj-Napoca", "status": "ACTIVE"},
    {"name": "Lungu Petru", "chamber": "Iasi", "office": "Str. Pacurari nr. 18, Iasi", "status": "ACTIVE"},
    {"name": "Stanciu Elena", "chamber": "Timisoara", "office": "Bd. Revolutiei nr. 5, Timisoara", "status": "ACTIVE"},
    {"name": "Georgescu Radu", "chamber": "Constanta", "office": "Str. Mircea cel Batran nr. 40, Constanta", "status": "ACTIVE"},
    {"name": "Nistor Alina", "chamber": "Bucuresti", "office": "Str. Turturelelor nr. 11, Sector 3, Bucuresti", "status": "SUSPENDED"},
]

PUBLIC_AUTHORITIES = {"TAX_AUTHORITY", "LOCAL_TAX_AUTHORITY"}
HARD_CHECKS = {"iban_checksum", "bailiff_registry", "treasury_account", "document_date"}


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    return "".join(c for c in s if not unicodedata.combining(c)).lower()


def verify_iban(iban: str | None) -> dict:
    raw = re.sub(r"\s+", "", (iban or "")).upper()
    if not raw:
        return {"iban": None, "valid": False, "reason": "No IBAN in the document"}
    if not re.fullmatch(r"[A-Z]{2}\d{2}[A-Z0-9]{8,30}", raw):
        return {"iban": raw, "valid": False, "reason": "Malformed IBAN"}
    country = raw[:2]
    if country == "RO" and len(raw) != 24:
        return {"iban": raw, "valid": False, "country": country, "reason": f"A Romanian IBAN has 24 characters, this one has {len(raw)}"}
    numeric = "".join(str(int(c, 36)) for c in raw[4:] + raw[:4])
    if int(numeric) % 97 != 1:
        return {"iban": raw, "valid": False, "country": country, "reason": "The IBAN check digits are wrong (mistyped or forged)"}
    bank_code = raw[4:8] if country == "RO" else None
    return {"iban": raw, "valid": True, "country": country, "bank_code": bank_code,
            "bank_name": BANK_CODES.get(bank_code) if bank_code else None,
            "is_treasury": bank_code == "TREZ"}


def find_bailiff(issuer_name: str | None) -> list[dict]:
    text = norm(issuer_name)
    return [b for b in BAILIFF_REGISTRY if all(tok in text for tok in norm(b["name"]).split())]


def _parse_date(value: str | None) -> date | None:
    for fmt in ("%d.%m.%Y", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime((value or "").strip(), fmt).date()
        except ValueError:
            continue
    return None


def check_document(issuer_type: str, issuer_name: str | None, payment_iban: str | None,
                   case_number: str | None, document_date: str | None) -> dict:
    checks: list[dict] = []

    def add(cid, label, status, detail):
        checks.append({"id": cid, "label": label, "status": status, "detail": detail})

    # 1. payment account
    iban = verify_iban(payment_iban)
    if iban["valid"]:
        add("iban_checksum", "Payment IBAN is valid", "PASS", f"{iban['iban']} ({iban.get('bank_name') or 'bank code ' + str(iban.get('bank_code'))})")
        if iban.get("country") != "RO":
            add("iban_country", "Payment account is in Romania", "WARN", f"Foreign account ({iban['country']})")
        elif not iban.get("bank_name"):
            add("iban_bank", "Payment bank is known", "WARN", f"Unknown bank code {iban.get('bank_code')}")
    elif payment_iban:
        add("iban_checksum", "Payment IBAN is valid", "FAIL", iban["reason"])
    else:
        add("iban_checksum", "Payment IBAN is valid", "SKIP", "The document does not state a payment account")

    if issuer_type in PUBLIC_AUTHORITIES:
        if iban["valid"] and not iban.get("is_treasury"):
            add("treasury_account", "Public authority collects into a Treasury account", "FAIL",
                f"Payment requested into {iban.get('bank_name') or 'a non-Treasury account'}, not the State Treasury")
        elif iban["valid"]:
            add("treasury_account", "Public authority collects into a Treasury account", "PASS", "Treasury (TREZ) account")

    # 2. issuer exists
    if issuer_type == "BAILIFF":
        found = find_bailiff(issuer_name)
        if not found:
            add("bailiff_registry", "Bailiff is in the public register", "FAIL", f"No bailiff matching \"{issuer_name}\" in the register")
        elif all(b["status"] != "ACTIVE" for b in found):
            add("bailiff_registry", "Bailiff is in the public register", "FAIL", f"{found[0]['name']} is registered but {found[0]['status'].lower()}")
        else:
            b = next(b for b in found if b["status"] == "ACTIVE")
            add("bailiff_registry", "Bailiff is in the public register", "PASS", f"{b['name']}, {b['chamber']} chamber, active")

    # 3. case number format (bailiff files look like 1234/2026)
    if issuer_type == "BAILIFF":
        m = re.fullmatch(r"\s*(\d{1,6})\s*/\s*(\d{4})\s*", case_number or "")
        if not case_number:
            add("case_number", "Case number has a plausible format", "WARN", "No case number")
        elif not m or not 2000 <= int(m.group(2)) <= date.today().year:
            add("case_number", "Case number has a plausible format", "WARN", f"Unusual case number \"{case_number}\"")
        else:
            add("case_number", "Case number has a plausible format", "PASS", case_number)

    # 4. document date
    d = _parse_date(document_date)
    if d is None:
        add("document_date", "Document date is plausible", "SKIP", "No readable date")
    elif d > date.today():
        add("document_date", "Document date is plausible", "FAIL", f"Dated in the future ({d.isoformat()})")
    elif (date.today() - d).days > 730:
        add("document_date", "Document date is plausible", "WARN", f"More than two years old ({d.isoformat()})")
    else:
        add("document_date", "Document date is plausible", "PASS", d.isoformat())

    hard_fails = sum(1 for c in checks if c["status"] == "FAIL" and c["id"] in HARD_CHECKS)
    warns = sum(1 for c in checks if c["status"] == "WARN")
    risk = "HIGH" if hard_fails >= 2 else "MEDIUM" if hard_fails == 1 or warns >= 2 else "LOW"
    return {"checks": checks, "risk_level": risk, "hard_fails": hard_fails, "warnings": warns}
