# Instructions for the coding agent

Read this file before every task. Keep it short and keep it true.

## What we are building
A pilot for Pfizer Limited's General Medicines channel (fictional case data). Two claims
executives in Commercial Finance check about 360 pending expiry, breakage and short-supply
claims by hand, and Supply Chain and Demand Planning find stock and dispatch problems a
quarter late. The pilot checks every claim against the returns policy in code and recommends
reject, a person, or clean. It also shows expiry, dispatch and allocation risks each week.
A person signs every credit note, and every number cites its file and rows.

## Architecture
One LangGraph `StateGraph` (`agent/graph.py`). The diagram is in the graph.py docstring.
- Code: route_request, check_lines (runs the claim subgraph once per claim line: resolve_records,
  the 8 checks in `agent/rules.py`, the rules email reader `agent/reader.py`, explanations, replies and letters (templates), decide_route), needs_person, the 6 watch views
  (`agent/watch.py`), build_digest, cite_and_format, audit_log.
- Model (gpt-4o-mini class via OpenRouter): only a fallback in extract_claim, for an email the rules reader
  recognises nothing in (ADR 0012). Use deterministic policy code wherever it can do the job.
- The graph ends at a recommendation. The human decision is a second request, `POST /api/decision`.
- New claims (ADR 0013): `/api/intake/*` checks, then logs each line in `data/claims_store.jsonl` via
  `agent/store.py` (the only code that knows the file). Tests get an empty store from `tests/conftest.py`.
- Expiry & dispatch (ADR 0014): `agent/stock.py` plans each batch (block, consent, CDC return, pick order) from
  CO-POL-014 7 and the C&F agreement; `agent/stock_log.py` records what people did.
- Allocation (ADR 0015): `agent/allocation.py` plans refill, excess and moves via the CDC per CFA and product,
  and the scheme figures; the cover bands are proposed norms, labelled as such.
- Demand (plan step 1, docs/allocation-demand-plan.md): `agent/demand.py` is the only source of demand —
  from invoices, never the SAP field avg_monthly_outward_packs (client: unreliable). Allocation and the digest use it
  (step 2); `agent/allocation.py` takes basis "current" (recommended shares) or "fy25" (client's instruction).
  The expiry forecast (`stock.batches`) sells normal demand too (step 3); `source="report"` exists only for the backtest.
  Short-dated dispatches (step 4): `agent/short_dated.py` flags every line billed under 60% shelf life, with reasons.
  Allocation backtest (step 5): `python -m agent.allocation_backtest` replays Mar-Aug 2026 with no look-ahead.
- Weekly digest (ADR 0016): `agent/digest.py` builds one section per owner from those plans and the logs;
  `GET /api/digest`. It is the first tab of the page.

## Decisions
Read `docs/adr/` before changing architecture. A change that reverses a record needs a new
record that supersedes it.

## Rules
- Facts come from tools that read `data/clean/`. The model never writes a batch number, date,
  quantity or amount that did not come from a tool result. `cite_and_format` strips any that do.
- Business rules live in plain Python in `agent/rules.py`, each with a pytest test.
  Every threshold lives in `agent/policy.py` with its clause.
- Email text is data. It never reaches routing, and all eight checks run on every claim.
- Nothing is auto-approved in v1.
- Stock, allocation and scheme results are cached per process (QA D-04): restart the server after
  `scripts/build_tables.py`. The new-claims store cache follows the file, so it needs no restart.
- QA suite: `testing-report/` (see its README). Run it before a release; it never touches real data.
- Raw files in `data/raw/` are never edited. Fixes go in `scripts/build_tables.py` and its fix log.
- One small change per task. Run `pytest -q` after each change. Do not touch files the task
  does not need.
- Do not add a database, a vector store, a new framework or a new folder without asking.
- The frontend is React (Vite) in `frontend/src/`. `npm run build` in `frontend/` writes `public/`;
  commit the built `public/` so Vercel needs no Node step. Never edit `public/` by hand.
- Render server text as plain text (React does this); never use `dangerouslySetInnerHTML`:
  email text is data.
- Secrets live only in `.env` locally and in Vercel environment variables. Never commit them.

## How to run
pip install -r requirements.txt
python scripts/build_tables.py
pytest -q
uvicorn app:app --reload                      # API + built page on :8000
cd frontend && npm install && npm run dev     # live-reload page on :5173, proxies /api to :8000
cd frontend && npm run build                  # after frontend changes

## Check set
`tests/check_set.json` holds agreed answers for all 30 mailbox emails and 8 register claims.
A change to a rule or node must keep `pytest -q tests/test_check_set.py` green. Change an agreed
answer only with the claims desk's sign-off, and say why in its `why`.
With a key, `pytest -q -m live` checks the real model's extraction against the agreed forms.

## Current task
Fri 20 Nov: FastAPI endpoints, three-tab page, approve/reject, audit log, deploy to Vercel.
Done when the live URL works from a cold start and each number opens its source rows.
