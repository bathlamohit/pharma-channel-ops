# Backtesting and historical validation

Run on 21 Nov 2026 against the pilot's extract (register, sales, batches and CFA stock
snapshots to 30 Sep 2026). Every result below comes from code that was actually run.
- Evidence: `evidence/backtest.json`, `evidence/qa_check.txt`, `evidence/backtest_cli.txt`.
- Tests: `automated_tests/test_08_backtest.py` (TC-BKT-001 to 006).

## What is calculated, and how it was tested

| Feature | Formula / algorithm | How it was validated |
|---|---|---|
| Claims register figures | Pending count and value; days to credit note; Q1 FY27 value | Independent recomputation from raw files |
| Claim rules (8 checks) | CO-POL-014 5.1–5.7; CF Sch 2 2.6 | Back-test over 4,503 historical claims; 19 synthetic boundary claims; all 360 pending claims |
| Months of stock | stock × PTS ÷ monthly outward × PTS, per CFA and national | Independent recomputation |
| Expiry radar | (expiry − snapshot) ÷ (shelf life × 30.44 days) < 60% | Independent recomputation |
| Batch-order check | Share of packs shipped while the same CFA shipped an older batch in the next 90 days, rolling 3 months | Independent recomputation |
| Unfilled orders, moves | (ordered − invoiced − free, ≥ 0) × PTS, once per invoice and SKU; scheme weeks 22nd to month end | Independent recomputation; consistency checks |
| Scheme figures | Near-expiry + expired claims ÷ sales, scheme vs other SKUs; free goods vs 3% cap per quarter | Independent recomputation |
| **Stock forecast** ("will not sell in time") | Sell monthly outward, oldest sellable batch first, until each batch's 60% date | **Time-ordered backtest** (section 3) |
| Credit amounts | quantity × PTS, to the paisa | Decimal half-up comparison |
| Due dates | +10 working days to verify; +30 days to credit note | Boundary dates |

## 1. Independent recomputation: 30 of 30 match

`scripts/qa_check.py` reads `data/raw/` with its own cleaning and imports nothing from `agent/`
to compute:
- 3 date formats
- code spellings (CFE01 vs CF-E01, PFL-1001)
- exact duplicates
- blank values priced at quantity × PTS
- blank snapshot expiries taken from the batch master

It then compares each figure with what the API serves and with the verified analysis.

| Figure | Independent | App | Verified | Result |
|---|---|---|---|---|
| Pending claims / value | 360 / Rs 95.95 L | 360 / Rs 95.9 L | 360 / Rs 95.9 L | PASS |
| Pending over 30 days | 129 | 129 | n/a | PASS |
| Days to credit note, mean / median | 45.18 / 42 | 45 / 42 | 45 / 42 | PASS |
| Q1 FY27 claims (not rejected) | Rs 1.414 cr | (unit test) | Rs 1.415 cr | PASS (±0.002) |
| Months of stock: Kolkata, Lucknow, national | 3.310, 0.321, 1.738 | 3.31, 0.32, 1.74 | 3.31, 0.32, 1.74 | PASS |
| Gurugram, Chennai, Bhiwandi, Hyderabad | 1.254, 1.804, 1.854, 2.233 | 1.25, 1.8, 1.85, 2.23 | n/a | PASS |
| Kolkata above 3 months | Rs 1.663 cr | Rs 1.663 cr | Rs 1.66 cr | PASS |
| Lucknow products at zero / all stock-outs that sell | 23 / 50 | 23 / 50 | 23 / n/a | PASS |
| Kolkata under 60% shelf life | Rs 1.179 cr | Rs 1.179 cr | Rs 1.18 cr | PASS |
| Batches under 60% / under 60 days | 65 / 0 | 65 / 0 | n/a | PASS |
| Short-dated billing, last 4 quarters | Rs 6.262 cr | Rs 6.262 cr | about Rs 6.3 cr | PASS |
| Batch order out of sequence, Kolkata FY27 Q2 | 70.70% | 70.70% | 70.7% | PASS |
| Unfilled H1 / outside scheme weeks | Rs 18.299 / 3.538 cr | same | Rs 18.30 / 3.54 cr | PASS |
| Claim rate scheme / other | 4.249% / 0.348% | 4.25% / 0.35% | 4.25% / 0.35% | PASS |
| Extra scheme claims | Rs 4.761 cr | Rs 4.761 cr | Rs 4.76 cr | PASS |
| Free goods over the 3% cap / quarters | Rs 3.954 cr / 7 | same | Rs 3.954 cr | PASS |
| Latest quarter free goods | 2.817% | 2.82% | 2.82% | PASS |

**Rounding.** The app rounds for display: months to 2 decimals, days to whole numbers, lakh to 1
decimal. All differences are within that rounding.

**Reproducibility.** The same inputs give the same outputs: the run was repeated and the claim
back-test compared row for row.

## 2. Claim rules over the historical register (TC-BKT-002)

The live rule functions (duplicate and window, the hard rules that reject) are run over every
historical claim.

| | Claims | Value |
|---|---|---|
| Credited in the last 4 quarters that break a hard rule (references as written) | 181 | Rs 21.89 L |
| Same, with invoice references normalised (what the app does) | 185 | Rs 22.12 L |
| Pending now that break a hard rule (as written / normalised) | 38 / 41 | Rs 7.25 L / Rs 7.37 L |
| Credited twice over 30 months | 61 | Rs 11.20 L |

- **Matches the verified analysis exactly.** Two runs give identical row-by-row results.
- **Cross-check through the API.** Of the 360 pending claims checked through the API (a different
  code path, all 8 checks), exactly 41 are recommended for rejection, matching the 41 above.

**Boundary dates** (synthetic claims, TC-CLM-1xx). Every result matches the policy:
- Expired claim 90 days after expiry: accepted. 91 days: rejected.
- Near-expiry claim 90 days before expiry: accepted. 91 days: to a person (decision D2).
- Breakage or short supply 7 days after invoice: accepted. 8 days: rejected.
- Quantity equal to supply: accepted. One more: part credit for the supplied quantity.

## 3. Time-ordered backtest of the stock forecast (TC-BKT-003, 004)

The Expiry & dispatch screen predicts which batches "will not sell in time".

**Method:**
- Forecast from a past snapshot T, using only the snapshot at T: the app's own
  `stock.batches(as_of=T)`.
- Compare with the snapshots that followed.
- Four forecast start dates (31 Mar, 30 Apr, 31 May, 30 Jun 2026), horizons of 1 to 3 months:
  12 combinations in all.
- No later data enters the forecast. The batch master's expiry dates are fixed facts.

**Error measure:** WAPE, the sum of absolute errors in remaining packs per batch, divided by the
actual total. Lower is better. Two baselines:
- **"Nothing sells":** every batch keeps its stock.
- **"Proportional":** the CFA's outward split across its batches in proportion to stock.

| Start | Horizon | Batches | Model WAPE | Nothing sells | Proportional | Model bias |
|---|---|---|---|---|---|---|
| 31 Mar | 1 m | 267 | **0.434** | 0.602 | 0.445 | −16% |
| 31 Mar | 2 m | 267 | 0.959 | 2.693 | 0.954 | −6% |
| 31 Mar | 3 m | 267 | 0.984 | 6.930 | 0.904 | −23% |
| 30 Apr | 1 m | 284 | **0.751** | 1.025 | 0.789 | −17% |
| 30 Apr | 2 m | 284 | 1.131 | 3.537 | 1.059 | +21% |
| 30 Apr | 3 m | 284 | 1.035 | 5.394 | 0.874 | +6% |
| 31 May | 1 m | 310 | 0.928 | 1.418 | 0.926 | +20% |
| 31 May | 2 m | 310 | 1.021 | 3.750 | 0.837 | +1% |
| 31 May | 3 m | 310 | 0.979 | 6.606 | 0.658 | −11% |
| 30 Jun | 1 m | 293 | 0.535 | 0.787 | 0.529 | −1% |
| 30 Jun | 2 m | 293 | 1.036 | 2.571 | 0.919 | +10% |
| 30 Jun | 3 m | 293 | 1.039 | 5.527 | 0.831 | −2% |

**"Will not sell in time" flag:** batches whose 60% date falls inside the data. Was the batch still
in stock at its 60% date?

| Start | Batches evaluable | Flagged and still there | Flagged, sold | Missed | Precision | Recall |
|---|---|---|---|---|---|---|
| 31 Mar | 160 | 21 | 28 | 28 | 0.43 | 0.43 |
| 30 Apr | 145 | 26 | 26 | 21 | 0.50 | 0.55 |
| 31 May | 108 | 23 | 8 | 17 | 0.74 | 0.58 |
| 30 Jun | 76 | 27 | 16 | 15 | 0.63 | 0.64 |

**By CFA**, all start dates pooled:

| CFA | Precision | Recall |
|---|---|---|
| Kolkata | 0.88 | 0.43 |
| Gurugram | 0.26 | 0.88 |
| Lucknow | 0.20 | 1.00 |
| Chennai | 0.48 | 0.85 |
| Hyderabad | 0.55 | 0.92 |
| Bhiwandi | 0.31 | 0.82 |

**What this shows:**
- **The method has real signal.** It beats "nothing sells" at all 12 start dates and horizons,
  and bias stays between −23% and +21%.
- **One month ahead, it's as good as the simple baseline.** Its error is within ±0.04 of the
  proportional baseline at every start date.
- **At 2–3 months it's worse than the simple baseline** (e.g. 0.979 against 0.658). Remaining stock
  per batch is hard to predict at 2–3 months either way, with errors near 100%.
- **Kolkata under-flags.** When it flags, it's right 88% of the time, but it misses more than half.
  This fits Kolkata's out-of-order picking (71% of packs): the model assumes oldest-first, so it
  expects older batches to sell when they don't.
- **The other CFAs over-flag.** Older batches there sell faster than average monthly outward
  suggests.

**Limitations:**
- Outward is the snapshot's average, not real daily sales.
- Receipts of the same batch after T would add stock that the forecast can't know about.
- Only batches whose 60% date falls by 30 Sep 2026 can be scored for the flag.

**Recommendation** (open item O-05; a business decision, not a code fix):
- Show the flag as "likely".
- Use each batch's recent sell-through, not only average outward, and allow for out-of-order
  picking where the batch-order check alerts.
- Re-run this backtest after any change. It's automated.

## 3b. After plan step 3 (22 Nov 2026): the forecast on normal demand

The client confirmed the SAP outward field is unreliable, so the forecast now sells each C&F's **normal
demand from invoices**. The same backtest was re-run for both sources, with the same start dates and
horizons, and no later data.

Average forecast error (WAPE) over the 4 start dates:

| Horizon | New (normal demand) | Old (SAP field) | Proportional baseline (new / old) | "Nothing sells" |
|---|---|---|---|---|
| 1 month | 0.759 | **0.662** | 0.742 / 0.672 | 0.958 |
| 2 months | **0.925** | 1.037 | 0.938 / 0.942 | 3.138 |
| 3 months | **0.988** | 1.009 | 1.000 / 0.817 | 6.114 |

| "Will not sell in time" flag | Flags | Precision | Recall |
|---|---|---|---|
| New (normal demand) | 43 | **0.84** | 0.20 |
| Old (SAP field) | 175 | 0.55 | **0.55** |

**What changes:**
- **Forecast error:** the new forecast matches or beats the proportional baseline at every horizon.
  The old one was worse at 2–3 months.
- **Flags:** a flag is now right 84% of the time, but it catches only 1 leftover batch in 5. The old
  field caught more by accident: it halved demand, so it flagged far more.
- **Today's to-do list:** "will not sell in time" drops from 40 batches (Rs 2.20 cr) to 2 (Rs 6.7 L).
  Both now say "push in dispatch", because neither passes the client's return rules.

**Two other approaches were tested, and neither fixes recall:**

| Approach | Precision | Recall |
|---|---|---|
| Model each C&F's out-of-order picking (measured 3 months earlier, to avoid look-ahead) | 0.89 | 0.14 |
| Flag batches whose stock hasn't fallen since the previous snapshot | 0.50 | 0.34 |
| That signal combined with the forecast | 0.55 | 0.43 |

**Conclusion:** monthly snapshots don't hold enough to forecast reliably which batches will be left
over. The new forecast is the honest one: few flags, mostly right.

**Added (22 Nov, approved):** a separate, clearly labelled **"Not moving" watch list** beside the
forecast (TC-BKT-007, re-run on the app's own code):

| Signal | Flags | Precision | Recall |
|---|---|---|---|
| Forecast only | 43 | 0.84 | 0.20 |
| Not moving only | 123 | 0.50 | 0.34 |
| Either | 141 | 0.55 | 0.43 |

**Today:** 61 batches (Rs 3.77 cr) are not moving.
- **45** are the batch to pick first. In the backtest, 46% of these were still there at the 60% date.
- **16** sit behind an older batch. In the backtest, 71% of these were still there.

The wording and the suggested check differ for the two cases.

## 5. Allocation backtest (plan step 5, TC-BKT-008)

**Question:** would the plan's monthly top-ups have prevented the orders that went unfilled?

**Method:** a chronological replay, using the app's own code (`agent/allocation_backtest.py`).
1. At each month-end T from March to August 2026, plan top-ups using **data up to T only**.
2. Deliver them at the start of the next month. The CDC is assumed able to supply, as the client said.
3. Serve that month's **actual normal orders:** non-scheme dispatches plus orders cut for lack of
   stock, counted once.

The test checks that no plan uses a normal month after T.

**Six months, Rs 85.81 cr of normal orders:**

| Plan | Orders left unfilled | Fill rate | Top-up sent | Lucknow unfilled |
|---|---|---|---|---|
| What actually happened (reference) | Rs 4.01 cr | 95.3% | n/a | n/a |
| **Current shares (recommended)** | **Rs 2.47 cr** | **97.1%** | Rs 76.25 cr | **Rs 1.10 cr** |
| FY25 shares (client's instruction) | Rs 3.53 cr | 95.9% | Rs 77.57 cr | Rs 2.15 cr |
| Old method (SAP outward field, refill to 2 months) | Rs 13.94 cr | 83.8% | Rs 29.17 cr | Rs 7.24 cr |

**By month (Rs lakh unfilled):**

| Month | Normal orders | Actual | Current | FY25 | Old method |
|---|---|---|---|---|---|
| Apr 2026 | Rs 11.87 cr | 48.5 | 0.0 | 1.6 | 147.3 |
| May 2026 | Rs 16.77 cr | 25.4 | 64.2 | 98.6 | 449.0 |
| Jun 2026 | Rs 12.81 cr | 48.0 | 0.0 | 4.7 | 61.2 |
| Jul 2026 | Rs 12.77 cr | 130.0 | 0.5 | 8.8 | 141.4 |
| Aug 2026 | Rs 18.06 cr | 35.8 | 182.2 | 226.8 | 507.2 |
| Sep 2026 | Rs 13.52 cr | 113.5 | 0.2 | 12.7 | 87.6 |

**Returns:** under the current plan there were 16 returns (Rs 1.23 cr) over the six months. **None** left
the returning C&F short the next month.

**What this shows:**
- **Current shares leave 30% less unfilled than FY25,** with almost the same top-up, and roughly halve
  Lucknow's shortfall. This is the evidence for the share change the client is being asked to approve.
- **The old method would have been much worse than what actually happened** (Rs 13.94 cr against
  Rs 4.01 cr), because the SAP field understates demand by about half.
- **The plan's misses are in May and August,** when normal orders jumped 30–40% above the usual month.
  One top-up a month, capped at 1.2 months by the agreement, cannot absorb a jump like that. A
  mid-month top-up when orders run ahead of plan would close most of the gap. This is a suggestion for
  the client: the agreement says one shipment a month.

**Limits:**
- The replay assumes one delivery a month, but reality also had deliveries within the month. That is why
  "what actually happened" is a reference, not a like-for-like baseline. Comparing the plans with each
  other is fair.
- Batches and shelf life are ignored.
- Scheme orders are left out (the client: not lasting demand).
- CDC stock is assumed to be enough.

## 4. Money and dates (TC-BKT-005, 006)

- **Credits are exact to the paisa.** Every PTS in the SKU master has at most 2 decimals, so
  quantity × PTS is exact. For 120 pending claims, every credit or part credit equals
  `Decimal(qty) × Decimal(PTS)` rounded half-up to 2 decimals: no float noise, never negative.
- **Due dates.** 10 working days to verify, checked across weekends and the year end:
  - Tue 20 Oct → 3 Nov
  - Fri 23 Oct → 6 Nov
  - Sat 24 Oct → 6 Nov
  - 31 Dec → 14 Jan
- **Time zones.**
  - Fixed: the new-claim form defaulted to the UTC date, a day behind in India before 05:30 (D-07).
  - Open: the API's own default "today" uses the server's date, which is UTC on Vercel (O-07).
  - Note: the "already decided on …" message shows the UTC date.
- **Missing data.**
  - Blank claim values are priced at quantity × PTS.
  - Blank snapshot expiries on stock-out rows stay blank.
  - Rows with zero outward show "no sales" or n/a, never divide by zero.
  - Cited rows that don't exist are reported as missing, not invented (TC-VAL-071).
