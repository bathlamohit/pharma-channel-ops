"""Performance and load against a real server process. There is no stated performance requirement,
so results are recorded as evidence (evidence/performance.json); the only assertions are that
nothing errors and that a sanity ceiling (10 s per request) is never hit."""
import json
import statistics
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx

from conftest import EVIDENCE, load

OUT = EVIDENCE / "performance.json"
READS = ["/api/health", "/api/claims?status=Pending&limit=400", "/api/emails", "/api/stock/overview",
         "/api/stock/plan?cfa=CF-E01", "/api/allocation/overview", "/api/allocation/plan?cfa=CF-N02",
         "/api/allocation/topups", "/api/allocation/returns", "/api/allocation/shares", "/api/allocation/schemes", "/api/digest", "/api/intake"]


def pct(xs, p):
    xs = sorted(xs)
    return round(xs[min(len(xs) - 1, int(round(p / 100 * (len(xs) - 1))))], 1)


def summary(ms):
    return {"n": len(ms), "p50_ms": pct(ms, 50), "p95_ms": pct(ms, 95), "p99_ms": pct(ms, 99), "max_ms": round(max(ms), 1),
            "mean_ms": round(statistics.mean(ms), 1)}


def save(key, value):
    data = json.loads(OUT.read_text()) if OUT.exists() else {}
    data[key] = value
    OUT.write_text(json.dumps(data, indent=1))


def timed(c, method, url, body=None):
    t = time.perf_counter()
    r = c.post(url, json=body) if method == "POST" else c.get(url)
    return r.status_code, (time.perf_counter() - t) * 1000


def test_cold_then_warm_latency(server):
    """TC-PRF-001 | Performance | n/a (no stated target) | Cold start, first call and warm p50/p95 per read endpoint"""
    res = {"server_boot_seconds": server["boot_seconds"], "endpoints": {}}
    with httpx.Client(base_url=server["base"], timeout=60) as c:
        for url in READS:
            code, first = timed(c, "GET", url)
            warm = [timed(c, "GET", url)[1] for _ in range(15)]
            assert code == 200 and max(warm) < 10_000
            res["endpoints"][url] = {"first_ms": round(first, 1), **summary(warm)}
        for name, body, url in (("register claim", {"claim_no": "CLM-2606-02056"}, "/api/claim/register"),
                                ("mailbox email (3 lines)", {"email_id": "EML-002"}, "/api/claim/email")):
            ms = [timed(c, "POST", url, body)[1] for _ in range(15)]
            res["endpoints"][f"POST {url} ({name})"] = summary(ms)
    save("latency", res)


def test_load_intake_1000_emails(server):
    """TC-PRF-002 | Load | n/a | 1,000 synthetic claim emails, 10 concurrent senders: no errors, unique claim numbers, throughput recorded"""
    emails = load("volume_emails.json")
    with httpx.Client(base_url=server["base"], timeout=60, limits=httpx.Limits(max_connections=20)) as c:
        def send(e):
            t = time.perf_counter()
            r = c.post("/api/intake/email", json=e["request"])
            return r.status_code, (time.perf_counter() - t) * 1000, (r.json().get("registered") if r.status_code == 200 else [])
        t0 = time.perf_counter()
        with ThreadPoolExecutor(max_workers=10) as ex:
            res = list(ex.map(send, emails))
        wall = time.perf_counter() - t0
    codes = [r[0] for r in res]
    nos = [n for r in res for n in r[2]]
    out = {"requests": len(res), "concurrency": 10, "wall_seconds": round(wall, 1), "throughput_rps": round(len(res) / wall, 1),
           "errors": len([x for x in codes if x != 200]), "claims_logged": len(nos), "unique_claim_numbers": len(set(nos)),
           **summary([r[1] for r in res])}
    save("load_intake", out)
    assert out["errors"] == 0 and len(nos) == len(set(nos))


def test_load_mixed_reads(server):
    """TC-PRF-003 | Load | n/a | Mixed reads, 10 concurrent users x 40 requests over all screens: no errors, latency recorded"""
    urls = READS * 40
    with httpx.Client(base_url=server["base"], timeout=60, limits=httpx.Limits(max_connections=20)) as c:
        t0 = time.perf_counter()
        with ThreadPoolExecutor(max_workers=10) as ex:
            res = list(ex.map(lambda u: timed(c, "GET", u), urls[:400]))
        wall = time.perf_counter() - t0
    out = {"requests": len(res), "concurrency": 10, "wall_seconds": round(wall, 1), "throughput_rps": round(len(res) / wall, 1),
           "errors": len([r for r in res if r[0] != 200]), **summary([r[1] for r in res])}
    save("load_reads", out)
    assert out["errors"] == 0


def test_store_growth_cost(server):
    """TC-PRF-004 | Scalability | ADR 0013 | Cost of a check as the claims store grows (after the 1,000-claim load)"""
    with httpx.Client(base_url=server["base"], timeout=60) as c:
        n = len(c.get("/api/intake").json())
        ms = [timed(c, "POST", "/api/claim/register", {"claim_no": "CLM-2606-02056"})[1] for _ in range(10)]
        lst = [timed(c, "GET", "/api/intake")[1] for _ in range(5)]
    save("store_growth", {"stored_claims": n, "register_check": summary(ms), "list_new_claims": summary(lst)})
    assert n >= 1000
