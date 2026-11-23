# 0010. FastAPI on Vercel, stateless, with pre-cleaned tables committed

- Status: Accepted; audit log store is an open decision
- Date: 2026-11-16

## Context
The course starter deploys FastAPI to Vercel Hobby. Vercel keeps no process between requests and
no lasting disk. The pilot is read-only on static extracts and writes nothing to client systems.

## Decision
- `app.py` exposes: `GET /api/health`, `GET /api/claims`, `GET /api/emails`,
  `POST /api/claim/register`, `POST /api/claim/email`, `POST /api/watch` (tab: watch,
  allocation, weekly), `POST /api/source` (a citation's rows, 50 a page, only the seven
  cleaned source tables), `POST /api/decision`.
- Tables load from `data/clean/` once per process (`lru_cache`); `data/clean/` is committed.
- Secrets: `OPENROUTER_API_KEY` in `.env` locally (gitignored) and in Vercel environment variables.
- The audit log is a JSONL file locally (`AUDIT_LOG`, default `data/audit_log.jsonl`). On a
  read-only disk the record is returned with `stored: false` so the page can say so.

## Alternatives considered
- **A database now.** Deferred: the open question "where is the audit log kept?" is the client's;
  a small hosted store is the recommendation.

## Consequences
- Cold start loads about 22 MB of CSVs; pandas adds to the function size.
- Until the audit store is chosen, decisions on Vercel are not kept.
- 20 Nov 2026: new claims are kept in `data/claims_store.jsonl` (0013). Like the audit log, it does
  not persist on Vercel; both move to the hosted store once the client chooses it.
