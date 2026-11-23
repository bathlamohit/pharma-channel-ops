"""Input validation: null, empty, wrong type, wrong format, extremes and unicode on every write endpoint."""
import pytest

FORM = {"stockist_code": "STK0096", "entered_by": "QA Synthetic", "received_date": "2026-08-29",
        "lines": [{"batch_no": "F2420525", "qty_claimed": 10, "invoice_ref": "INV/W01/2501/026732"}]}

CASES = [
    # (id, endpoint, body, expected status)
    ("TC-VAL-001", "/api/intake/form", {**FORM, "stockist_code": None}, 422),
    ("TC-VAL-002", "/api/intake/form", {**FORM, "stockist_code": ""}, 422),
    ("TC-VAL-003", "/api/intake/form", {**FORM, "stockist_code": "STK9999"}, 422),
    ("TC-VAL-004", "/api/intake/form", {**FORM, "entered_by": "A"}, 422),
    ("TC-VAL-005", "/api/intake/form", {**FORM, "entered_by": "x" * 81}, 422),
    ("TC-VAL-006", "/api/intake/form", {**FORM, "lines": None}, 422),
    ("TC-VAL-007", "/api/intake/form", {**FORM, "lines": [{"batch_no": "F2420525", "qty_claimed": "ten"}]}, 422),
    ("TC-VAL-008", "/api/intake/form", {**FORM, "received_date": "2026-02-30"}, 422),
    ("TC-VAL-009", "/api/intake/form", {**FORM, "received_date": "2099-12-31"}, 422),
    ("TC-VAL-010", "/api/intake/form", {**FORM, "lines": [{"batch_no": "F" * 21, "qty_claimed": 1}]}, 422),
    ("TC-VAL-011", "/api/intake/form", {**FORM, "entered_by": "Ananya Iyer-Ramakrishnan ✓ अनन्या"}, 200),
    ("TC-VAL-012", "/api/intake/form", {**FORM, "received_date": "2024-01-01"}, 200),
    ("TC-VAL-020", "/api/intake/email", {"body": "batch F2420525 10 strips", "stockist_code": "STK0096", "from_name": "y" * 121}, 422),
    ("TC-VAL-021", "/api/intake/email", {"body": None}, 422),
    ("TC-VAL-022", "/api/intake/email", {}, 422),
    ("TC-VAL-023", "/api/intake/email", {"body": "batch F2420525 10 strips", "stockist_code": "STK0096", "subject": "s" * 301}, 422),
    ("TC-VAL-030", "/api/stock/action", {"cnf_code": "CF-E01", "step": "Raised with CFA", "by": None}, 422),
    ("TC-VAL-031", "/api/stock/action", {"cnf_code": "CF-E01", "step": "Raised with CFA", "by": "QA", "qty": -1}, 422),
    ("TC-VAL-032", "/api/stock/action", {"cnf_code": "CF-E01", "step": "Raised with CFA", "by": "QA", "qty": 1.5}, 422),
    ("TC-VAL-033", "/api/stock/action", {"cnf_code": "CF-E01", "step": "Raised with CFA", "by": "QA", "note": "n" * 501}, 422),
    ("TC-VAL-034", "/api/stock/action", {"cnf_code": "", "step": "Raised with CFA", "by": "QA"}, 422),
    ("TC-VAL-035", "/api/stock/action", {"cnf_code": "CF-E01", "step": None, "by": "QA"}, 422),
    ("TC-VAL-040", "/api/decision", {"audit_id": "abcdef12", "decided_by": "QA", "decision": "approve", "note": "n" * 1001}, 422),
    ("TC-VAL-041", "/api/decision", {"audit_id": "a" * 65, "decided_by": "QA", "decision": "approve"}, 422),
    ("TC-VAL-042", "/api/decision", {"audit_id": "abcdef12", "decided_by": "QA", "decision": "approve", "recommended": "maybe"}, 422),
    ("TC-VAL-050", "/api/intake/status", {"claim_no": "CLM-2611-04519", "status": "Verified", "by": "QA", "credit_note_no": "c" * 41}, 422),
    ("TC-VAL-060", "/api/source", {"file": "sku_master.csv", "rows": "2,3"}, 422),
    ("TC-VAL-061", "/api/source", {"file": "sku_master.csv", "rows": []}, 200),
    ("TC-VAL-062", "/api/source", {"file": "sku_master.csv", "rows": [999999]}, 200),
]


@pytest.mark.parametrize("tc,url,body,status", CASES, ids=[c[0] for c in CASES])
def test_validation(api, tc, url, body, status):
    """TC-VAL-0xx | Input validation | ADR 0012, 0013, 0014 | Null, empty, wrong type, format, length and range are refused; valid unicode and historical dates accepted"""
    r = api.post(url, json=body)
    assert r.status_code == status, r.text[:300]


def test_unicode_name_is_stored_exactly(api):
    """TC-VAL-070 | Data integrity | ADR 0013 | A unicode name is stored and returned unchanged"""
    name = "Ananya Iyer-Ramakrishnan ✓ अनन्या"
    no = api.post("/api/intake/form", json={**FORM, "entered_by": name}).json()["registered"][0]
    c = next(x for x in api.get("/api/intake").json() if x["claim_no"] == no)
    assert c["by"] == name


def test_missing_row_is_reported_not_invented(api):
    """TC-VAL-071 | Data integrity | ADR 0004 | A cited row that does not exist is reported as missing"""
    r = api.post("/api/source", json={"file": "sku_master.csv", "rows": [999999]}).json()
    assert r["rows"] == [] and r["missing"] == [999999]
