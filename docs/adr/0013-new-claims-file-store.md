# 0013. New claims: intake, claim numbers and status, kept in an append-only file

- Status: Accepted for local use; the hosted store is still an open decision (see 0010)
- Date: 2026-11-20

## Context
The pilot only checked claims already in the data extract: a register claim number or one of the
30 sample emails. A real desk receives new claims every day. The C&F procedure (SC-AGR-CF-003
Sch 2 2.6) and CO-POL-014 5.6 say every claim is:
- logged on arrival with a number `CLM-yymm-nnnnn`
- checked against earlier claims on the same stockist and batch
- physically verified within 10 working days
- credited within 30 days

AGENTS.md says not to add a database without asking. The product owner chose a file store for
now.

## Decision
**Intake, two ways.** Both run the same graph: rules, no model.
- `POST /api/intake/email`: an email that arrived in the claims mailbox. The desk picks the
  mailbox's stockist account; it is never read from the text. Unknown sender: the lines are
  logged as *Awaiting info*.
- `POST /api/intake/form`: the stockist's claim form (5.3), typed in by the desk or C&F, with the
  name of the person entering it.

**Check, then log.** Each line is checked against the register and earlier new claims. Each line
then gets the next claim number: the register's running serial continues after 04518, with the
received month. The acknowledgement letter quotes the numbers. Status questions are answered
and not logged.

**The store** (`agent/store.py`): `data/claims_store.jsonl`, path from `CLAIMS_STORE`,
gitignored. One JSON event per line: `registered`, `checked`, `status`, `decision`. Nothing is
edited or deleted; a claim's state is its events in order. Writes take a file lock.

**Statuses and allowed moves:**

| From | To |
|---|---|
| Received | Awaiting info, Verified, On hold, Rejected |
| Awaiting info | Received, Verified, On hold, Rejected |
| Verified | Approved, Rejected, On hold |
| On hold | Received, Verified, Approved, Rejected |
| Approved | Credit note raised (needs the credit note number) |
| Credit note raised, Rejected | Closed |

- Approve and reject go through `POST /api/decision` with `claim_no`, so they keep the override
  rule (0012).
- Approval needs the CFA's verification first (5.6), so `/api/decision` returns 409 until then.
- Other moves go through `POST /api/intake/status`.

**Due dates**, shown with overdue flags:
- verify by: received + 10 working days (weekends skipped, no holiday calendar yet)
- credit note by: received + 30 days

**Checks see new claims.** `tools.get_prior_claims` adds stored claims, shaped as register rows:
a credit note means Credited, a rejection means Rejected, anything else is Pending. The
duplicate and quantity checks therefore count them.

**The page.** A "+ New claim" button offers two modes, Paste an email and Enter a claim form.
New claims sit at the top of the inbox under *New*, with status and overdue tags. Opening one
shows its status card: due dates, history and the next moves.

## Alternatives considered
- **Edit `expiry_claims.csv`.** Rejected: the cleaned tables are rebuilt from raw data and are
  committed; claims would be lost or mixed with the extract.
- **SQLite.** Close to the file in effort, but it is a database (needs asking) and still does
  not persist on Vercel.
- **Hosted Postgres now.** Right for the deployed pilot; needs the client's choice. `store.py` is
  the only module to change.

## Consequences
- Locally, new claims survive restarts. On Vercel they do not persist: the store must move to a
  hosted database before the desk uses the deployed app for real claims.
- Checks still use the extract (to 30 Sep 2026) for sales, batches and stock. A genuine claim on
  stock invoiced after that fails "never supplied" until a daily SAP extract refreshes
  `data/clean/`.
- Mailbox addresses are not in the stockist master, so the desk picks the account. An address
  table from the client would let the mailbox rule fill it.
- Tests use an empty temporary store (`tests/conftest.py`), never the developer's file.
