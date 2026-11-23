"""Claims desk, end to end through the API: register claims, mailbox emails, new claims (email
and form) with synthetic boundary data, decisions and the new-claim lifecycle."""
import json
from pathlib import Path

import pytest

from conftest import load

FORMS = load("intake_form_cases.json")
EMAILS = load("intake_email_cases.json")
CHECK_SET = json.loads((Path(__file__).resolve().parents[2] / "tests" / "check_set.json").read_text())


def bad(line):
    return sorted(k for k, r in line["checks"].items() if r["outcome"] in ("fail", "flag"))


@pytest.mark.parametrize("case", FORMS, ids=[c["id"] for c in FORMS])
def test_boundary_forms(api, case):
    """TC-CLM-1xx | Functional boundary | CO-POL-014 5.2, 5.3, 5.5, 5.6 | Synthetic claim forms on the policy boundaries get the route the policy requires"""
    r = api.post("/api/intake/form", json=case["request"])
    assert r.status_code == 200, r.text
    b = r.json()
    exp = case["expect"]
    if "routes" in exp:
        assert [ln["route"] for ln in b["lines"]] == exp["routes"], case["why"]
        return
    ln = b["lines"][0]
    assert ln["route"] == exp["route"], (case["why"], ln["errors"], {k: v["detail"] for k, v in ln["checks"].items()})
    assert bad(ln) == sorted(exp["fails"]), case["why"]
    if "action" in exp:
        assert ln["recommendation"]["action"] == exp["action"] and ln["recommendation"]["qty"] == exp["qty"]
    assert len(b["registered"]) == len(b["lines"])  # every line is logged on arrival (CF Sch 2 2.6.1)


@pytest.mark.parametrize("case", EMAILS, ids=[c["id"] for c in EMAILS])
def test_email_intake_cases(api, case):
    """TC-CLM-2xx | Functional/negative | ADR 0006, 0012, 0013 | New claim emails: valid, injection, unknown sender, status, not-a-claim, unreadable, invalid"""
    r = api.post("/api/intake/email", json=case["request"])
    exp = case["expect"]
    assert r.status_code == exp["status"], (case["why"], r.text[:200])
    if r.status_code != 200:
        return
    b = r.json()
    if "registered" in exp:
        assert len(b["registered"]) == exp["registered"], case["why"]
    if "read_by" in exp:
        assert b["read_by"] == exp["read_by"]
    if "route" in exp:
        assert b["lines"][0]["route"] == exp["route"]
    if "checks" in exp:
        assert len(b["lines"][0]["checks"]) == exp["checks"]
    if "reply_has" in exp:
        assert exp["reply_has"] in b["reply"]


@pytest.mark.parametrize("case", CHECK_SET["emails"], ids=[c["id"] for c in CHECK_SET["emails"]])
def test_mailbox_emails_agreed_answers(api, case):
    """TC-CLM-3xx | Regression | tests/check_set.json | All 30 mailbox emails give the claims desk's agreed routes, with no model call"""
    b = api.post("/api/claim/email", json={"email_id": case["id"]}).json()
    assert b["route"] == case["expect"]["route"], case["why"]
    assert b["read_by"] == "rules" and not b["usage"]
    if "lines" in case["expect"]:
        assert [(ln["route"], bad(ln)) for ln in b["lines"] or []] == [(e["route"], sorted(e["fails"])) for e in case["expect"]["lines"]]


def test_settled_register_claim_is_never_recommended(api):
    """TC-CLM-401 | Functional | CO-POL-014 5.6 | A credited register claim is already_decided, credit 0, and cannot be approved"""
    b = api.post("/api/claim/register", json={"claim_no": "CLM-2404-04177"}).json()
    assert b["route"] == "already_decided" and b["lines"][0]["recommendation"]["credit_inr"] == 0
    r = api.post("/api/decision", json={"audit_id": b["audit_id"], "decided_by": "QA Exec", "decision": "approve", "note": "attempting a second credit"})
    assert r.status_code == 409


def test_decision_rules(api):
    """TC-CLM-402 | Functional | ADR 0002, 0012 | Override needs a reason; one decision per claim; a change needs a reason and records what it changes"""
    a = api.post("/api/claim/register", json={"claim_no": "CLM-2603-01321"}).json()["audit_id"]  # recommend reject
    d = lambda **k: api.post("/api/decision", json={"audit_id": a, "decided_by": "QA Exec", **k})  # noqa: E731
    assert d(decision="approve").status_code == 422
    assert d(decision="approve", note="Area Manager confirmed receipt").json()["override"] is True
    assert d(decision="approve", note="again").status_code == 409
    assert d(decision="reject").status_code == 422
    assert d(decision="reject", note="AM approval withdrawn").json()["changes"]["decision"] == "approve"


def test_new_claim_full_lifecycle(api):
    """TC-CLM-403 | End-to-end | CO-POL-014 5.6; CF Sch 2 2.6 | New claim: logged, verified, approved, credit note, closed; illegal moves refused"""
    case = next(c for c in FORMS if c["id"] == "BND-EXP-90")
    b = api.post("/api/intake/form", json=case["request"]).json()
    no, audit_id = b["registered"][0], b["audit_id"]
    st = lambda s, **k: api.post("/api/intake/status", json={"claim_no": no, "status": s, "by": "QA CFA", **k})  # noqa: E731
    dec = lambda x: api.post("/api/decision", json={"audit_id": audit_id, "decided_by": "QA Exec", "decision": x, "claim_no": no})  # noqa: E731
    assert dec("approve").status_code == 409                  # not verified
    assert st("Closed").status_code == 409                     # Received -> Closed not allowed
    assert st("Verified", note="counted").status_code == 200
    assert dec("approve").status_code == 200
    assert dec("approve").status_code == 409                   # already approved
    assert st("Credit note raised").status_code == 409         # needs the number
    assert st("Credit note raised", credit_note_no="CN/QA/0001").status_code == 200
    assert st("Closed").status_code == 200
    assert st("Verified").status_code == 409                   # closed is final
    c = next(x for x in api.get("/api/intake").json() if x["claim_no"] == no)
    assert [h["status"] for h in c["history"]] == ["Received", "Verified", "Approved", "Decision: approve", "Credit note raised", "Closed"]


def test_claim_numbers_are_sequential_and_unique(api):
    """TC-CLM-404 | Data integrity | CF Sch 2 2.6.1 | New claim numbers continue the register serial, one per line, never reused"""
    case = next(c for c in FORMS if c["id"] == "DUP-IN-FORM")
    first = api.post("/api/intake/form", json=case["request"]).json()["registered"]
    second = api.post("/api/intake/form", json=case["request"]).json()["registered"]
    serials = [int(n[-5:]) for n in first + second]
    assert serials == list(range(4519, 4523))
    assert all(n.startswith("CLM-26") for n in first + second)


def test_repeat_claim_counts_against_the_first(api):
    """TC-CLM-405 | Functional | CO-POL-014 5.5, 5.6 | A second new claim on the same batch sees the first (duplicate check)"""
    case = next(c for c in FORMS if c["id"] == "BND-QTY-1")
    api.post("/api/intake/form", json=case["request"])
    b = api.post("/api/intake/form", json=case["request"]).json()
    assert b["lines"][0]["route"] == "reject" and "chk_duplicate" in bad(b["lines"][0])


def test_status_reply_privacy(api):
    """TC-CLM-406 | Security/functional | ADR 0006 | A status question about another stockist's claim discloses nothing"""
    b = api.post("/api/intake/email", json={"stockist_code": "STK0001", "body": "Status of CLM-2608-02444?"}).json()
    assert "no such claim on this stockist's account" in b["reply"] and "Pending" not in b["reply"]


def test_all_pending_register_claims_check(api):
    """TC-CLM-407 | Volume/functional | ADR 0003, 0012 | All 360 pending register claims check with 8 checks, no model, valid money"""
    claims = api.get("/api/claims?status=Pending&limit=1000").json()
    assert len(claims) == 360
    for c in claims:
        b = api.c.post("/api/claim/register", json={"claim_no": c["claim_no"]}).json()
        ln = b["lines"][0]
        rec = ln["recommendation"]
        assert ln["route"] == "needs_person" or len(ln["checks"]) == 8
        for k in ("credit_inr", "credit_if_approved_inr"):
            v = rec.get(k)
            assert v is None or (v >= 0 and round(v, 2) == v)
