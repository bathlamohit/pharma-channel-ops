"""Regression tests for the QA report of 21 Nov 2026 (docs/qa-report-2026-11-21.md), one per bug."""
from fastapi.testclient import TestClient

import agent.claim_nodes as nodes
from app import app

client = TestClient(app)


def no_model():
    raise AssertionError("the model was called")


def check(claim_no, monkeypatch):
    monkeypatch.setattr(nodes, "get_llm", no_model)
    return client.post("/api/claim/register", json={"claim_no": claim_no}).json()["audit_id"]


def decide(audit_id, who, decision, note=""):
    return client.post("/api/decision", json={"audit_id": audit_id, "decided_by": who, "decision": decision, "note": note})


def test_b1_a_claim_cannot_be_approved_twice(monkeypatch):
    first = check("CLM-2606-02056", monkeypatch)
    assert decide(first, "Exec A", "approve").status_code == 200
    assert decide(first, "Exec B", "approve").status_code == 409              # same audit id
    again = check("CLM-2606-02056", monkeypatch)                              # checked again: new audit id
    assert again != first
    r = decide(again, "Exec C", "approve")
    assert r.status_code == 409 and "Exec A" in r.json()["detail"]
    assert decide(again, "Exec C", "hold").status_code == 422                 # a change needs a reason
    assert decide(again, "Exec C", "hold", "Stockist disputes the pack count").json()["changes"]["decided_by"] == "Exec A"


def test_b1_email_claims_are_one_subject(monkeypatch):
    monkeypatch.setattr(nodes, "get_llm", no_model)
    a = client.post("/api/claim/email", json={"email_id": "EML-001"}).json()["audit_id"]
    b = client.post("/api/claim/email", json={"email_id": "EML-001"}).json()["audit_id"]
    assert decide(a, "Exec A", "approve").status_code == 200
    assert decide(b, "Exec B", "approve").status_code == 409


def test_b2_unknown_audit_id_is_refused_where_the_log_is_kept(monkeypatch):
    check("CLM-2606-02056", monkeypatch)  # the server now keeps a log
    assert decide("zzzzzz999", "Exec", "approve").status_code == 404


def step(**kw):
    return client.post("/api/stock/action", json={"cnf_code": "CF-E01", "by": "QA Tester", **kw})


def test_b3_steps_must_be_about_something_in_the_plan():
    assert step(cnf_code="XX-999", step="Raised with CFA").status_code == 422
    assert step(sku_code="PFL0000", step="Allocation raised").status_code == 422
    assert step(batch_no="NOPE123", sku_code="PFL1004", step="Blocked in SAP").status_code == 422
    assert step(batch_no="A2600468", sku_code="PFL1201", step="Return requested").status_code == 422  # wrong product
    assert step(step="Raised with NSM").status_code == 422                       # scheme steps are national
    assert step(cnf_code="NATIONAL", step="Raised with CFA").status_code == 422
    assert step(cnf_code="NATIONAL", step="Raised with NSM").status_code == 200


def test_b4_a_step_is_recorded_once():
    item = {"batch_no": "H2550579", "sku_code": "PFL1505", "step": "Pushed in dispatch"}
    assert step(**item).status_code == 200
    assert step(**item).status_code == 409
    move = {"sku_code": "PFL1201", "step": "Return requested"}
    assert step(**move, note="for Lucknow").status_code == 200
    assert step(**move, note="for Gurugram").status_code == 200                 # a second move of the product
    assert step(step="Raised with CFA").status_code == step(step="Raised with CFA").status_code == 200  # recurring


def test_b5_names_of_spaces_are_refused():
    assert step(step="Raised with CFA", by="     ").status_code == 422
    assert client.post("/api/intake/form", json={"stockist_code": "STK0117", "entered_by": "    ",
                                                 "lines": [{"batch_no": "L2400579", "qty_claimed": 5}]}).status_code == 422
    assert client.post("/api/intake/status", json={"claim_no": "CLM-2611-04519", "status": "Verified",
                                                   "by": "    "}).status_code == 422


def test_b6_blank_email_is_refused():
    assert client.post("/api/intake/email", json={"stockist_code": "STK0117", "body": "   \n  "}).status_code == 422


def test_b7_limit_must_be_at_least_one():
    assert client.get("/api/claims?limit=-1").status_code == 422
    assert client.get("/api/claims?limit=0").status_code == 422
    assert len(client.get("/api/claims?limit=1000").json()) == 360


def test_b8_offset_cannot_be_negative():
    assert client.post("/api/source", json={"file": "sku_master.csv", "rows": [2, 3], "offset": -5}).status_code == 422


def test_d01_security_headers_on_every_response():
    """QA 21 Nov D-01."""
    for r in (client.get("/"), client.get("/api/health"), client.post("/api/claim/register", json={"claim_no": "X"})):
        assert r.headers["x-content-type-options"] == "nosniff" and r.headers["x-frame-options"] == "DENY"
        assert "frame-ancestors 'none'" in r.headers["content-security-policy"]


def test_d03_half_written_registration_is_never_served(tmp_path, monkeypatch):
    """QA 21 Nov D-03: a 'registered' event without its status (as a reader could see mid-write) is skipped, not a 500."""
    import json as _json

    from agent import store
    monkeypatch.setattr(store, "PATH", tmp_path / "s.jsonl")
    (tmp_path / "s.jsonl").write_text(_json.dumps({"event": "registered", "claim_no": "CLM-2611-09999", "at": "x",
                                                   "claim_date": "2026-11-20", "stockist_code": "STK0117"}) + "\n")
    assert store.claims() == [] and store.as_register_rows("STK0117") == []
