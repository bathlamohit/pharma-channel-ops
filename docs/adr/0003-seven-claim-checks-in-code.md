# 0003. Seven claim checks as pure functions, thresholds in one policy file

- Status: Accepted; amended by 0012 (eighth check, CFA rule CO-POL-014 5.1; input checks; recommendation)
- Date: 2026-11-17 (rules corrected 2026-11-18 by the back-test)

## Context
The team's note checked only duplicates and quantity. The verified loss (Rs 21.9 L a year of
credits that break a hard rule) comes from the returns policy and the C&F procedure.

## Decision
Seven checks in `agent/rules.py`, each a pure function `(claim, records) -> CheckResult` with
outcome, clause, detail and citations, run in parallel in the claim subgraph:

| Check | Rule | On failure |
|---|---|---|
| duplicate | same stockist, batch and quantity already claimed by an earlier, non-rejected claim (CF 2.6.3) | reject |
| window | any claim over 90 days after the batch expires; breakage or short supply over 7 days after the invoice (RP 5.2) | reject |
| window | near expiry raised over 90 days before expiry | to a person |
| supplied | batch billed to this stockist before the claim date (RP 5.5) | reject |
| quantity | all claims on the batch <= packs supplied, free included (RP 5.5) | to a person |
| invoice_ref | reference present and the invoice shows this batch to this stockist (RP 5.3, 5.4) | to a person |
| batch | exists; product and expiry month match; made before Oct 2023 unverifiable; a corrected batch number is flagged | to a person |
| value | value = quantity x PTS (RP 5.7) | to a person |

`decide()`: any reject-failure rejects; any other failure or flag goes to a person; else clean.
Every threshold lives in `agent/policy.py` with its clause.

## Alternatives considered
- **Expiry window only for "Expired" claims.** First version; the back-test showed the verified
  figure applies it to every claim type (worth Rs 4.3 L).
- **Duplicate against any other claim.** First version; it flagged the first claim of a pair too.
  Now only earlier claims count.

## Consequences
- The live back-test (`python -m agent.backtest`) runs these same functions over the register.
- A policy change is one edit in `policy.py`; the clause shows on every result.
- The 60% shelf-life floor and transfer approvals still need the client to confirm the clause.
