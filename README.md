# pharma-channel-ops: Project Sankalp pilot

A working pilot for a pharmaceutical company's distribution channel. It covers three jobs that teams
there do by hand today:

- **Expiry, breakage and short-supply claims.** Two claims executives in Commercial Finance check
  about 360 pending claims against the returns policy.
- **Expiry and dispatch.** Supply Chain finds stock about to expire, and batches picked in the wrong
  order, a quarter late.
- **Allocation.** Demand Planning decides how much stock each C&F (carrying and forwarding agent)
  should get from the central warehouse (CDC).

The pilot checks every claim in code and recommends **reject**, **a person** or **clean**. It turns
stock and sales into a weekly list of jobs for each owner. **A person signs every credit note, and
every number links to the file and rows it came from.**

> All data is fictional teaching material (a case study). No real company, stockist or patient data
> is used.

---

## Contents

1. [What the app does](#what-the-app-does)
2. [How it works](#how-it-works)
3. [Quick start](#quick-start)
4. [Project layout](#project-layout)
5. [The four screens](#the-four-screens)
6. [Claim checks](#claim-checks)
7. [Demand and allocation](#demand-and-allocation)
8. [API](#api)
9. [Data](#data)
10. [Testing](#testing)
11. [Deploying to Vercel](#deploying-to-vercel)
12. [Design decisions (ADRs)](#design-decisions-adrs)
13. [Status](#status)
14. [Limits and open decisions](#limits-and-open-decisions)

---

## What the app does

| Screen | For | What it gives them |
|---|---|---|
| **Weekly digest** | Every owner | One section per owner: the figures that matter, the top jobs (each opens the screen where it's done) and what's been recorded as done. Copies as email text. |
| **Claims desk** | Commercial Finance | Every claim checked against the returns policy (CO-POL-014). Recommends reject / person / clean with the reason, the clause and the source rows. Drafts replies and letters from templates. A person approves or rejects. |
| **Expiry & dispatch** | Supply Chain, C&Fs | A plan per batch: block, bill only with consent, return to the CDC, or pick first. Also a pick order, a batch-order check, a "not moving" watch list, and every dispatch billed under 60% shelf life with its likely reason. |
| **Allocation** | Demand Planning, NSM, CFO | Months of stock per C&F against the 2-month target. Top-ups from the CDC, returns to the CDC, allocation shares, old vs new figures with the reason, and the scheme report. |

---

## How it works

```
                 ┌───────────────────────── FastAPI (app.py) ─────────────────────────┐
 React page  ──► │  /api/claim/*  /api/intake/*   ──►  LangGraph StateGraph (graph.py) │
 (public/)       │                                      ├─ read email (rules first)    │
                 │                                      ├─ 8 claim checks (rules.py)   │
                 │                                      ├─ recommend, explain, letters │
                 │                                      └─ cite_and_format, audit log  │
                 │  /api/stock/*       ──► stock.py, short_dated.py, stock_log.py       │
                 │  /api/allocation/*  ──► demand.py, allocation.py                     │
                 │  /api/digest        ──► digest.py (built from the plans above)       │
                 └───────────────────────────── reads data/clean/*.csv ─────────────────┘
```

**Rules come first.** Every business rule and threshold is plain Python (`agent/rules.py`,
`agent/policy.py`), each with its policy clause and a test. The language model (gpt-4o-mini class, via
OpenRouter) is used **only** as a fallback, for a claim email the rules-based reader can't read. With no
API key, everything else still works.

**Every number is cited.** Facts come only from lookup tools over `data/clean/`. `cite_and_format`
strips any number in the output that didn't come from a tool result. On the page, "Show rows" opens the
source rows.

**It recommends, it doesn't decide.** The graph ends at a recommendation. The human decision is a
separate request (`POST /api/decision`), written to an append-only audit log. Nothing is auto-approved.

**Email text is data.** It never steers routing, and all eight checks run on every claim.

---

## Quick start

Requirements: Python 3.12. Node 18+ is needed only if you change the frontend.

```bash
python3.12 -m venv .venv && source .venv/bin/activate
```

```bash
pip install -r requirements.txt
```

```bash
python scripts/build_tables.py
```

```bash
cp .env.example .env
```

The key in `.env` is optional. Without `OPENROUTER_API_KEY`, the model fallback is simply off.

```bash
pytest -q
```

```bash
uvicorn app:app --reload
```

Then open http://127.0.0.1:8000.

### Working on the frontend

The page is React (Vite) in `frontend/`. It builds into `public/`, which FastAPI serves locally and
Vercel serves from its CDN.

```bash
cd frontend && npm install && npm run dev
```

That opens http://127.0.0.1:5173, which forwards `/api` requests to uvicorn on :8000. When you're
done, build and commit `public/`; never edit `public/` by hand:

```bash
cd frontend && npm run build
```

### Useful command-line tools

| Command | What it prints |
|---|---|
| `python -m agent.backtest` | The claim-rule back-test: the verified ₹21.9 L, ₹7.25 L and ₹11.2 L reproduced by the live rules |
| `python -m agent.demand` | Demand from invoices: normal months, shares, months of stock per C&F |
| `python -m agent.allocation_backtest` | Six-month replay of the allocation (Mar–Aug 2026) with no look-ahead |
| `python scripts/client_note.py` | Regenerates `docs/client-note-demand-and-allocation.md` from live figures |
| `python scripts/qa_check.py` | Recomputes the headline figures independently and compares them |
| `python scripts/qa_consistency.py` | Checks that every screen agrees with every other and with its source rows |

---

## Project layout

```
app.py                     FastAPI app and the Vercel entrypoint (all /api routes)
agent/
  graph.py                 the LangGraph StateGraph (diagram in its docstring)
  state.py                 graph state, Citation, CheckResult, extraction form
  policy.py                every threshold with its policy clause
  tools.py                 lookups over data/clean/; each returns rows + citation; shared cached helpers
  rules.py                 the eight claim checks, input checks, decide(), recommend()
  reader.py                reads claim emails with rules (the model is only a fallback)
  claim_nodes.py           graph nodes: extract, resolve records, checks, route, explain, letters, replies
  guard.py                 cite_and_format: strips uncited numbers
  audit.py                 audit log and human decisions (data/audit_log.jsonl)
  store.py                 new claims: claim numbers, status, due dates (data/claims_store.jsonl)
  llm.py                   the only file that knows the model provider (OpenRouter)
  stock.py                 expiry & dispatch plan per batch; not-moving watch list
  stock_log.py             who did what, and when (data/stock_actions.jsonl)
  short_dated.py           dispatches billed under 60% shelf life, with reasons
  demand.py                demand from invoices: the only source of demand
  allocation.py            allocation per C&F and product: top-ups, returns, shares, what changed, schemes
  allocation_backtest.py   replay of the allocation plan, Mar–Aug 2026
  backtest.py              claim-rule back-test
  watch.py                 summary watch views (expiry radar, batch order, cover, schemes, claims ageing)
  digest.py                weekly digest by owner, with email text
scripts/
  build_tables.py          cleans data/raw/ into data/clean/ and writes a fix log
  client_note.py           writes the client note from live figures
  qa_check.py              independent recalculation of the headline figures
  qa_consistency.py        cross-screen and source-row consistency checks
data/
  raw/                     the seven CSVs from the data pack (never edited)
  clean/                   cleaned tables (built, committed so Vercel needn't clean on start)
frontend/                  React (Vite) source: src/App.jsx, src/components/*
public/                    the built page (output of npm run build)
docs/
  adr/                     architecture decision records (0001–0017)
  allocation-demand-plan.md            the six-step demand and allocation plan
  client-note-demand-and-allocation.md note for the client: old vs new figures and why
  claim-desk-review-and-plan.md        claims desk review
  qa-report-2026-11-21.md              QA summary
tests/                     unit and regression tests (pytest, no API key needed)
testing-report/            full QA suite, reports, registers and evidence (see its README)
AGENTS.md                  rules for coding agents working in this repo
vercel.json                Vercel config: one FastAPI app plus security headers
```

---

## The four screens

### Weekly digest (first tab)
One section per owner: Commercial Finance (claims), Supply Chain (expiry and dispatch), Demand
Planning (allocation), and NSM and CFO (schemes). Each section shows:
- the key figures
- the top jobs, each opening the screen and item where it's done
- what's been recorded as done

The Allocation section carries a "Restated" notice that links to the old vs new figures. **Copy**
gives the same digest as email text. Everything is built by code from the same plans as the work
screens; no model is used.

### Claims desk
- **Pending claims** from the register, and **claim emails** from the mailbox.
- **New claims** can be pasted as an email or entered on a form. They get a claim number and are
  tracked through to the credit note.
- Each claim shows the eight checks, the recommendation, the clause behind it and the source rows.
- **Approve / Reject.** Going against the recommendation needs a written reason.

### Expiry & dispatch
One card per C&F, then for the chosen C&F:
- **To do:** block (under 60 days to expiry), bill only with the stockist's consent (under 60% shelf
  life), return to the CDC, or push in dispatch. Each with an act-by date, the clause, and step buttons.
- **Pick order:** batches per product, oldest expiry first, with "Pick now".
- **Batch-order check:** 12 months against the 35% alert line. Kolkata has been over it since
  March 2026.
- **Not moving:** batches that sold under 5% since the previous snapshot. This is a watch list, not a
  forecast.
- **Short-dated dispatches:** every invoice line billed under 60% shelf life in the last four quarters
  (1,171 lines, ₹6.26 cr), with its likely reason and a consent step.

### Allocation
- **By C&F:** months of stock against the 2-month target, and products out of stock, below target,
  on target or in excess.
- **Top-up from CDC:** up to 2 months of allocated volume, at most 1.2 months per shipment
  (CF Sch 2 §2.2).
- **Returns to CDC:** only batches that keep 60% shelf life after 14 days in transit, and only when
  worth at least ₹5 lakh per SKU.
- **Shares:** FY25 shares compared with current shares (each C&F's share of real need).
- **What changed:** old figure, new figure and reason, side by side.
- **Schemes (NSM, CFO):** claim rate on scheme products (4.25% against 0.35%), and free goods against
  the 3% cap.

A toggle switches between **Current shares (recommended)** and **FY25 shares (the client's
instruction)** until the client approves a change.

---

## Claim checks

All eight run on every claim line (`agent/rules.py`, thresholds in `agent/policy.py`):

| # | Check | Rule | On failure |
|---|---|---|---|
| 1 | duplicate | same stockist, batch and quantity already claimed (CF 2.6.3) | reject |
| 2 | window | expiry claims within 90 days after expiry; breakage or short within 7 days of invoice (RP 5.2); near-expiry over 90 days before expiry | reject if late; a person if early |
| 3 | supplied | batch billed to this stockist before the claim (RP 5.5) | reject |
| 4 | quantity | total claimed ≤ packs supplied, including free goods (RP 5.5) | a person |
| 5 | invoice_ref | present, and shows this batch to this stockist (RP 5.3, 5.4) | a person |
| 6 | batch | exists; product and expiry match; batches before Oct 2023 can't be verified | a person |
| 7 | value | value = quantity × PTS (RP 5.7) | a person |
| 8 | cfa | returned to the C&F that billed the stock (CO-POL-014 5.1) | a person |

`tests/check_set.json` holds agreed answers for all 30 mailbox emails and 8 register claims. Any rule
change must keep `pytest -q tests/test_check_set.py` green.

---

## Demand and allocation

As the client instructed, demand comes from **invoices**, not the SAP stock report's
`avg_monthly_outward_packs` field. That field ran at 44–48% of real dispatches at every snapshot. See
ADR 0017 and `docs/client-note-demand-and-allocation.md`.

| Term | Definition |
|---|---|
| Dispatched | invoiced + free packs |
| Ordered | highest `ordered_qty` on an order line, taken once |
| Unmet need | ordered − dispatched on non-scheme lines, counted once per stockist, SKU and month |
| Scheme sales | lines with a scheme code |
| Normal month | average of the last 3 months with no scheme lines |
| Real need | normal month + unmet need |
| Allocated volume | national normal demand × the C&F's share |
| Top-up | min(2 × allocated − stock, 1.2 × allocated), assuming the CDC can supply |

**Headline figures at 30 Sep 2026:**

| Figure | Old (report field) | New (invoices) |
|---|---|---|
| Months of stock, national | 1.74 | 0.85 |
| Kolkata | 3.31 | 1.84 |
| Lucknow | 0.32 | 0.14 |
| Orders not filled, 6 months | ₹18.30 cr | ₹4.01 cr, plus ₹14.29 cr of cut scheme orders |

In the six-month replay, current shares leave ₹2.47 cr of normal orders unfilled, against ₹3.53 cr on
FY25 shares.

---

## API

All responses are JSON. Read endpoints are cached per process. Restart after rebuilding the tables.

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/health` | Health check |
| GET | `/api/claims` | Pending claims from the register |
| GET | `/api/emails` | Claim emails from the mailbox |
| POST | `/api/claim/register` | Run the checks on a register claim |
| POST | `/api/claim/email` | Read and check a claim email |
| GET | `/api/stockists` | Stockist list for the claim form |
| POST | `/api/intake/email` | New claim from a pasted email |
| POST | `/api/intake/form` | New claim from the form |
| GET | `/api/intake` | New claims and their status |
| POST | `/api/intake/status` | Move a new claim on (e.g. credit note issued) |
| POST | `/api/decision` | Record a person's approve/reject decision |
| POST | `/api/source` | The source rows behind a citation |
| POST | `/api/watch` | A summary watch view |
| GET | `/api/digest` | The weekly digest (with email text) |
| GET | `/api/stock/overview` | Expiry & dispatch cards per C&F |
| GET | `/api/stock/plan?cfa=` | Batch plan, pick order and watch list for one C&F |
| POST | `/api/stock/action` | Record a step (block, consent, return, checked with C&F…) |
| GET | `/api/stock/short-dated` | Dispatches under 60% shelf life: summary |
| GET | `/api/stock/short-dated/lines?cfa=&reason=&offset=` | The flagged lines, 50 per page |
| GET | `/api/allocation/overview?basis=current\|fy25` | Allocation cards and national figures |
| GET | `/api/allocation/plan?cfa=&basis=` | Plan per product for one C&F |
| GET | `/api/allocation/topups?basis=` | Top-ups from the CDC |
| GET | `/api/allocation/returns?basis=` | Returns to the CDC |
| GET | `/api/allocation/shares` | FY25 vs current shares |
| GET | `/api/allocation/restatement` | Old vs new figures, with reasons |
| GET | `/api/allocation/schemes` | Scheme report for NSM and CFO |

---

## Data

The seven CSVs in `data/raw/` come from the case data pack. Stock and registers run to 30 Sep 2026.

| File | Contents |
|---|---|
| `primary_sales.csv` | Invoice lines from C&Fs to stockists (ordered, invoiced, free, scheme code) |
| `cnf_stock_snapshot.csv` | Monthly stock per C&F, product, batch and bin |
| `expiry_claims.csv` | The claims register |
| `claim_emails.csv` | The claims mailbox (30 emails) |
| `batch_master.csv` | Batches with manufacture and expiry dates |
| `sku_master.csv` | Products, pack size, shelf life, PTS |
| `stockist_master.csv` | Stockists and their home C&F |

`scripts/build_tables.py` cleans them once into `data/clean/` and records every fix in
`data/clean/fix_log.csv`. Raw files are never edited.

**Local stores** are append-only, locked files, kept out of git:
- `data/claims_store.jsonl` (new claims)
- `data/stock_actions.jsonl` (steps recorded on the work screens)
- `data/audit_log.jsonl` (decisions)

---

## Testing

| Suite | Command | What it covers |
|---|---|---|
| Unit and regression (222) | `pytest -q` | rules, check set, demand, allocation, stock, digest, API |
| Live model check | `pytest -q -m live` | real extraction against agreed answers (needs a key) |
| QA suite (217) | `pytest testing-report/automated_tests -q` | API contract, functional, validation, security, concurrency, performance, backtests, end-to-end UI (Playwright) |
| Independent figures | `python scripts/qa_check.py` | 30 headline figures recomputed separately |
| Consistency | `python scripts/qa_consistency.py` | 101 cross-screen and source-row checks |

The QA suite needs its extra packages and a browser once (see `testing-report/README.md`). No test
writes to the real stores or calls the model: `conftest.py` gives every test temporary stores and
removes the API key.

Reports in `testing-report/`:
- QA executive report
- API, security and performance reports
- backtesting report
- test-case and defect registers (Excel), rebuilt by `build_registers.py`

---

## Deploying to Vercel

1. Import this repository in Vercel.
2. In Project → Settings → Build & Deployment:
   - **Framework Preset:** FastAPI (also set in `vercel.json`)
   - **Root Directory:** the repository root
   - **Build Command:** none
   - **Output Directory:** none
3. Add the environment variable `OPENROUTER_API_KEY` (optional; without it the model fallback is off).
4. Deploy.

How it runs on Vercel:
- `app.py` is the function. Vercel serves `public/` (the built page) from its CDN and sends `/api/*`
  to FastAPI.
- `vercel.json` adds the security headers.
- `data/clean/` is committed, so a cold start loads pre-cleaned tables. The first request takes
  about 2 s.

**Don't add a separate Vite/frontend service.** The page is already built into `public/`, so Vercel
needs no Node build. A Vite service makes Vercel look for `frontend/dist` and fail.

**Vercel keeps no disk between requests.** New claims, recorded steps and decisions don't persist
there until a hosted store is chosen (ADR 0010).

---

## Design decisions (ADRs)

Full list and status: [docs/adr/README.md](docs/adr/README.md).

| ADR | Decision |
|---|---|
| 0001 | One LangGraph workflow, code first |
| 0002 | Recommend, don't decide |
| 0003 | Claim checks in code |
| 0004 | Every number cited |
| 0005 | Clean once, at build time |
| 0006 | Email text is data |
| 0007 | One claim subgraph per line |
| 0008 | Tests reproduce the verified figures |
| 0009 | Metric definitions (partly superseded by 0017) |
| 0010 | FastAPI on Vercel, stateless |
| 0011 | React frontend built to `public/` |
| 0012 | Deterministic claim handling |
| 0013 | New-claims file store |
| 0014 | Expiry and dispatch as a work screen |
| 0015 | Allocation as a work screen (partly superseded by 0017) |
| 0016 | Weekly digest by owner |
| 0017 | Demand from invoices; allocation on current shares |

---

## Status

| Part | State |
|---|---|
| Claims: eight checks, rules-based email reader, templates, recommendations, override reasons | done |
| New claims: email or form, claim numbers, status to credit note | done locally; hosted store open |
| Expiry & dispatch work screen, not-moving watch list, short-dated dispatch flags | done locally |
| Demand from invoices, top-ups, returns, current vs FY25 shares, restatement, client note | done locally; share change awaits client approval |
| Weekly digest by owner | done locally |
| QA: unit, QA suite, independent figures, consistency | all passing (3 known gaps recorded as expected failures) |
| Hosted store for decisions and steps on Vercel | open decision |

---

## Limits and open decisions

**Limits:**
- Claims figures are past rates.
- Allocation is sales recovered, not profit.
- The scheme saving isn't measured.
- The expiry-claims ratio moves slowly; the claims desk is the first proof.

**Assumptions** stated on screen:
- the CDC can supply top-ups
- normal demand stands in for the national forecast
- FY25 shares are the client's instruction until a change is approved

**Open decisions for the client:**
- approve the share change, and whether to limit it to 5 points per review
- confirm the 70% "arrived old" cut-off
- a mid-month top-up when demand spikes
- where decisions and steps are stored once deployed
