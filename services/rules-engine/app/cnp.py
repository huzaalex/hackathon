"""Romanian personal numeric code (CNP) validation and typo correction.

Structure: S YY MM DD JJ NNN C
  S   sex + century, JJ county code, NNN sequence, C control digit
  C = (sum(digit_i * key_i) mod 11), with 10 -> 1, key = 279146358279
"""

from datetime import date

CONTROL_KEY = "279146358279"

COUNTIES = {
    1: "Alba", 2: "Arad", 3: "Argeș", 4: "Bacău", 5: "Bihor", 6: "Bistrița-Năsăud", 7: "Botoșani", 8: "Brașov",
    9: "Brăila", 10: "Buzău", 11: "Caraș-Severin", 12: "Cluj", 13: "Constanța", 14: "Covasna", 15: "Dâmbovița",
    16: "Dolj", 17: "Galați", 18: "Gorj", 19: "Harghita", 20: "Hunedoara", 21: "Ialomița", 22: "Iași", 23: "Ilfov",
    24: "Maramureș", 25: "Mehedinți", 26: "Mureș", 27: "Neamț", 28: "Olt", 29: "Prahova", 30: "Satu Mare",
    31: "Sălaj", 32: "Sibiu", 33: "Suceava", 34: "Teleorman", 35: "Timiș", 36: "Tulcea", 37: "Vaslui", 38: "Vâlcea",
    39: "Vrancea", 40: "Bucharest", 41: "Bucharest Sector 1", 42: "Bucharest Sector 2", 43: "Bucharest Sector 3", 44: "Bucharest Sector 4",
    45: "Bucharest Sector 5", 46: "Bucharest Sector 6", 51: "Călărași", 52: "Giurgiu", 70: "Any county (CNP issued after 2024)",
}

CENTURY_BY_SEX_DIGIT = {1: 1900, 2: 1900, 3: 1800, 4: 1800, 5: 2000, 6: 2000}


def control_digit(first12: str) -> int:
    r = sum(int(a) * int(b) for a, b in zip(first12, CONTROL_KEY)) % 11
    return 1 if r == 10 else r


def _birth_date(cnp: str) -> date | None:
    s = int(cnp[0])
    yy, mm, dd = int(cnp[1:3]), int(cnp[3:5]), int(cnp[5:7])
    if s in CENTURY_BY_SEX_DIGIT:
        year = CENTURY_BY_SEX_DIGIT[s] + yy
    else:  # 7/8 residents, 9 foreigners: century is not encoded, pick the plausible one
        year = 2000 + yy if 2000 + yy <= date.today().year else 1900 + yy
    try:
        return date(year, mm, dd)
    except ValueError:
        return None


def validate(cnp: str) -> dict:
    cnp = (cnp or "").strip().replace(" ", "")
    errors: list[str] = []
    if len(cnp) != 13 or not cnp.isdigit():
        return {"cnp": cnp, "valid": False, "errors": ["The CNP must have exactly 13 digits"]}

    if cnp[0] == "0":
        errors.append("The first digit (sex/century) cannot be 0")
    birth = _birth_date(cnp)
    if birth is None:
        errors.append("The birth date encoded in the CNP is not a valid date")
    county = int(cnp[7:9])
    if county not in COUNTIES:
        errors.append(f"County code {cnp[7:9]} does not exist")
    if cnp[9:12] == "000":
        errors.append("The sequence number NNN cannot be 000")
    expected = control_digit(cnp[:12])
    checksum_ok = expected == int(cnp[12])
    if not checksum_ok:
        errors.append(f"The check digit is {cnp[12]} but should be {expected} (likely a typing or OCR error)")

    return {
        "cnp": cnp,
        "valid": not errors,
        "checksum_ok": checksum_ok,
        "errors": errors,
        "sex": "M" if cnp[0] in "1357" else "F" if cnp[0] in "2468" else None,
        "birth_date": birth.isoformat() if birth else None,
        "county_code": cnp[7:9],
        "county": COUNTIES.get(county),
    }


def suggest_corrections(cnp: str, limit: int = 40) -> list[str]:
    """Structurally valid CNPs at edit distance 1 (one wrong digit or two swapped adjacent digits)."""
    cnp = (cnp or "").strip().replace(" ", "")
    if len(cnp) != 13 or not cnp.isdigit():
        return []
    candidates: list[str] = []
    for i in range(13):
        for d in "0123456789":
            if d != cnp[i]:
                candidates.append(cnp[:i] + d + cnp[i + 1:])
    for i in range(12):
        if cnp[i] != cnp[i + 1]:
            candidates.append(cnp[:i] + cnp[i + 1] + cnp[i] + cnp[i + 2:])
    valid = [c for c in dict.fromkeys(candidates) if validate(c)["valid"]]
    return valid[:limit]
