"""One test per claim check, on hand-made records. No data files, no key."""
from agent import rules

CITE = {"file": "x.csv", "rows": [2], "snapshot": "2026-09-30"}


def rec(*rows, found=True):
    return {"found": found and bool(rows), "rows": list(rows), "citation": CITE if rows else None}


def claim(**kw):
    base = {"claim_no": "CLM-1", "claim_date": "2026-06-01", "stockist_code": "STK0001", "sku_code": "PFL1001",
            "batch_no": "K2300101", "qty_claimed": 10, "claim_type": "Near expiry", "invoice_ref": "INV/1",
            "claim_value_inr": 714.0, "expiry_date_as_claimed": "2026-07-31"}
    return {**base, **kw}


def records(**kw):
    base = {
        "batch": {**rec({"batch_no": "K2300101", "sku_code": "PFL1001", "mfg_date": "2024-08-01",
                         "expiry_date": "2026-07-31"}),
                  "sku": rec({"sku_code": "PFL1001", "pts_inr": "71.4"}), "corrected": None},
        "supplies": rec({"invoiced_qty": "20", "free_qty": "0"}),
        "prior_claims": rec(),
        "invoice": rec({"invoice_date": "2026-05-28", "stockist_code": "STK0001", "batch_no": "K2300101"}),
    }
    return {**base, **kw}


def test_duplicate_rejects_same_qty_claimed_before():
    r = records(prior_claims=rec({"claim_no": "CLM-0", "claim_date": "2026-05-01", "qty_claimed": "10", "status": "Credited"}))
    out = rules.chk_duplicate(claim(), r)
    assert out["outcome"] == "fail" and out["on_fail"] == "reject"


def test_duplicate_only_counts_earlier_claims():
    r = records(prior_claims=rec({"claim_no": "CLM-2", "claim_date": "2026-07-01", "qty_claimed": "10", "status": "Credited"}))
    assert rules.chk_duplicate(claim(), r)["outcome"] == "pass"


def test_any_claim_type_over_90_days_after_expiry_is_rejected():
    for kind in ("Near expiry", "Short supply"):
        out = rules.chk_window(claim(claim_type=kind, claim_date="2026-11-15"), records())
        assert out["outcome"] == "fail" and out["on_fail"] == "reject", kind


def test_duplicate_ignores_rejected_claims():
    r = records(prior_claims=rec({"claim_no": "CLM-0", "qty_claimed": "10", "status": "Rejected"}))
    assert rules.chk_duplicate(claim(), r)["outcome"] == "pass"


def test_window_rejects_expired_claim_over_90_days_late():
    out = rules.chk_window(claim(claim_type="Expired", claim_date="2026-12-01"), records())
    assert out["outcome"] == "fail" and out["on_fail"] == "reject"


def test_window_sends_early_near_expiry_to_person():
    out = rules.chk_window(claim(claim_date="2026-01-01"), records())
    assert out["outcome"] == "fail" and out["on_fail"] == "to_person"


def test_window_rejects_breakage_after_7_days():
    out = rules.chk_window(claim(claim_type="Breakage in transit", claim_date="2026-06-10"), records())
    assert out["outcome"] == "fail" and out["on_fail"] == "reject"


def test_supplied_rejects_batch_never_billed():
    assert rules.chk_supplied(claim(), records(supplies=rec()))["outcome"] == "fail"


def test_quantity_counts_earlier_claims_and_free_packs():
    r = records(supplies=rec({"invoiced_qty": "10", "free_qty": "2"}),
                prior_claims=rec({"claim_no": "CLM-0", "qty_claimed": "5", "status": "Credited"}))
    out = rules.chk_quantity(claim(), r)
    assert out["outcome"] == "fail" and "excess 3" in out["detail"]


def test_invoice_ref_missing_goes_to_person():
    out = rules.chk_invoice_ref(claim(invoice_ref=None), records())
    assert out["outcome"] == "fail" and out["on_fail"] == "to_person"


def test_batch_made_before_oct_2023_is_unverifiable():
    r = records()
    r["batch"]["rows"][0]["mfg_date"] = "2023-06-01"
    assert rules.chk_batch(claim(), r)["outcome"] == "flag"


def test_value_must_equal_qty_times_pts():
    assert rules.chk_value(claim(), records())["outcome"] == "pass"
    assert rules.chk_value(claim(claim_value_inr=900), records())["outcome"] == "fail"


def test_decide_reject_beats_person_and_clean_is_not_approval():
    fail_reject = {"outcome": "fail", "on_fail": "reject"}
    flag = {"outcome": "flag", "on_fail": "to_person"}
    ok = {"outcome": "pass", "on_fail": "reject"}
    assert rules.decide({"a": fail_reject, "b": flag}) == "reject"
    assert rules.decide({"a": ok, "b": flag}) == "to_person"
    assert rules.decide({"a": ok}) == "clean"


# --- Input checks, CFA rule and recommendation (ADR 0012) ---------------------------------
from datetime import date as _date  # noqa: E402

import pytest  # noqa: E402


def _claim(**kw):
    return {"claim_no": "X", "claim_date": "2026-07-29", "qty_claimed": 10, "claim_type": "Near expiry", **kw}


@pytest.mark.parametrize("qty", [-38, 0, 0.5, "abc", None])
def test_impossible_quantities_never_reach_the_rules(qty):
    assert any("quantity" in p.lower() for p in rules.input_problems(_claim(qty_claimed=qty), _date(2026, 11, 20)))


def test_future_date_and_unknown_type_are_input_problems():
    problems = rules.input_problems(_claim(claim_date="2030-01-01", claim_type="Damaged"), _date(2026, 11, 20))
    assert any("future" in p for p in problems) and any("Damaged" in p for p in problems)
    assert rules.input_problems(_claim(), _date(2026, 11, 20)) == []


def _supplies(*cfas):
    return {"supplies": {"found": True, "rows": [{"cnf_code": c, "invoiced_qty": "100", "free_qty": "10"} for c in cfas],
                         "citation": None}}


def test_claim_lodged_at_another_cfa_goes_to_a_person():
    r = rules.chk_cfa(_claim(cnf_code="CF-N01"), _supplies("CF-E01"))
    assert r["outcome"] == "fail" and r["on_fail"] == "to_person" and "CF-E01" in r["detail"]
    assert rules.chk_cfa(_claim(cnf_code="CF-E01"), _supplies("CF-E01"))["outcome"] == "pass"
    assert rules.chk_cfa(_claim(), {"supplies": {"found": False, "rows": []}})["outcome"] == "skip"


def _rec(route, bad, qty=150, earlier=()):
    checks = {k: {"outcome": "pass"} for k in rules.CHECKS}
    for k in bad:
        checks[k] = {"outcome": "fail"}
    records = {**_supplies("CF-E01"), "batch": {"sku": {"found": True, "rows": [{"pts_inr": "10.5"}]}},
               "prior_claims": {"rows": [{"claim_no": f"E{i}", "qty_claimed": q, "status": "Credited"}
                                         for i, q in enumerate(earlier)]}}
    return rules.recommend(_claim(qty_claimed=qty), checks, records, route)


def test_recommendation_in_packs_and_rupees():
    assert _rec("clean", [], qty=100) == {"action": "approve", "qty": 100, "credit_inr": 1050.0, "reason_codes": []}
    assert _rec("reject", ["chk_window"])["reason_codes"] == ["OUT_OF_WINDOW"]
    part = _rec("to_person", ["chk_quantity"], qty=150, earlier=[30])  # 110 supplied, 30 claimed before
    assert (part["action"], part["qty"], part["credit_inr"]) == ("approve_part", 80, 840.0)
    assert _rec("to_person", ["chk_quantity"], qty=50, earlier=[110])["action"] == "reject"  # nothing left
    review = _rec("to_person", ["chk_quantity", "chk_invoice_ref"])
    assert review["action"] == "review" and review["credit_inr"] is None
