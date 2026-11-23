# 0008. Tests reproduce the verified figures; an agreed check set guards the claim path

- Status: Accepted
- Date: 2026-11-17 (check set 2026-11-20)

## Context
The plan builds data-first: each day ends on a test that reproduces a verified figure, so a broken
number is caught the day it appears. The claim path also needs agreed answers for real emails.

## Decision
- **Figure tests** assert the numbers the client will see:
  Q1 FY27 claims Rs 1.415 cr; 360 pending, Rs 95.9 L; back-test Rs 21.9 L (181 claims) and
  Rs 7.25 L pending (38); 61 double credits, Rs 11.2 L; cover Kolkata 3.31 / Lucknow 0.32 /
  national 1.74 months; batch-order inversion by month; scheme claim rate 4.25% vs 0.35% and
  Rs 4.76 cr; free goods over the 3% cap Rs 3.954 cr; unfilled Rs 18.30 cr; donor cover 49%,
  about Rs 3.5 cr a year (Rs 2.8-4.8 cr range).
- **The back-test** (`agent/backtest.py`) runs the live rule functions over the register. It
  reproduces the verified figures with invoice references as written, and reports the live
  figures with references normalised (Rs 22.12 L, 41 pending: 4 and 3 more caught).
- **The check set** (`tests/check_set.json`): all 30 mailbox emails and 8 register claims, each
  with the agreed extraction form, each line's route and the exact checks that must not pass,
  and the evidence. Offline, a fake model returns the agreed form and injects an invented number.
- **Live tests** (`pytest -q -m live`) compare the real model's extraction with the agreed forms.
  They are opt-in so a plain `pytest -q` never spends money.
- An agreed answer changes only with the claims desk's sign-off, with the reason in its `why`.

## Consequences
- 94 offline tests in about 7 s; 30 live tests in about 1 minute.
- Where a figure could not be reproduced exactly (the evidence log's donor variant, Rs 1.76 cr;
  the plan's "69% over 30 days"), the code follows the plan's stated definition and the gap is
  written down rather than hidden.
