"""The graph and API run end to end with no model at all (ADR 0012). No key, no cost."""
from fastapi.testclient import TestClient

import agent.claim_nodes as nodes
from agent import audit
from app import app

client = TestClient(app)


def no_model():
    raise AssertionError("the model was called")


def test_health():
    body = client.get("/api/health").json()
    assert body["ok"] is True and body["clean_data"] is True


def test_register_claim_runs_eight_checks_without_a_model(monkeypatch):
    monkeypatch.setattr(nodes, "get_llm", no_model)
    claim_no = client.get("/api/claims?status=Pending&limit=1").json()[0]["claim_no"]
    body = client.post("/api/claim/register", json={"claim_no": claim_no}).json()
    assert body["route"] in {"reject", "to_person", "clean", "needs_person"}
    if body["route"] != "needs_person":
        assert len(body["lines"][0]["checks"]) == 8
    assert body["lines"][0]["recommendation"]["action"]
    assert body["audit_id"] and not body["usage"]


def test_email_claim_over_the_api(monkeypatch):
    """EML-009: two lines, read by rules; line 1 credited in full, line 2 out of window."""
    monkeypatch.setattr(nodes, "get_llm", no_model)
    body = client.post("/api/claim/email", json={"email_id": "EML-009"}).json()
    assert body["read_by"] == "rules"
    assert [ln["route"] for ln in body["lines"]] == ["clean", "reject"]
    assert [ln["recommendation"]["action"] for ln in body["lines"]] == ["approve", "reject"]
    assert body["route"] == "to_person"
    assert body["reply"].startswith("Dear Sri Drug House,")


def test_watch_tab_builds_digest():
    body = client.post("/api/watch", json={"tab": "watch"}).json()
    assert set(body["watch"]) == {"expiry_radar", "fefo_alert", "short_dated"}
    assert "Supply Chain" in body["digest"]
    assert body["watch"]["fefo_alert"]["summary"].startswith("ALERT CF-E01")


def test_allocation_tab_has_scheme_report():
    body = client.post("/api/watch", json={"tab": "allocation"}).json()
    assert set(body["watch"]) == {"allocation_gap", "scheme_report"}
    assert all(v["citations"] for v in body["watch"].values())


def test_decision_is_recorded(tmp_path, monkeypatch):
    monkeypatch.setattr(audit, "LOG", tmp_path / "log.jsonl")
    r = client.post("/api/decision", json={"audit_id": "abc123", "decided_by": "Exec", "decision": "reject"}).json()
    assert r["decision"] == "reject" and (tmp_path / "log.jsonl").exists()


# --- Source-row viewer -----------------------------------------------------------------
def test_source_returns_cited_rows_with_their_fixes():
    r = client.post("/api/source", json={"file": "expiry_claims.csv", "rows": [2, 3]}).json()
    assert [row["src_line"] for row in r["rows"]] == ["2", "3"]
    assert r["total"] == 2 and r["missing"] == []
    assert {"field": "credit_value_inr", "before": "3,936.80", "after": "3936.80", "fix": "number format"} in r["fixes"]["2"]
    assert all(f["before"] != f["after"] for fs in r["fixes"].values() for f in fs)


def test_source_pages_long_citations_and_reports_dropped_lines():
    rows = list(range(2, 200))
    first = client.post("/api/source", json={"file": "primary_sales.csv", "rows": rows}).json()
    assert first["total"] == 198 and len(first["rows"]) + len(first["missing"]) == 50
    second = client.post("/api/source", json={"file": "primary_sales.csv", "rows": rows, "offset": 50}).json()
    assert second["rows"][0]["src_line"] != first["rows"][0]["src_line"]


def test_source_rows_from_a_real_citation(monkeypatch, tmp_path):
    monkeypatch.setattr(nodes, "get_llm", no_model)
    monkeypatch.setattr(audit, "LOG", tmp_path / "log.jsonl")
    citations = client.post("/api/claim/register", json={"claim_no": "CLM-2404-04177"}).json()["citations"]
    assert citations
    for cit in citations:
        r = client.post("/api/source", json={"file": cit["file"], "rows": cit["rows"]}).json()
        assert r["rows"], cit


def test_source_refuses_other_files():
    for name in ("fix_log.csv", "../.env", "audit_log.jsonl"):
        assert client.post("/api/source", json={"file": name, "rows": [2]}).status_code == 400


# --- Claim handling rules (ADR 0012) ------------------------------------------------------
def _register(claim_no, monkeypatch, tmp_path):
    monkeypatch.setattr(nodes, "get_llm", no_model)
    monkeypatch.setattr(audit, "LOG", tmp_path / "log.jsonl")
    return client.post("/api/claim/register", json={"claim_no": claim_no}).json()


def test_settled_claim_is_never_recommended_again(monkeypatch, tmp_path):
    body = _register("CLM-2404-04177", monkeypatch, tmp_path)
    rec = body["lines"][0]["recommendation"]
    assert body["route"] == "already_decided" and rec["action"] == "already_decided" and rec["credit_inr"] == 0
    assert "CN/S02/2405/45970" in rec["note"]
    r = client.post("/api/decision", json={"audit_id": body["audit_id"], "decided_by": "Exec", "decision": "approve",
                                           "note": "approve it anyway please"})
    assert r.status_code == 409  # the server's own log says it is settled


def test_override_needs_a_reason(monkeypatch, tmp_path):
    body = _register("CLM-2603-01321", monkeypatch, tmp_path)  # 132 days after expiry: reject
    assert body["route"] == "reject"
    base = {"audit_id": body["audit_id"], "decided_by": "Exec", "decision": "approve"}
    assert client.post("/api/decision", json=base).status_code == 422
    ok = client.post("/api/decision", json={**base, "note": "Area Manager confirmed late receipt at CFA"}).json()
    assert ok["override"] is True and ok["recommended"] == "reject"
    # changing that decision needs a reason too, and records what it changes (QA B1)
    assert client.post("/api/decision", json={**base, "decision": "reject"}).status_code == 422
    change = client.post("/api/decision", json={**base, "decision": "reject", "note": "AM approval was not given"}).json()
    assert change["override"] is False and change["changes"]["decision"] == "approve"


def test_decision_needs_a_name():
    r = client.post("/api/decision", json={"audit_id": "abc123", "decided_by": " ", "decision": "hold"})
    assert r.status_code == 422


def test_over_quantity_is_part_approved_for_a_person(monkeypatch, tmp_path):
    rec = _register("CLM-2608-01758", monkeypatch, tmp_path)["lines"][0]["recommendation"]
    assert rec["action"] == "approve_part" and rec["qty"] == 1773 and rec["reason_codes"] == ["OVER_QUANTITY"]


def test_oversized_request_is_refused():
    r = client.post("/api/claim/email", content=b'{"email_id": "' + b"x" * 70000 + b'"}',
                    headers={"Content-Type": "application/json"})
    assert r.status_code == 413


def test_letter_never_invites_goods_for_a_rejected_line(monkeypatch):
    monkeypatch.setattr(nodes, "get_llm", no_model)
    rejected = client.post("/api/claim/email", json={"email_id": "EML-010"}).json()["reply"]
    assert "do not send these goods" in rejected and "send the goods in sealed" not in rejected.lower()
    mixed = client.post("/api/claim/email", json={"email_id": "EML-009"}).json()["reply"]
    assert "Line 2: Raised 188 days after expiry" in mixed and "For the other lines, please send" in mixed


def test_inbox_lists_carry_what_the_page_shows():
    email = client.get("/api/emails").json()[0]
    assert {"body", "stockist_code_by_mailbox_rule", "subject"} <= set(email)
    claim = client.get("/api/claims?limit=1").json()[0]
    assert claim["stockist_name"] and claim["product"] and len(claim["claim_date"]) == 10
