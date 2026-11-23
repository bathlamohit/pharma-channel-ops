# Claim desk: test findings and plan for professional claims handling

- App tested: https://claim-desk-woad.vercel.app/ (rules only: `model_key_set: false`)
- Date: 20 Nov 2026
- How: 3 sample claims, 1 credited register claim, all 30 sample emails, 14 hand-built new claims,
  7 free-text emails, and the credited-claims audit. Decisions were **not** posted, so the app's
  decision log was not written to.

## 1. Summary

The rules engine does the core job well. It applies policy CO-POL-014 v4.2 as eight numbered
checks, each with its clause and evidence row. It never approves a claim it can't fully verify,
catches duplicates inside an email and against the register, corrects a mistyped batch only
when exactly one batch matches, flags the injection email, and won't disclose another stockist's
claim status.

It isn't ready for real use, for three reasons:

1. **It accepts inputs no claim can have.** A claim for **-38 packs comes back "Approve" with a
   recommended credit of -₹5,749.40**. A claim for 0.5 packs is also approved.
2. **It re-recommends money that has already been paid.** Checking `CLM-2404-04177`, already
   credited on note CN/S02/2405/45970, returns "Approve" with a ₹3,936.80 credit. Nothing on the
   result says the claim was already settled.
3. **Anyone with the link can use it, and its log doesn't record who decided.** There is no
   sign-in. A decision is logged without the name of the person who made it, and every new
   claim is logged under the same id, `new-claim`.

## 2. Findings

Severity: **P0** means a wrong credit or a control gap, so fix before any real claim goes
through. **P1** means wrong or unclear handling. **P2** is polish.

| # | Sev | What happens | How to reproduce |
|---|---|---|---|
| F1 | P0 | Negative quantity approved with a negative credit | New claim from the EML-001 line, qty `-38`: APPROVE, credit -5749.40 |
| F2 | P0 | Fractional quantity approved | Same line, qty `0.5`: APPROVE, credit 75.65 |
| F3 | P0 | Already-credited claim recommended for approval again | Claim number `CLM-2404-04177`: APPROVE, credit 3,936.80 |
| F4 | P0 | No sign-in; anyone with the URL can run claims, read register facts and run the audit | Open the URL |
| F5 | P0 | Decision log has no decider, and all new claims share one id | `app.js` posts `{claim_ref: … \|\| "new-claim", action, reason}`, with no user field |
| F6 | P1 | "Resubmission of" accepts any claim number, even another stockist's credited claim, and judges the time window on that claim's date | New claim with `resubmission_of: CLM-2404-04177` (STK0145, credited): note says "window judged on its claim date 18-04-2024" |
| F7 | P1 | Unknown claim type accepted; a blank type silently becomes "Near expiry" | `claim_type: "Damaged"` is checked as breakage; `null` comes back as "Near expiry" |
| F8 | P1 | Future claim dates accepted; a blank date silently becomes today | `claim_date: 2030-01-01` is rejected only on the window rule |
| F9 | P1 | Over-quantity claims rejected in full, even when most of the quantity is valid | `CLM-2608-01758`: 1,782 claimed, 1,773 supplied, so the whole claim is rejected over 9 packs. The app works out "allowable 1773" but offers no partial approval |
| F10 | P1 | Unknown stockist gets "Reject" instead of "not in the stockist master" | `STK9999`: REJECT because the batch was never invoiced to it |
| F11 | P1 | Without a model key, free text is barely read | "credit 500 packs of batch K2440124…" and a Hinglish email both come back with every field missing. EML-006 and EML-018 can't be read at all |
| F12 | P1 | Non-claims are forwarded to "the right team (not a claim)", with no team named; empty email text is treated the same way | EML-028 to 030; `email_text: "   "` |
| F13 | P1 | Status replies don't flag claims past the 30-day settlement target | EML-023: pending 50 days, and the draft just says "Pending" |
| F14 | P1 | The audit figure disagrees with the verified back-test: ₹87.9 L across 373 claims here, against ₹21.9 L across 181 claims in the agreed analysis. The difference isn't explained on the page | Run audit |
| F15 | P1 | The same check shows two different "supplied" figures | `CLM-2404-04177`: R1 says 1,855 packs invoiced, R4 says 705 supplied |
| F16 | P2 | A 1 MB email body is accepted | 200 OK |
| F17 | P2 | Unknown claim number returns HTTP 200 with an error inside the body | `CLM-0000-00000` |
| F18 | P2 | Money values have floating-point noise in the API | credit `5749.400000000001` |
| F19 | P2 | Sample link "early near-expiry" opens an Expired claim | `CLM-2603-02697` is type Expired, 10 days after expiry |
| F20 | P2 | A line says "do not reject" while the overall result is Reject | EML-016: R1 says "escalate, do not reject", and R3 fails at 865 days |
| F21 | P2 | Repeated line in EML-013 loses its claim type on line 2 | `claim_type: null` on #2 |

## 3. What professional claims handling looks like

A claim goes through stages, each with an owner, a time limit and a record. Today's tool covers
step 3 and part of step 4.

```
1 Intake → 2 Register & acknowledge → 3 Validate → 4 Decide → 5 Verify goods → 6 Credit note → 7 Close & report
```

| Stage | What happens | Owner | Target time |
|---|---|---|---|
| 1. Intake | Email, portal or register entry. Sender identified from the mailbox, never from the email text | System | Same day |
| 2. Register & acknowledge | Claim number issued, duplicates caught before a number is issued, acknowledgement sent with the number and expected date | System, Claims exec | 1 working day |
| 3. Validate | The eight policy checks with evidence. Inputs rejected at the door if no claim could have them | System | Minutes |
| 4. Decide | Approve, partially approve, reject, or ask for information. Reason code required. Second sign-off above a value limit. Override needs a written reason | Claims exec, Approver | 5 working days |
| 5. Verify goods | Expired and near-expiry goods counted at the CFA or by an auditor, and a destruction certificate attached before the credit note | CFA, Field audit | 10 working days |
| 6. Credit note | Raised for the approved quantity × PTS, rounded to the paisa, linked to the claim | Commercial Finance | Within 30 days of claim (CLAIM_SETTLE_DAYS) |
| 7. Close & report | Stockist told the outcome with reasons and clause. Ageing, rejection reasons and repeat claimants reported weekly | Claims lead | Weekly |

**Status model** (one status at a time, every change logged with who, when and why):
`Received → Registered → Validated → Awaiting information | Awaiting approval → Approved (full or partial) | Rejected → Goods verified → Credit note raised → Closed`

**Reason codes.** Every reject or partial decision carries one or more, so outcomes can be
counted: `OUT_OF_WINDOW`, `NOT_SUPPLIED`, `OVER_QUANTITY`, `DUPLICATE`, `NO_INVOICE_REF`,
`BATCH_MISMATCH`, `WRONG_CFA`, `VALUE_MISMATCH`, `ALREADY_CREDITED`, `INFO_REQUESTED`.

**Approval limits.** These are a proposal; Commercial Finance needs to confirm them.

| Recommended credit | Who signs |
|---|---|
| Up to ₹25,000, all checks passed | Claims executive |
| ₹25,000 to ₹2,00,000, or any override | Claims manager |
| Over ₹2,00,000, or a repeat claimant (3 or more in 90 days) | Commercial Finance controller |

**Stockist letters.** Four templates, written by code from facts (acknowledged, information
needed, decision, credit note raised). Each names the claim number, the clause and the next
step. A person sends; the tool never sends.

## 4. Plan

### Phase 0: fix before any real claim (1 week)

| Fix | Closes | Done when |
|---|---|---|
| Input validation at the API: quantity is a whole number of at least 1, claim type is one of three, claim date not in the future, required fields present, body under 50 KB. Fail with HTTP 422 and the field name | F1, F2, F7, F8, F16 | Tests post each bad input and get 422. None reaches the rules |
| "Already credited / already decided" guard as rule R0. A register claim with status Credited or Rejected returns ALREADY_LOGGED with the credit note, never APPROVE | F3 | `CLM-2404-04177` returns ALREADY_LOGGED with CN/S02/2405/45970 |
| Resubmission only of the same stockist's rejected claim for the same batch, within 30 days of the rejection | F6 | The F6 case returns NEEDS_PERSON with "resubmission does not match" |
| Sign-in (Vercel password protection now; company SSO later). Decider's name taken from the session and stored with every decision. Unique id for every new claim | F4, F5 | The log shows who decided, when, the recommendation, the action and the reason. No anonymous access |
| Durable decision store (hosted Postgres or KV). Today the log does not survive on Vercel | F5 | A decision is still there after a redeploy |
| Unknown claim number returns 404; money rounded to 2 decimals in the API | F17, F18 | Tests |

### Phase 1: handle claims the way the desk does (2–3 weeks)

| Change | Closes |
|---|---|
| Partial approval: when only quantity fails, recommend "Approve 1,773 of 1,782 packs" with the credit for 1,773 and reason `OVER_QUANTITY`. A person confirms | F9 |
| Unknown stockist → NEEDS_PERSON "not in the stockist master", not Reject | F10 |
| Turn on the model for reading emails (key set in Vercel), keeping the rules as a fallback. Extraction tested against the agreed answers for all 30 emails | F11 |
| Name the team for every non-claim (Logistics, Sales, Accounts) from a routing table. Empty text → 422 | F12 |
| Status replies show days pending against the 30-day target, flag overdue claims, and offer an apology line plus the expected date | F13 |
| Reason codes on every outcome, and the stockist letter templates | — |
| One "supplied" figure per check, with the date range it covers | F15 |
| Consistent line wording; sample links that match their labels; keep the claim type on repeated lines | F19–F21 |

### Phase 2: control and reporting (3–4 weeks)

- Approval limits with second sign-off; overrides always need a manager.
- Status model and SLA timers; a "my queue" view sorted by days to breach.
- Goods-verification step: CFA count and destruction certificate uploaded before the credit note.
- Weekly report: ageing buckets (0–15, 16–30, over 30 days), approval and rejection by reason
  code, top repeat claimants, value recovered by the checks.
- Reconcile the audit figure (₹87.9 L) with the agreed back-test (₹21.9 L). Show both, with the
  definition of each, and have the claims desk sign off which one is reported.

## 5. Acceptance tests to add

Each P0 and P1 finding becomes a test using the exact reproduction above, so it can't come back.
Add these alongside the 30-email check set:

- negative, zero, fractional and huge quantities
- future and blank dates
- unknown claim type
- re-checking a credited claim
- resubmission of another stockist's claim
- unknown stockist
- empty email and oversized email
- a decision posted without a signed-in user (must fail)

## 6. Open decisions for the client

1. Approval limits (section 3).
2. Which audit figure is reported: the strict re-check (₹87.9 L) or the agreed back-test (₹21.9 L).
3. Whether partial approvals are allowed under CO-POL-014, or over-quantity claims must be
   returned to the stockist to re-lodge.
4. Where decisions are stored, and for how long.
5. Whether goods verification is needed for every claim or only above a value limit.

## 7. Applied to project_sankalp (20 Nov 2026)

The lessons above were built into our own pilot with deterministic policy code (ADR 0012), not
into the deployed build:

| Finding | In our pilot |
|---|---|
| F1, F2, F7, F8 impossible inputs | `rules.input_problems`: quantity a whole number of at least 1, claim type from CO-POL-014 5.2, no future or missing date; the line goes to a person |
| F3 settled claim recommended again | route `already_decided` with the credit note; approving it returns 409 |
| F5 decisions without a decider or reason | name required; going against the recommendation needs a reason, logged as an override; the recommendation is read from the server log |
| F9 over-quantity rejected in full | `approve_part` with the claimable packs and credit, for a person to confirm |
| F11 free text barely read | rules reader matches the agreed form on all 30 emails; the model is only a fallback |
| F12 vague forwards | the team is named from `policy.FORWARD_RULES` |
| F13 overdue not flagged | status replies give days pending against the 30-day limit, with an apology and escalation |
| F16 oversized requests | 413 over 64 KB |
| F18 money noise | credits rounded to the paisa; page shows Indian grouping |
| (new) CFA rule, CO-POL-014 5.1 | eighth check `chk_cfa` |

Not done, as in section 6: sign-in (F4), a durable decision store, approval limits, goods
verification, and the reconciliation of the two audit figures.
