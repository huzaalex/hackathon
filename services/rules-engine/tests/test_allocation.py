import pytest

from app.allocation import AccountIn, AllocationRequest, GarnishmentIn, allocate


def run(accounts, garnishments):
    return allocate(AllocationRequest(accounts=[AccountIn(**a) for a in accounts],
                                      garnishments=[GarnishmentIn(**g) for g in garnishments]))


def test_full_coverage_without_protected_income():
    r = run([{"iban": "A", "balance": 12450, "inflows": {"TRANSFER": 4200}}],
            [{"id": "NOU", "claim_type": "UNSECURED", "amount_ron": 5000, "received_at": "2026-10-01"}])
    assert r["total_blocked_ron"] == 5000
    assert r["garnishments"][0]["fully_covered"]


def test_child_allowance_is_protected_and_salary_limited_to_one_third():
    # balance 5219 = 300 + salary 4200 + allowance 719
    r = run([{"iban": "A", "balance": 5219, "inflows": {"SALARY": 4200, "CHILD_ALLOWANCE": 719}}],
            [{"id": "NOU", "claim_type": "UNSECURED", "amount_ron": 4000, "received_at": "2026-10-01"}])
    # protected = 719 + 2/3 * 4200 = 3519 -> seizable 1700
    assert r["total_blocked_ron"] == 1700
    assert r["garnishments"][0]["remaining_ron"] == 2300


def test_alimony_has_priority_over_tax_claim():
    r = run([{"iban": "A", "balance": 4800, "inflows": {"SALARY": 4500}}],
            [{"id": "ANAF", "claim_type": "TAX", "amount_ron": 6000, "received_at": "2026-09-01"},
             {"id": "NOU", "claim_type": "CHILD_SUPPORT", "amount_ron": 3000, "received_at": "2026-10-20"}])
    by_id = {g["id"]: g for g in r["garnishments"]}
    # alimony cap = 4800 - 1/2*4500 = 2550 ; tax cap = 4800 - 2/3*4500 = 1800, already exceeded
    assert by_id["NOU"]["allocated_ron"] == 2550
    assert by_id["ANAF"]["allocated_ron"] == 0
    assert r["garnishments"][0]["id"] == "NOU"


def test_foreign_currency_account_converted():
    r = run([{"iban": "E", "currency": "EUR", "balance": 3000, "fx_to_ron": 5.0}],
            [{"id": "NOU", "claim_type": "TAX", "amount_ron": 6000, "received_at": "2026-10-01"}])
    assert r["holds"][0]["amount"] == 1200
    assert r["holds"][0]["amount_ron"] == 6000


def test_closed_accounts_ignored_and_ron_first():
    r = run([{"iban": "E", "currency": "EUR", "balance": 1000, "fx_to_ron": 5.0},
             {"iban": "C", "balance": 9999, "status": "CLOSED"},
             {"iban": "R", "balance": 1000}],
            [{"id": "NOU", "claim_type": "UNSECURED", "amount_ron": 1500, "received_at": "2026-10-01"}])
    assert [h["iban"] for h in r["holds"]] == ["R", "E"]
    assert r["holds"][1]["amount"] == 100


def test_unknown_claim_type_rejected():
    with pytest.raises(ValueError):
        run([{"iban": "A", "balance": 100}], [{"id": "X", "claim_type": "SOMETHING_ELSE", "amount_ron": 1, "received_at": "x"}])
