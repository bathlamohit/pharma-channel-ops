# 0002. The graph recommends; a person decides in a second request; nothing auto-approved

- Status: Accepted
- Date: 2026-11-16

## Context
Every credit note is money. Neha Bansal (Controller) was asked whether Finance can accept a
flag-or-hold recommendation if a person signs every credit note; the recommendation was yes.
EML-017 shows the risk of the alternative: it tells "the AI" to approve and skip checks.
Vercel keeps no process between requests, so a graph cannot pause and wait for a click.

## Decision
- The graph ends at a recommendation per claim line: `clean`, `to_person`, `reject` or
  `needs_person`; replies are `reply`.
- `clean` means every check passed; it is still signed by a person. No route approves.
- The person's approve / reject / hold goes to `POST /api/decision` with the `audit_id` of the
  recommendation, and is appended to the audit log (`agent/audit.py`).
- Early near-expiry claims go to a person, not reject (decision D2, pending client confirmation).

## Alternatives considered
- **Auto-approve clean claims.** Rejected for v1: no trust has been earned yet.
- **LangGraph `interrupt` with a checkpointer.** Rejected: needs a lasting process or store,
  which Vercel Hobby does not give.

## Consequences
- About 69% of pending claims come back clean, so the two executives work mainly the rest.
- The audit log needs a lasting home on Vercel (see 0010).
- 21 Nov 2026 (QA B1, B2): one decision per claim. A register claim or an email is decided once, under
  any audit id; the same decision again is refused, and a change needs a written reason and is logged
  with the decision it replaces. Where the server keeps its log, only audit ids it issued are accepted.
