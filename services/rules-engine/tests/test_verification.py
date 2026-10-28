from app.verification import check_document, find_bailiff, verify_iban


def make_iban(bank: str, account: str) -> str:
    numeric = "".join(str(int(c, 36)) for c in bank + account + "RO00")
    return f"RO{98 - int(numeric) % 97:02d}{bank}{account}"


def test_valid_and_invalid_iban():
    good = make_iban("CECE", "B310075938400000")
    assert verify_iban(good)["valid"]
    assert verify_iban(good)["bank_name"] == "CEC Bank"
    bad = good[:-1] + ("1" if good[-1] != "1" else "2")
    assert not verify_iban(bad)["valid"]
    assert not verify_iban("RO12")["valid"]


def test_treasury_iban_with_letters_is_valid():
    r = verify_iban(make_iban("TREZ", "2165067XXX012345"))
    assert r["valid"] and r["is_treasury"]


def test_registry_lookup_ignores_diacritics_and_prefix():
    assert find_bailiff("BIROUL EXECUTORULUI JUDECĂTORESC MARINESCU OVIDIU")
    assert not find_bailiff("BEJ Popovici Dan")


def test_genuine_bailiff_order_is_low_risk():
    r = check_document("BAILIFF", "BEJ Marinescu Ovidiu", make_iban("CECE", "B310075938400000"), "1234/2026", "27.10.2026")
    assert r["risk_level"] == "LOW"


def test_forged_order_is_high_risk():
    good = make_iban("BTRL", "RONCRT0412345678")
    forged_iban = good[:2] + ("00" if good[2:4] != "00" else "01") + good[4:]
    r = check_document("BAILIFF", "BEJ Popovici Dan", forged_iban, "EX-77/2026", None)
    assert r["risk_level"] == "HIGH"


def test_tax_authority_must_collect_into_treasury():
    r = check_document("TAX_AUTHORITY", "ANAF", make_iban("BTRL", "RONCRT0412345678"), "X/1", None)
    assert any(c["id"] == "treasury_account" and c["status"] == "FAIL" for c in r["checks"])
