"""API contract: every endpoint, status codes, response structure and types, error responses."""
import pytest

ENDPOINTS_GET = [
    ("TC-API-001", "/api/health", dict, {"ok": bool, "model_key_set": bool, "clean_data": bool}),
    ("TC-API-002", "/api/claims?status=Pending&limit=5", list, {"claim_no": str, "claim_date": str, "stockist_name": str, "product": str}),
    ("TC-API-003", "/api/emails", list, {"email_id": str, "received_date": str, "body": str, "subject": str}),
    ("TC-API-004", "/api/stockists", list, {"stockist_code": str, "stockist_name": str, "cnf_code": str}),
    ("TC-API-005", "/api/intake", list, {}),
    ("TC-API-006", "/api/stock/overview", dict, {"as_of": str, "cards": list, "rules": dict}),
    ("TC-API-007", "/api/stock/plan?cfa=CF-E01", dict, {"todo": list, "pick_list": list, "fefo": dict, "citations": list, "actions": list}),
    ("TC-API-008", "/api/allocation/overview", dict, {"national": dict, "cards": list, "rules": dict}),
    ("TC-API-009", "/api/allocation/plan?cfa=CF-N02", dict, {"products": list, "unfilled": dict, "citations": list, "actions": list}),
    ("TC-API-010", "/api/allocation/topups", dict, {"cfas": list, "total_inr": float, "assumption": str, "actions": list}),
    ("TC-API-016", "/api/allocation/returns", dict, {"returns": list, "rules": list, "actions": list}),
    ("TC-API-017", "/api/allocation/shares", dict, {"cfas": list, "largest_product_changes": list, "status": str}),
    ("TC-API-018", "/api/allocation/restatement", dict, {"rows": list}),
    ("TC-API-019", "/api/allocation/overview?basis=fy25", dict, {"basis": str, "national": dict, "assumptions": list}),
    ("TC-API-011", "/api/allocation/schemes", dict, {"scheme_rate": float, "other_rate": float, "quarters": list}),
    ("TC-API-012", "/api/digest", dict, {"as_of": str, "sections": list, "text": str}),
    ("TC-API-040", "/api/stock/short-dated", dict, {"lines": int, "value_inr": float, "reasons": list, "cfas": list, "consent": dict}),
    ("TC-API-041", "/api/stock/short-dated/lines?cfa=CF-S01", dict, {"total": int, "rows": list, "citations": list, "actions": list}),
]


@pytest.mark.parametrize("tc,url,kind,fields", ENDPOINTS_GET, ids=[e[0] for e in ENDPOINTS_GET])
def test_get_endpoints_shape(api, tc, url, kind, fields):
    """TC-API-0xx | API | ADR 0010 | Each GET endpoint returns 200 with the documented structure and types"""
    r = api.get(url)
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body, kind)
    sample = body[0] if isinstance(body, list) and body else body
    if isinstance(body, list) and not body:
        return
    for k, t in fields.items():
        assert k in sample, k
        assert isinstance(sample[k], t), (k, type(sample[k]))


def test_post_claim_register_shape(api):
    """TC-API-013 | API | ADR 0007 | POST /api/claim/register returns route, lines with 8 checks, recommendation, audit id"""
    r = api.post("/api/claim/register", json={"claim_no": "CLM-2606-02056"})
    assert r.status_code == 200
    b = r.json()
    assert set(b) >= {"route", "lines", "explanation", "citations", "errors", "usage", "audit_id"}
    ln = b["lines"][0]
    assert len(ln["checks"]) == 8 and set(ln["recommendation"]) >= {"action", "qty", "credit_inr", "reason_codes"}
    for chk in ln["checks"].values():
        assert set(chk) == {"check", "outcome", "clause", "on_fail", "detail", "citations"}
        assert chk["outcome"] in {"pass", "fail", "flag", "skip"}


def test_post_claim_email_shape(api):
    """TC-API-014 | API | ADR 0006 | POST /api/claim/email returns lines, a draft reply and read_by"""
    b = api.post("/api/claim/email", json={"email_id": "EML-002"}).json()
    assert b["read_by"] == "rules" and len(b["lines"]) == 3 and b["reply"].startswith("Dear ")


def test_post_watch_and_source(api):
    """TC-API-015 | API | ADR 0004 | POST /api/watch and /api/source return views and cited rows"""
    w = api.post("/api/watch", json={"tab": "weekly"}).json()
    assert set(w["watch"]) == {"expiry_radar", "fefo_alert", "short_dated", "allocation_gap", "scheme_report", "claims_ageing"}
    s = api.post("/api/source", json={"file": "sku_master.csv", "rows": [2, 3]}).json()
    assert [r["src_line"] for r in s["rows"]] == ["2", "3"] and s["total"] == 2


ERRORS = [
    ("TC-API-020", "post", "/api/claim/register", {"claim_no": "CLM-0000-00000"}, 404),
    ("TC-API-021", "post", "/api/claim/email", {"email_id": "EML-999"}, 404),
    ("TC-API-022", "post", "/api/claim/register", {}, 422),
    ("TC-API-023", "post", "/api/watch", {"tab": "monthly"}, 422),
    ("TC-API-024", "get", "/api/stock/plan?cfa=CF-XX", None, 404),
    ("TC-API-025", "get", "/api/stock/plan", None, 422),
    ("TC-API-026", "get", "/api/allocation/plan?cfa=nope", None, 404),
    ("TC-API-039", "get", "/api/allocation/overview?basis=fy99", None, 422),
    ("TC-API-027", "post", "/api/source", {"file": "../.env", "rows": [1]}, 400),
    ("TC-API-028", "post", "/api/source", {"file": "fix_log.csv", "rows": [1]}, 400),
    ("TC-API-029", "get", "/api/claims?limit=0", None, 422),
    ("TC-API-030", "get", "/api/claims?limit=1001", None, 422),
    ("TC-API-031", "post", "/api/decision", {"audit_id": "x", "decided_by": "QA", "decision": "approve"}, 422),
    ("TC-API-032", "post", "/api/decision", {"audit_id": "abcdef1", "decided_by": "QA", "decision": "maybe"}, 422),
    ("TC-API-033", "post", "/api/intake/status", {"claim_no": "CLM-2611-00001", "status": "Approved", "by": "QA"}, 422),
    ("TC-API-034", "post", "/api/stock/action", {"cnf_code": "CF-E01", "step": "Teleported", "by": "QA"}, 409),
    ("TC-API-035", "get", "/api/nonexistent", None, 404),
]


@pytest.mark.parametrize("tc,method,url,body,status", ERRORS, ids=[e[0] for e in ERRORS])
def test_error_responses(api, tc, method, url, body, status):
    """TC-API-02x | API negative | ADR 0010 | Invalid requests get the right error status and a readable message"""
    r = api.post(url, json=body) if method == "post" else api.get(url)
    assert r.status_code == status, r.text
    if status in (400, 404, 409, 422) and r.headers.get("content-type", "").startswith("application/json"):
        j = r.json()
        assert "detail" in j or "error" in j


def test_oversized_body_is_refused(api):
    """TC-API-036 | API boundary | ADR 0012 | Bodies over 64 KB are refused with 413"""
    r = api.c.post("/api/claim/email", content=b'{"email_id":"' + b"x" * 70000 + b'"}', headers={"Content-Type": "application/json"})
    assert r.status_code == 413


def test_malformed_json_is_refused(api):
    """TC-API-037 | API negative | ADR 0010 | Malformed JSON gets 422, not 500"""
    r = api.c.post("/api/decision", content=b"{not json", headers={"Content-Type": "application/json"})
    assert r.status_code == 422


def test_static_page_served(api):
    """TC-API-038 | API | ADR 0011 | GET / serves the built React page"""
    r = api.get("/")
    assert r.status_code == 200 and '<div id="root">' in r.text
