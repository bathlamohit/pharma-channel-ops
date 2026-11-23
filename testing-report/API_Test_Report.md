# API test report

The API was tested in process (FastAPI TestClient) and over HTTP against a real uvicorn server.
- Evidence: `evidence/api_calls.jsonl`, 238 logged requests and responses (method, URL, request
  body, status, response, ms).
- Tests: `automated_tests/test_01` to `test_07`.

## Endpoints and results

| Endpoint | What it does | Tested | Result |
|---|---|---|---|
| `GET /api/health` | Liveness, key set, clean data present | Shape and types (TC-API-001) | Pass |
| `GET /api/claims` | Pending register claims with names | Shape; `limit` 0, −1, 1001 → 422; 1000 → all 360 | Pass |
| `GET /api/emails` | Mailbox with bodies | Shape; 30 emails | Pass |
| `GET /api/stockists` | Stockist master for pickers | Shape | Pass |
| `POST /api/claim/register` | Check a register claim | Shape (8 checks, recommendation, citations); unknown 404; missing body 422; SQL- and shell-like strings 404; all 360 pending claims | Pass |
| `POST /api/claim/email` | Read and check a mailbox email | All 30 agreed answers; read by rules, no model; unknown id 404 | Pass |
| `POST /api/intake/email` | New email: check, log, acknowledge | 12 synthetic cases; 1,000-email load; blank, over 20,000 characters, future date, bad format, unknown account → 422 | Pass |
| `POST /api/intake/form` | New claim form | 19 boundary cases; null/empty/short/long fields; 21 lines; bad date (30 Feb); unicode name | Pass |
| `GET /api/intake` | New claims with status, history, due dates | Shape; lifecycle; 1,041 claims | Pass |
| `POST /api/intake/status` | Move a new claim | Full lifecycle; illegal moves 409; blank name 422; long credit note number 422 | Pass |
| `GET /api/stock/overview`, `/api/stock/plan` | Expiry & dispatch | Shape; integrity per CFA (6); unknown CFA 404; missing `cfa` 422 | Pass |
| `POST /api/stock/action` | Record a step | Order rules; repeats 409; unknown CFA, SKU or batch 422; scheme steps national only; null and blank fields 422 | Pass |
| `GET /api/allocation/overview`, `/plan`, `/moves`, `/schemes` | Allocation | Shape; integrity per CFA (6); move steps; unknown CFA 404 | Pass |
| `GET /api/digest` | Weekly digest | Equals the screens; to-dos point at screens; email text carries the figures | Pass |
| `POST /api/watch` | Summary views (back the figure tests) | 6 views; bad tab 422 | Pass |
| `POST /api/source` | Cited rows | Paging; fixes; missing rows reported; traversal and other files 400; negative offset 422; 100,000 rows 413 | Pass |
| `POST /api/decision` | A person's decision | Override needs a reason; one decision per claim; change needs a reason; unknown audit id 404; settled claim 409; enum, length and type checks | Pass |
| `GET /` and static files | React page | Served; `.env`, data, logs and source not served (404) | Pass |

**Status codes seen in the evidence log:** 200, 400, 404, 409, 413, 422. No 500 appears in the final
run. The only 500 seen during the assessment was defect D-03, now fixed.

## Request and response rules (verified)

- **422 for validation errors.** Each gives a readable `detail` naming the field (Pydantic).
- **Other errors:**
  - 404: unknown claim, email, CFA or audit id
  - 409: refused by a business rule (already decided, out-of-order step, illegal status move)
  - 400: a file not allowed in the source viewer
  - 413: body over 64 KB
- **Malformed JSON** gives 422, not 500 (TC-API-037).
- **Text is trimmed before length checks:** names, notes and email bodies (B5, B6).
- **Errors leak nothing:** no stack traces, paths or `.py` names (TC-SEC-008).

## Duplicate submissions

| Action | Same request twice | Same request ×10 at once |
|---|---|---|
| Decision on one claim | Second refused (409) | Exactly 1 recorded (**after fix D-02**; before it, 4 were recorded) |
| Stock / allocation step | Second refused (409) | Exactly 1 recorded, 9 × 409 |
| Status move | Second refused (409) | Exactly 1 applied, 9 × 409 |
| Claim form | Each logged separately, then caught as a duplicate claim by the rules (reject) | 40 forms at once: 40 unique, consecutive claim numbers (**after fix D-03**) |

## Not covered

- **Rate limiting.** Not implemented (O-04); the expected-failure test TC-SEC-013 records it.
- **Authentication and roles.** No sign-in yet (O-01, O-02); every endpoint is open.
- **Live model fallback.** Not called: tests run without a key. The 30 live tests in `tests/` are
  opt-in.
