"""Concurrent requests against a real server process: things that must happen once, happen once."""
from concurrent.futures import ThreadPoolExecutor

import httpx

from conftest import load

FORM = next(c for c in load("intake_form_cases.json") if c["id"] == "BND-QTY-1")["request"]


def _burst(n, fn):
    with ThreadPoolExecutor(max_workers=n) as ex:
        return list(ex.map(lambda _: fn(), range(n)))


def test_concurrent_intake_gives_unique_claim_numbers(server):
    """TC-CON-001 | Concurrency | CF Sch 2 2.6.1 | 40 claim forms at once (8 threads): every claim number unique and consecutive"""
    with httpx.Client(base_url=server["base"], timeout=60) as c:
        with ThreadPoolExecutor(max_workers=8) as ex:
            res = list(ex.map(lambda i: c.post("/api/intake/form", json={**FORM, "entered_by": f"QA thread {i}"}), range(40)))
    assert all(r.status_code == 200 for r in res)
    nos = [n for r in res for n in r.json()["registered"]]
    serials = sorted(int(n[-5:]) for n in nos)
    assert len(nos) == len(set(nos)) == 40 and serials == list(range(serials[0], serials[0] + 40))


def test_concurrent_identical_decisions_record_once(server):
    """TC-CON-002 | Concurrency | ADR 0002 (QA B1) | 10 identical approvals at once on one claim: exactly one is recorded"""
    with httpx.Client(base_url=server["base"], timeout=60) as c:
        a = c.post("/api/claim/register", json={"claim_no": "CLM-2606-02056"}).json()["audit_id"]
        codes = _burst(10, lambda: c.post("/api/decision", json={"audit_id": a, "decided_by": "QA Exec", "decision": "approve"}).status_code)
    assert sorted(codes).count(200) == 1, codes


def test_concurrent_identical_stock_steps_record_once(server):
    """TC-CON-003 | Concurrency | ADR 0014 (QA B4) | 10 identical 'Pushed in dispatch' at once: exactly one recorded"""
    body = {"cnf_code": "CF-E01", "sku_code": "PFL1505", "batch_no": "H2550579", "step": "Pushed in dispatch", "by": "QA"}
    with httpx.Client(base_url=server["base"], timeout=60) as c:
        codes = _burst(10, lambda: c.post("/api/stock/action", json=body).status_code)
    assert codes.count(200) == 1 and codes.count(409) == 9, codes


def test_concurrent_status_moves_apply_once(server):
    """TC-CON-004 | Concurrency | ADR 0013 | 10 'Verified' moves at once on one new claim: one succeeds, the rest are refused"""
    with httpx.Client(base_url=server["base"], timeout=60) as c:
        no = c.post("/api/intake/form", json={**FORM, "entered_by": "QA once"}).json()["registered"][0]
        codes = _burst(10, lambda: c.post("/api/intake/status", json={"claim_no": no, "status": "Verified", "by": "QA"}).status_code)
    assert codes.count(200) == 1 and codes.count(409) == 9, codes
