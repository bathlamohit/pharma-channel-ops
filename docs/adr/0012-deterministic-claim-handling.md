# 0012. Claims are handled by policy code; the model is only a fallback reader

- Status: Accepted (amends 0001 and 0003)
- Date: 2026-11-20

## Context
Testing a separate rules-only claim desk build showed what the claims desk needs beyond the seven
checks: impossible inputs rejected at the door, settled claims never recommended again, partial
credit when only the quantity limit fails, reason codes, letters to the stockist, and decisions
that record who overrode what. It also showed the 30 mailbox emails can be read by rules.
The product owner asked that the model be used only where code cannot do the job, and that
claims be handled by the policy document: CO-POL-014 v4.2 section 5 and the C&F procedure
SC-AGR-CF-003 Schedule 2 section 2.6.

## Decision
**Policy in one file.** `agent/policy.py` cites CO-POL-014 clauses (5.1 to 5.7, 8.3) and the C&F
procedure. It also holds the claim types, the 30-day settlement and 10-working-day verification
limits, reason codes, what to ask the stockist for each gap, and who handles non-claims.

**Eight checks.** The seven of 0003, plus `chk_cfa` (5.1): goods are returned only to the CFA that
billed them. Emails carry no CFA, so the letter names the billing CFA. A check that does not
apply returns `skip`, which counts as neither pass nor fail.

**Input checks before the rules** (`rules.input_problems`). Each of these sends the line to a
person:
- quantity not a whole number of at least 1
- claim type not one of the four in 5.2
- claim date missing or in the future

**Settled claims.** A register claim already Credited or Rejected gets the route
`already_decided` with its credit note. `POST /api/decision` refuses to approve it (409).

**Recommendation in packs and rupees** (`rules.recommend`), for each line:

| Action | When | Credit |
|---|---|---|
| approve | every check passes | quantity × PTS (5.7) |
| approve_part | only the quantity limit (5.5) fails | the packs still claimable; a person decides whether to part-credit or return the claim (the policy sets the limit, not this choice) |
| reject | a hard rule fails | none, with reason codes |
| review | anything else | none; the amount if approved in full is shown |
| missing_info | a record or input is missing | none |

**Reading emails.** The rules reader (`agent/reader.py`) reads batch, quantity (including
"boxes of N"), expiry, invoice, claim numbers, breakage or short-supply wording, status
questions, and the topic for forwarding. It matches the agreed form on all 30 check-set emails.
The model is asked only when the reader recognises nothing in an email and a key is set; with
no key, a person reads it. Who read each email is returned as `read_by`.

**Text from templates, not a model:**
- the explanation for each line: route, failing clauses, recommendation and reason codes
- status replies: register facts, plus days pending against the 30-day limit, with an apology
  and escalation when the limit is passed
- forwards that name the team
- the acknowledgement letter for claims: what was received and what is still needed under 5.3
  to 5.5, with the 5.1, 5.3 and 5.6 instructions

The number guard (0004) now runs only on text a model wrote (`state.model_text`).

**Decisions.**
- The name of the person deciding is required.
- Going against the recommendation (approving a reject or needs-person line, or rejecting a
  clean one) needs a written reason of at least 10 characters. It is logged as an override.
- Where the server kept the recommendation, it is read from the log, not taken from the page.
- Request bodies over 64 KB are refused (413).

## Alternatives considered
- **Keep the model for wording.** Rejected: the wording carries no judgment the checks do not
  already state, it costs a call per claim, and it needed a guard to stop invented numbers.
- **Drop the model completely.** Rejected for now: an email in an unexpected language or layout
  would otherwise go unread. The live tests keep the fallback honest.
- **Reject over-quantity claims outright.** Rejected: 5.5 sets a limit, not a penalty. Whether
  to part-credit is the client's open decision, so the line goes to a person with the figure.

## Consequences
- 0 model calls for every register claim and all 30 mailbox emails (was 1 and 2). Same answers
  every run.
- The check set's `CLM-2605-04488` now expects `already_decided`. It is credited, and the back-test
  still counts it as a double credit.
- Still open:
  - sign-in, so the decider's name comes from a session rather than a text field
  - a durable decision store on Vercel (0010)
  - whether partial credit is allowed under CO-POL-014
