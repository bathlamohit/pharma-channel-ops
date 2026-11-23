# Project Sankalp pilot

One LangGraph workflow with three entry points: a **claims desk** for Commercial Finance,
an **expiry and dispatch watch** for Supply Chain, and an **allocation view** for Demand
Planning and RSMs. Code applies every rule, every number cites its file and rows, and a
person signs every credit note. All data is fictional teaching material.

Plan and design: [Final Plan](https://claude.ai/artifact/4yZwzq4wwjs6TKyuu1dovi) ·
[Workflow v2](https://claude.ai/artifact/DnfKWnGhgXmSAy8kVxcMjg) ·
[Discovery](https://claude.ai/artifact/6a7jwXcFEeaZY3fUcVEQpj) ·
[SteerCo](https://claude.ai/artifact/Ar8LLnG5WmhpztPHL8MsFj)

Design decisions and why: [docs/adr/](docs/adr/README.md).

## Layout

```
app.py                  FastAPI: /api/claim/*, /api/watch, /api/source, /api/decision (Vercel entrypoint)
agent/
  policy.py             every policy number with its clause
  state.py              graph state, Citation, CheckResult, extraction form
  tools.py              lookups over data/clean/, each returns rows + citation
  policy.py             CO-POL-014 clauses, thresholds, reason codes, letter wording
  rules.py              the eight claim checks, input checks, decide(), recommend()
  reader.py             reads mailbox emails by rules (the model is only a fallback)
  store.py              new claims: data/claims_store.jsonl, claim numbers, status, due dates
  stock.py              expiry & dispatch plan per batch: block, consent, CDC return, pick order
  stock_log.py          who did what about it: data/stock_actions.jsonl
  demand.py             demand from invoices: order lines, scheme by code, normal month, unmet once, shares (ADR 0017)
  allocation.py         allocation per CFA and product: top-up from the CDC to 2 months, returns, shares, what changed, schemes
  digest.py             weekly digest by owner, built from the plans above, with email text
  claim_nodes.py        extract_claim, resolve_records, check nodes, decide_route, explain + letters, draft_reply (templates)
  watch.py              six watch views + build_digest
  guard.py              cite_and_format: strips uncited numbers
  audit.py              audit log and human decisions
  graph.py              the StateGraph
  llm.py                the only file that knows the model provider (OpenRouter)
scripts/build_tables.py clean data/raw/ -> data/clean/ with a fix log
data/raw/               the seven CSVs from the data pack, never edited
data/clean/             cleaned tables (built, committed for Vercel)
frontend/               React (Vite) source: src/App.jsx, src/components/*
docs/adr/               architecture decision records
public/                 built page (npm run build in frontend/), served by FastAPI and Vercel
tests/                  pytest, no API key needed
```

## The claim checks

| # | Check | Rule | On failure |
|---|---|---|---|
| 1 | duplicate | same stockist, batch and quantity already claimed (CF 2.6.3) | reject |
| 2 | window | any claim >90 days after batch expiry; breakage/short >7 days after invoice (RP 5.2); near expiry >90 days before expiry | reject if late; person if early |
| 3 | supplied | batch billed to this stockist before the claim (RP 5.5) | reject |
| 4 | quantity | all claims ≤ packs supplied incl. free (RP 5.5) | person |
| 5 | invoice_ref | present and shows this batch to this stockist (RP 5.3, 5.4) | person |
| 6 | batch | exists; product and expiry match; pre-Oct-2023 unverifiable | person |
| 7 | value | value = qty × PTS (RP 5.7) | person |

## Status

| Part | State |
|---|---|
| Cleaning script, tools, eight checks, graph wiring, API, page | skeleton working |
| Deterministic claim handling: rules reader, templates, recommendation, settled guard, override reasons (ADR 0012) | done |
| New claims: paste an email or enter a claim form, claim numbers, status to credit note (ADR 0013) | done locally; hosted store open |
| Expiry & dispatch work screen: per-CFA to-do, pick order, batch-order check, action log (ADR 0014) | done locally |
| Allocation work screen: refill and excess per CFA, moves via the CDC, schemes for NSM and CFO (ADR 0015) | superseded in part by 0017 |
| Demand from invoices, top-ups to 2 months, returns, current vs FY25 shares, old/new restatement, client note (ADR 0017) | done locally; share change awaits client approval |
| Weekly digest by owner, linked to the work screens, email text (ADR 0016) | done locally |
| End-to-end QA: 385 automated tests, backtests, security, performance, defect register (`testing-report/`) | 21 Nov 2026: 382 pass, 0 fail, 3 known gaps |
| expiry_radar, short_dated, allocation cover, claims_ageing | first version |
| fefo_alert: 3-month pack share >35%; Kolkata alerts from Mar 2026 (FY27Q2 70.7%), no other CFA | done, tested |
| scheme_report: 4.25% vs 0.35% claim rate, ₹4.76 cr excess; free goods ₹3.954 cr over 3% cap | done, tested |
| Allocation: unfilled ₹18.30 cr in H1 (old) restated to ₹4.01 cr + ₹14.29 cr of cut scheme orders; donor moves retired (ADR 0017) | restated, tested |
| Claim check set: 30 emails + 8 register claims with agreed answers (`tests/check_set.json`) | passing offline; live extraction 30/30 with gpt-4o-mini (`pytest -q -m live`) |
| Multi-line emails, duplicate lines within one email, status lookups by claim or batch | done, in check set |
| Source-row viewer on the page ("Show rows" on any source) | done |
| Back-test (`python -m agent.backtest`): ₹21.9 L, ₹7.25 L, ₹11.2 L reproduced by the live rules | done, tested |
| Allocation cover on value: old Kolkata 3.31, Lucknow 0.32, national 1.74; now 1.84, 0.14, 0.85 from invoices (ADR 0017) | restated, tested |
| Audit log store on Vercel | open decision |

## Run

```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python scripts/build_tables.py
cp .env.example .env               # add your OpenRouter key
pytest -q
uvicorn app:app --reload           # open http://127.0.0.1:8000
```

Working on the page: in a second terminal, `cd frontend && npm install && npm run dev`, open
http://127.0.0.1:5173 (it proxies `/api` to uvicorn), then `npm run build` to update `public/`.

## Deploy
Push to GitHub, import in Vercel, add `OPENROUTER_API_KEY`, deploy. `data/clean/` is committed so
the function loads pre-cleaned tables on a cold start. Vercel keeps no disk between requests, so
the audit log needs a hosted store (open decision).

## Limits to state when presenting
Claims figures are past rates. Allocation is sales recovered, not profit. The scheme saving is
not measured. The expiry-claims ratio moves slowly; the claims desk is the first proof.
