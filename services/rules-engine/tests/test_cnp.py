from app.cnp import control_digit, suggest_corrections, validate


def make(first12: str) -> str:
    return first12 + str(control_digit(first12))


def test_valid_cnp():
    cnp = make("185031242015")
    r = validate(cnp)
    assert r["valid"]
    assert r["sex"] == "M"
    assert r["birth_date"] == "1985-03-12"
    assert r["county"] == "București S2"


def test_wrong_checksum_detected():
    cnp = make("185031242015")
    bad = cnp[:12] + str((int(cnp[12]) + 1) % 10)
    r = validate(bad)
    assert not r["valid"]
    assert not r["checksum_ok"]


def test_invalid_date_and_length():
    assert not validate(make("185023042015"))["valid"]  # 30 February
    assert not validate("12345")["valid"]


def test_suggestions_recover_single_digit_typo():
    cnp = make("290072312087")
    typo = cnp[:9] + ("0" if cnp[9] != "0" else "1") + cnp[10:]
    if validate(typo)["valid"]:  # extremely unlikely, typo happened to be valid
        return
    assert cnp in suggest_corrections(typo)


def test_suggestions_recover_swapped_digits():
    cnp = make("290072312087")
    swapped = cnp[:3] + cnp[4] + cnp[3] + cnp[5:]
    if swapped != cnp and not validate(swapped)["valid"]:
        assert cnp in suggest_corrections(swapped)
