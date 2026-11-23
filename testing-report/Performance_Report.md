# Performance report

**Environment:**
- One uvicorn process (the default worker) on a MacBook. Not the Vercel runtime.
- A temporary store, no model key.
- Load came from the same machine over HTTP: 10 concurrent clients via a thread pool.

**There is no stated performance requirement,** so results are measured and compared, not judged
against a target. The test's only pass condition is "no errors and no request over 10 s".

Evidence:
- `evidence/performance.json`: the final run.
- `evidence/performance_before_fix.json`: the run before fix D-04.
- Tests: `automated_tests/test_07_performance.py`.

## Results after the fix (final run)

**Start-up.** The server is ready in 1.8 s; the 22 MB of CSVs load on first use.

| Endpoint | First call | Warm p50 | Warm p95 |
|---|---|---|---|
| `GET /api/health` | 1.6 ms | 1.0 ms | 1.1 ms |
| `GET /api/claims` (360) | 16.9 ms | 14.9 ms | 15.1 ms |
| `GET /api/stock/overview` | 328 ms | 1.2 ms | 1.3 ms |
| `GET /api/stock/plan` (Kolkata) | 117 ms | 16.0 ms | 16.1 ms |
| `GET /api/allocation/overview` | 408 ms | 1.3 ms | 1.5 ms |
| `GET /api/allocation/plan` (Lucknow) | 18 ms | 4.9 ms | 5.0 ms |
| `GET /api/allocation/schemes` | 104 ms | 1.3 ms | 1.6 ms |
| `GET /api/digest` | 287 ms | 14.6 ms | 15.0 ms |
| `POST /api/claim/register` | | 21.4 ms | 21.7 ms |
| `POST /api/claim/email` (3 lines) | | 53.2 ms | 54.3 ms |

| Load test | Requests | Throughput | p50 | p95 | p99 | Max | Errors |
|---|---|---|---|---|---|---|---|
| Mixed reads over all screens, 10 users | 400 | **25.3 /s** | 405 ms | **559 ms** | 792 ms | 876 ms | 0 |
| 1,000 new claim emails, 10 senders | 1,000 | 10.5 /s | 903 ms | 1.80 s | 2.05 s | 2.41 s | 0 (1,000 unique claim numbers) |

| Scalability: store holding 1,041 new claims | p50 |
|---|---|
| Check a claim (reads earlier claims, including new ones) | 21.7 ms (same as with an empty store) |
| List all new claims (`GET /api/intake`) | 342 ms |

## Before and after fix D-04

| Measure | Before | After |
|---|---|---|
| Mixed reads, 10 users: throughput | 4.7 /s | **25.3 /s** |
| Mixed reads: p95 / max | **10.5 s / 15.5 s** | 0.56 s / 0.88 s |
| Digest, warm p50 | 791 ms | 14.6 ms |
| Allocation overview, warm p50 | 297 ms | 1.3 ms |
| Check a claim with 1,000 stored claims | 73.9 ms | 21.7 ms |
| Intake load, 1,000 emails | 11.4 /s, p95 1.58 s | 10.5 /s, p95 1.80 s (within run-to-run variation) |

**Root cause.** The digest, stock plan, allocation overview and plan, and scheme figures were
recomputed from the full extract on every request: 0.1–0.8 s of CPU each. Under concurrency, the
requests queued. The new-claims file was also replayed in full on every check.

**Fix:**
- Results that depend only on the extract are computed once per process and handed out as copies.
- The store is replayed once per version of the file.
- Outputs are unchanged: the figure, consistency and functional suites all pass after the change.

A first version of the fix made intake slower (5.7 /s), because it copied the whole store on every
check. That was caught by this test and corrected before the final run.

## Bottlenecks still present

- **Intake throughput, about 10–11 claims a second.** Each claim runs the 8 checks and writes to the
  file under a lock, in one process. The desk handles about 360 claims a quarter, so this is far
  above need.
- **Listing new claims takes about 0.34 s at 1,000 claims.** Each claim is returned with its full
  check detail. Paginate or slim the list before the store grows large (O-08).
- **First call after start: 0.1–0.4 s per screen.** On Vercel each cold start pays this once.
- **Not measured:** the Vercel runtime, multiple workers, and network latency.
