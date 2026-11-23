# Project Sankalp pilot: QA and testing report

- **Date:** 21 Nov 2026
- **Build tested:** working copy in `project_sankalp/`. It isn't a git repository, so there's no
  commit id.
- **Data:** the pilot's extract (stock and register to 30 Sep 2026), plus synthetic test data
  (seed 20261121).
- **Environment:** local machine; FastAPI + React built into `public/`; temporary stores; no model key.

## A. Executive summary

**Overall health: good for a controlled pilot; not production-ready.**
- **Calculations are correct.** Every figure checked against an independent recomputation from raw
  data matches (30 of 30), and the screens agree with each other (210 of 210 checks).
- **Fixed in this assessment:** 8 defects, all fixed and re-tested:
  - 2 High: a double-approval race, and a server error during simultaneous intake
  - 3 Medium: missing security headers, slow screens under load, "Mark verified" refusing a typed name
  - 3 Low: a silent link, a UTC default date, a greeting read as the product
- **What blocks production:** three open decisions, not code bugs:
  - no sign-in
  - no roles
  - nowhere persistent to keep decisions on Vercel

| | Count |
|---|---|
| Modules tested | 9 areas over 4 screens and 23 API endpoints (inventory in section B) |
| Automated test cases executed | **385**: 200 in the QA suite, 185 unit/regression tests |
| Passed | **382** |
| Failed | **0** (final run; 8 defects were found failing and fixed during the assessment) |
| Expected failures (known gaps, open decisions) | **3**: sign-in, roles, rate limiting |
| Blocked / not run | **30** opt-in live model tests (cost money; the model is only a fallback reader) |
| Pass rate of executed tests | **99.2%** (382/385); QA suite 98.5% (197/200), unit 100% (185/185) |
| Separate scripted checks | Independent figures 30/30; cross-screen consistency 210/210; claim-rule back-test reproduces all verified figures |

**Critical findings:**
1. **D-02 (High, fixed).** Ten simultaneous identical approvals recorded four decisions: a
   double-credit risk. Now exactly one is recorded.
2. **D-03 (High, fixed).** Simultaneous new claims caused a server error (500) when one request read
   a claim another was still writing.
3. **O-01, O-02 (High, open).** No sign-in and no roles. Anyone with the URL can approve claims or
   record "Return approved" meant for the Head of Supply Chain.
4. **O-03 (High, open).** On Vercel the claims store, step log and audit log do not persist.
5. **O-05 (Medium, open).** The "will not sell in time" forecast is about as good as a simple
   baseline at 1 month but weaker at 2–3 months. Precision is 0.43–0.74.

**Production readiness:** not ready. Ready for a supervised pilot on a password-protected
deployment, with decisions copied out, once O-01 and O-03 are settled.

## B. Functionality inventory

| Screen / module | Features | API | Code |
|---|---|---|---|
| **Weekly digest** (first tab) | 4 owner sections with figures, to-dos that open the right screen, done list, email text, copy, print | `GET /api/digest` | `agent/digest.py`, `DigestDesk.jsx` |
| **Claims desk** | One inbox (new claims, mailbox, register), filter, search, arrow keys; check on open; line cards with recommendation, failing checks and clauses; draft letter with Copy; source email or register entry; decision bar (name, reason, approve/reject/hold); "+ New claim" (paste email / claim form); new-claim status, timeline and due dates | `/api/claims`, `/api/emails`, `/api/stockists`, `/api/claim/register`, `/api/claim/email`, `/api/intake/*`, `/api/decision` | `reader.py`, `rules.py`, `claim_nodes.py`, `graph.py`, `store.py`, `audit.py`; `ClaimsDesk`, `ClaimResult`, `DecisionBar`, `NewClaim`, `ClaimStatus` |
| **Expiry & dispatch** | CFA cards; to-do with act-by dates (block, consent, CDC return, push) and steps; pick order with search, print, confirm; batch-order check | `/api/stock/overview`, `/api/stock/plan`, `/api/stock/action` | `stock.py`, `stock_log.py`, `StockDesk.jsx` |
| **Allocation** | National figures; CFA cards; refill / too much / in range / orders not filled; moves via the CDC with steps; schemes for NSM and CFO | `/api/allocation/*`, `/api/stock/action` | `allocation.py`, `AllocationDesk.jsx` |
| **Citations** | "Show rows" on any source; paging; cleaning fixes shown | `POST /api/source` | `tools.source_rows`, `SourceRows.jsx` |
| **Data build** | Clean raw extract, fix log | (script) | `scripts/build_tables.py` |
| **Back-test, QA scripts** | Claim rules over history; independent figures; consistency | (scripts) | `agent/backtest.py`, `scripts/qa_*.py` |
| **Model fallback** | Reads an email only when rules recognise nothing and a key is set | (inside intake) | `claim_nodes.extract_email`, `llm.py` |

**Placeholders, TODOs and hard-coded values found:**
- Two TODOs, both documented open decisions: where the audit log is kept, and the plan's "69%"
  figure.
- No mock responses in the app.
- Proposed planning norms (cover bands of 1, 2 and 3 months) are labelled "proposed" in `policy.py`
  and on screen. All other thresholds cite CO-POL-014 or the C&F agreement.

## C. Test strategy and coverage

| Type | How | Cases | Result |
|---|---|---|---|
| Functional and end-to-end (API) | Claims, new claims, decisions, lifecycle, stock and allocation steps, digest | 86 | Pass |
| Boundary values | Policy day limits (90/91, 7/8), quantity limits, extremes, dates | 19 + 4 | Pass |
| Input validation / negative | Null, empty, wrong type, wrong format, length, range, unicode | 31 + 16 error cases | Pass |
| API contract | 23 endpoints: status, structure, types, errors | 34 | Pass |
| Security | Traversal, exposure, secrets, XSS, prompt and SQL injection, headers, CORS, auth, roles, rate limits | 21 | 18 pass, 3 known gaps |
| Concurrency | Simultaneous intake, decisions, steps, status moves | 4 | Pass (after D-02, D-03) |
| Performance / load | Latency, 1,000-email load, mixed reads, store growth | 4 | Pass (after D-04) |
| Backtesting | Independent figures; claim-rule back-test; time-ordered forecast; money; dates | 9 | Pass (forecast quality reported, O-05) |
| UI end-to-end (Playwright) | Every screen, decisions, new-claim lifecycle, phone width, local date | 11 | Pass (after D-05, D-06, D-07) |
| Regression | Unit suite and the 30-email check set | 185 + 30 | Pass |
| Data integrity | Cards = plans = digest; cited rows hold the numbers; each batch once | in the above + 210 scripted | Pass |

The categories overlap: a boundary claim is also a functional test. Each automated test is counted
once in `Test_Cases.xlsx`: 200 QA tests by file are API 34, claims 68, expiry/allocation/digest 18,
validation 31, security 21, concurrency 4, performance 4, backtesting 9, UI 11.

**Roles and permissions:** none exist in the app, so no permission tests could pass. They are
recorded as expected failures (TC-SEC-010, 011).

**Test data:** see `README.md`, "Test data".
- Synthetic claims use real stockist, batch and invoice combinations so the checks have records.
- Expected outputs come from the policy.
- Results per case are in `Test_Cases.xlsx`.

## D. Defects

Full detail is in `Defect_Register.xlsx`.

| ID | Severity | Defect | Status |
|---|---|---|---|
| D-01 | Medium | No security headers | Fixed: app middleware + `vercel.json` |
| D-02 | High | Simultaneous identical approvals all recorded | Fixed: decision lock |
| D-03 | High | 500 when reading a claim mid-registration | Fixed: atomic write, shared-lock read |
| D-04 | Medium | Read screens p95 10.5 s under 10 users; store replay per check | Fixed: cache; p95 0.56 s |
| D-05 | Medium | "Mark verified" refused a typed name | Fixed: name saved as typed |
| D-06 | Low | Claim-number link silent while the list refreshes | Fixed |
| D-07 | Low | New-claim date defaulted to UTC | Fixed: local date |
| D-08 | Low | Greeting shown as the product | Fixed |
| B1–B8 | High–Low | Earlier QA the same day (double approval, validation) | Fixed, regression tests |
| O-01..O-03 | High | No sign-in; no roles; stores not persistent on Vercel | Open: decisions for the client |
| O-04..O-09 | Medium–Low | No rate limit; forecast quality; static extract; server-date default; list size; "69%" | Open or accepted |

**Rules followed while fixing:**
- No business rule was changed to make a test pass.
- Where a test was wrong (6 cases), the test was corrected, and each is noted in the run log
  below.

## E. Backtesting

See `Backtesting_Report.md`.
- **Independent figures:** 30 of 30 match.
- **Claim-rule back-test:**
  - Rs 21.89 L / 181 credited; Rs 7.25 L / 38 pending; 61 double credits, Rs 11.20 L.
  - Deterministic: two runs give identical results.
  - The 41 rejects recommended through the API equal the back-test's 41.
- **Policy boundary dates:** all correct.
- **Stock forecast, time-ordered backtest:** better than "nothing sells" everywhere; as good as a
  proportional baseline at 1 month; weaker at 2–3 months. The flag over-flags at most CFAs and
  under-flags at Kolkata (out-of-order picking).

## F. Security

See `Security_Assessment.md`.
- **Passes:** traversal, secrets, XSS, prompt injection, disclosure, validation, size limits, CORS.
- **Fixed:** headers (D-01) and concurrency integrity (D-02, D-03).
- **Open:** sign-in, roles, rate limiting, store durability.

## G. Performance

See `Performance_Report.md`.
- **Mixed reads, 10 users:** 25 requests/s, p95 0.56 s (was 4.7/s, 10.5 s).
- **Intake:** 10.5 claims/s with 1,000 synthetic emails and 0 errors.
- **Claim check:** 22 ms, flat as the store grows.

## H. Traceability

| Requirement (source) | Tests |
|---|---|
| CO-POL-014 5.1 billing CFA | `chk_cfa` unit tests; TC-API-013 (8 checks) |
| 5.2 claim windows | TC-CLM-1-BND-EXP/NE/BRK/SHT; TC-CLM-3xx; unit `test_rules` |
| 5.3 valid claim contents | TC-CLM-1-NEG-NOBATCH, NEG-NOINV, NEG-TYPE; input-problem tests |
| 5.4 no invoice route | TC-CLM-1-NEG-NOINV; letter text tests |
| 5.5 quantity limit, part credit | TC-CLM-1-BND-QTY-*; TC-BKT-005 |
| 5.6 register, duplicates, verify 10 days, credit 30 days | TC-CLM-403..405; TC-BKT-006; TC-CON-001 |
| 5.7 value = qty × PTS | TC-BKT-005 |
| 7.1 / 7.2 shelf life and 60-day block | TC-STK-1-*; Backtesting section 1 |
| CF 6.3 / Sch 2 2.3 pick order | TC-STK-1-* (one pick-now, oldest first) |
| CF Sch 2 2.5 CDC returns | TC-STK-201; TC-ALC-201; expected failure TC-SEC-011 (role) |
| CO-POL-014 4.3–4.5 schemes | TC-ALC-202; Backtesting section 1 |
| ADR 0002 one decision, reasons | TC-CLM-401, 402; TC-CON-002; TC-E2E-003, 004 |
| ADR 0004 citations | TC-SRC-101, 102; TC-E2E-010 |
| ADR 0006 email is data, privacy | TC-SEC-007; TC-CLM-406 |
| ADR 0013 new claims | TC-CLM-2xx, 403–405; TC-E2E-005, 006, 011 |
| ADR 0014 / 0015 / 0016 screens | TC-STK, TC-ALC, TC-DIG, TC-E2E-001, 002, 007, 008 |

## I. Not executed, and why

- **Live model tests (30).** Opt-in, cost money. The model is only a fallback reader; no test
  reached it.
- **Vercel runtime.** Not deployed in this session: cold starts, CDN headers via `vercel.json`, and
  the read-only disk are not measured there.
- **Dependency vulnerability scan.** No scanner run (pip-audit, npm audit).
- **Spreadsheet formula recalculation.** LibreOffice isn't installed, so the summary formulas will
  calculate when the file is opened. The counts were checked in Python.
- **Different user roles.** None exist in the app.

## J. Run log: tests that were wrong, not the app

Each was fixed in the test and re-run. The app was not changed for these.
- Two synthetic emails reused the subject "Expiry claim", which correctly reads as a claim.
- EML-018 returns no lines (null), which the test didn't handle.
- A test looked up a field the schemes endpoint doesn't return.
- Browser locators matched hidden tabs; they're now scoped to the visible screen.
- One browser journey's claim was 174 days past expiry, so approving it correctly needed a reason.
- Batch H2550579 was paired with the wrong product in an earlier probe; the new validation (B3)
  refused it, which is correct.

## K. Recommendations

1. **Settle O-01 and O-02:** sign-in, then roles mapped to the C&F steps.
2. **Settle O-03:** a hosted database behind `store.py`, `stock_log.py` and `audit.py`.
3. **O-05:** relabel the forecast as "likely"; consider recent sell-through; re-run the backtest.
4. **O-06:** a daily extract refresh so new claims check against current sales.
5. **CI:** run the unit suite and the QA suite (or at least `test_01` to `test_06`) on every change.
