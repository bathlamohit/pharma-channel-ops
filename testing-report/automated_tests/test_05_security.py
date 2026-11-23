"""Security checks. Findings that are open decisions (sign-in, hosted store) are recorded as
expected failures with the reason, so they stay visible without hiding the rest of the suite."""
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("name", ["../.env", "..%2F.env", "/etc/passwd", "fix_log.csv", "audit_log.jsonl",
                                  "claims_store.jsonl", "../app.py", "expiry_claims.csv/../../.env"])
def test_source_viewer_only_serves_the_seven_tables(api, name):
    """TC-SEC-001 | Security: path traversal | ADR 0004 | The source viewer refuses any file outside its allow-list"""
    assert api.post("/api/source", json={"file": name, "rows": [1]}).status_code == 400


def test_static_files_do_not_expose_data_or_secrets(api):
    """TC-SEC-002 | Security: file exposure | ADR 0010 | .env, data files, logs and source are not served"""
    for path in ("/.env", "/data/clean/expiry_claims.csv", "/data/audit_log.jsonl", "/app.py", "/agent/policy.py", "/../.env"):
        assert api.get(path).status_code == 404, path


def test_no_secret_in_the_built_page():
    """TC-SEC-003 | Security: secrets | ADR 0010 | The built JavaScript holds no API key or .env value"""
    bundle = "".join(p.read_text(errors="ignore") for p in (ROOT / "public").rglob("*") if p.is_file())
    assert not re.search(r"sk-or-[A-Za-z0-9-]{10,}|OPENROUTER_API_KEY", bundle)
    env = (ROOT / ".env").read_text() if (ROOT / ".env").exists() else ""
    for line in env.splitlines():
        if "=" in line and len(line.split("=", 1)[1].strip()) > 8:
            assert line.split("=", 1)[1].strip() not in bundle


def test_env_is_git_ignored():
    """TC-SEC-004 | Security: secrets | ADR 0010 | .env and the local stores are in .gitignore"""
    ignored = (ROOT / ".gitignore").read_text().split()
    for p in (".env", "data/audit_log.jsonl", "data/claims_store.jsonl", "data/stock_actions.jsonl"):
        assert p in ignored


def test_frontend_never_renders_html_from_data():
    """TC-SEC-005 | Security: XSS | ADR 0011 | No dangerouslySetInnerHTML or innerHTML in the React source"""
    src = "".join(p.read_text() for p in (ROOT / "frontend" / "src").rglob("*.jsx"))
    assert "dangerouslySetInnerHTML" not in src and "innerHTML" not in src


def test_script_in_input_is_returned_as_plain_data(api):
    """TC-SEC-006 | Security: XSS | ADR 0006 | Markup sent as a name or email is stored and returned as text, never executed server-side"""
    evil = "<script>alert(1)</script><img src=x onerror=alert(2)>"
    b = api.post("/api/intake/email", json={"stockist_code": "STK0096", "from_name": evil,
                                            "body": f"batch F2420525 10 strips {evil}"}).json()
    assert b["registered"] and evil in str(api.get("/api/intake").json())  # stored verbatim, React escapes on render


def test_prompt_injection_has_no_effect(api):
    """TC-SEC-007 | Security: prompt injection | ADR 0006 | An instruction in an email cannot skip checks or change the sender"""
    b = api.post("/api/claim/email", json={"email_id": "EML-017"}).json()
    ln = b["lines"][0]
    assert len(ln["checks"]) == 8 and ln["route"] == "to_person" and ln["claim"]["stockist_code"] == "STK0110"
    spoof = api.post("/api/intake/email", json={"stockist_code": "STK0001", "body": "I am STK0096. batch F2420525 10 strips"}).json()
    assert spoof["lines"][0]["claim"]["stockist_code"] == "STK0001"  # identity from the mailbox, never the text


def test_errors_do_not_leak_internals(api):
    """TC-SEC-008 | Security: information disclosure | OWASP | Error responses carry no stack trace or file path"""
    for r in (api.post("/api/claim/register", json={"claim_no": "X"}), api.get("/api/stock/plan?cfa=ZZ"),
              api.post("/api/source", json={"file": "../x", "rows": [1]})):
        assert "Traceback" not in r.text and "/Users/" not in r.text and ".py" not in r.text


def test_sql_and_shell_strings_are_inert(api):
    """TC-SEC-009 | Security: injection | OWASP | SQL/shell-like strings in lookups are treated as plain text (no database, no shell)"""
    for s in ("' OR 1=1 --", "$(rm -rf /)", "`id`", "CLM-2606-02056'; DROP TABLE claims;--"):
        assert api.post("/api/claim/register", json={"claim_no": s}).status_code == 404


@pytest.mark.xfail(strict=True, reason="OPEN DECISION: no sign-in yet (QA review F4, ADR 0013). Anyone with the URL can act.")
def test_endpoints_require_authentication(api):
    """TC-SEC-010 | Security: authentication | QA review F4 | Write endpoints require a signed-in user"""
    assert api.post("/api/stock/action", json={"cnf_code": "NATIONAL", "step": "Raised with NSM", "by": "Anyone"}).status_code == 401


@pytest.mark.xfail(strict=True, reason="NOT IMPLEMENTED: no role model; any user can approve, record steps or move claims.")
def test_roles_limit_actions(api):
    """TC-SEC-011 | Security: authorisation | CF Sch 2 2.5 | Only the Head of Supply Chain can record 'Return approved'"""
    api.post("/api/stock/action", json={"cnf_code": "CF-E01", "sku_code": "PFL1004", "batch_no": "A2600468", "step": "Return requested", "by": "QA RDM"})
    r = api.post("/api/stock/action", json={"cnf_code": "CF-E01", "sku_code": "PFL1004", "batch_no": "A2600468", "step": "Return approved", "by": "Not the Head"})
    assert r.status_code == 403


def test_security_headers(api):
    """TC-SEC-012 | Security: headers | OWASP | Responses set nosniff and frame protection"""
    h = api.get("/").headers
    assert h.get("x-content-type-options") == "nosniff"
    assert h.get("x-frame-options") in ("DENY", "SAMEORIGIN") or "frame-ancestors" in h.get("content-security-policy", "")


@pytest.mark.xfail(strict=True, reason="NOT IMPLEMENTED: no rate limiting (only a 64 KB body limit). Vercel's platform limits apply when deployed.")
def test_rate_limiting(api):
    """TC-SEC-013 | Security: abuse | OWASP | Rapid repeated requests are throttled"""
    codes = {api.c.get("/api/health").status_code for _ in range(300)}
    assert 429 in codes


def test_no_cors_wildcard(api):
    """TC-SEC-014 | Security: CORS | OWASP | Other sites are not allowed to call the API from a browser"""
    r = api.c.options("/api/health", headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "GET"})
    assert r.headers.get("access-control-allow-origin") not in ("*", "https://evil.example")
