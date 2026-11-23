"""New claims (ADR 0013): checked on arrival, logged with a claim number, tracked to the credit note.
conftest.py gives every test an empty store, so these never touch data/claims_store.jsonl."""
from datetime import date

from fastapi.testclient import TestClient

import agent.claim_nodes as nodes
from agent import store
from app import app

client = TestClient(app)
LINE = "Linezolid 600, batch L2400579, exp Oct-26, 30 strips, inv INV/S01/2507/044588"


def no_model():
    raise AssertionError("the model was called")


def email(body=LINE, stockist="STK0117", day="2026-10-20"):
    return client.post("/api/intake/email", json={"stockist_code": stockist, "subject": "Expiry claim",
                                                  "body": body, "received_date": day})


def test_new_email_is_checked_logged_and_acknowledged(monkeypatch):
    monkeypatch.setattr(nodes, "get_llm", no_model)
    out = email().json()
    assert out["registered"] == ["CLM-2610-04519"]  # register's running number continues after 04518
    assert out["route"] == "clean" and out["lines"][0]["recommendation"]["credit_inr"] == 4539.0
    assert "Line 1, claim CLM-2610-04519" in out["reply"]
    [c] = client.get("/api/intake").json()
    assert (c["claim_no"], c["status"], c["due"]["verify_by"], c["due"]["credit_by"]) == (
        "CLM-2610-04519", "Received", "2026-11-03", "2026-11-19")


def test_a_second_claim_counts_against_the_first(monkeypatch):
    monkeypatch.setattr(nodes, "get_llm", no_model)
    email()
    out = client.post("/api/intake/form", json={"stockist_code": "STK0117", "entered_by": "Desk A",
                                                "received_date": "2026-10-21",
                                                "lines": [{"batch_no": "L2400579", "qty_claimed": 30,
                                                           "invoice_ref": "INV/S01/2507/044588"}]}).json()
    line = out["lines"][0]
    assert out["registered"] == ["CLM-2610-04520"]
    assert line["route"] == "reject" and "CLM-2610-04519" in line["checks"]["chk_duplicate"]["detail"]


def test_bad_lines_are_logged_as_awaiting_info(monkeypatch):
    monkeypatch.setattr(nodes, "get_llm", no_model)
    out = client.post("/api/intake/form", json={"stockist_code": "STK0117", "entered_by": "Desk A",
                                                "lines": [{"batch_no": "L2400579", "qty_claimed": -3}]}).json()
    assert out["lines"][0]["route"] == "needs_person"
    assert "Quantity -3 is not a whole number" in out["lines"][0]["errors"][0]
    assert store.get(out["registered"][0])["status"] == "Awaiting info"


def test_lifecycle_verify_before_approve_then_credit_note(monkeypatch):
    monkeypatch.setattr(nodes, "get_llm", no_model)
    out = email().json()
    no, audit_id = out["registered"][0], out["audit_id"]
    decide = {"audit_id": audit_id, "decided_by": "Exec", "decision": "approve", "claim_no": no}
    assert client.post("/api/decision", json=decide).status_code == 409  # not verified yet (5.6)
    assert client.post("/api/intake/status", json={"claim_no": no, "status": "Verified", "by": "CFA S01"}).status_code == 200
    assert client.post("/api/decision", json=decide).status_code == 200
    move = {"claim_no": no, "status": "Credit note raised", "by": "Exec"}
    assert client.post("/api/intake/status", json=move).status_code == 409  # needs the number
    assert client.post("/api/intake/status", json={**move, "credit_note_no": "CN/S01/2611/00001"}).status_code == 200
    c = store.get(no)
    assert c["status"] == "Credit note raised" and c["credit_note_no"] == "CN/S01/2611/00001"
    assert [h["status"] for h in c["history"]] == ["Received", "Verified", "Approved", "Decision: approve",
                                                    "Credit note raised"]
    # once credited, a repeat of the same claim is a duplicate of a settled claim
    assert store.as_register_rows("STK0117", "L2400579")[0]["status"] == "Credited"


def test_unknown_sender_and_bad_inputs(monkeypatch):
    monkeypatch.setattr(nodes, "get_llm", no_model)
    out = email(stockist=None).json()
    assert out["lines"][0]["route"] == "needs_person" and store.get(out["registered"][0])["status"] == "Awaiting info"
    assert email(stockist="STK9999").status_code == 422
    assert email(day="2099-01-01").status_code == 422
    assert client.post("/api/intake/form", json={"stockist_code": "STK0117", "entered_by": "A", "lines": []}).status_code == 422


def test_status_query_by_email_is_answered_not_logged(monkeypatch):
    monkeypatch.setattr(nodes, "get_llm", no_model)
    out = client.post("/api/intake/email", json={"stockist_code": "STK0056", "body": "Status of CLM-2608-02444?"}).json()
    assert out["registered"] == [] and "CLM-2608-02444: Pending" in out["reply"]
    assert client.get("/api/intake").json() == []


def test_working_day_due_date_skips_weekends():
    assert store._working_days_after(date(2026, 10, 20), 10) == date(2026, 11, 3)
