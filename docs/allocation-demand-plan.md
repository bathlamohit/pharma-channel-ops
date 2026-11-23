# Plan: correct demand and allocation using the client's answers

- Status: **all six steps built (22 Nov 2026).** ADR 0017; client note `docs/client-note-demand-and-allocation.md` (`python scripts/client_note.py`). Awaiting the client's share approval.
- Version 2, 22 Nov 2026. Version 1 was 21 Nov.
- Sources:
  - the client's answers to two rounds of questions (13 + 5)
  - the C&F agreement (Sch 2 §2.2–2.5)
  - CO-POL-014 (§4.2, §7.1, Annexure B)

## 1. What the client told us

| Topic | Client's answer | Rule we will apply |
|---|---|---|
| Report "average monthly outward" | Unreliable since the ERP extract. **Don't use it.** | Not used anywhere. All demand comes from the sales extract, **stated in the client note**. |
| What outward is | CFA dispatches to stockists, SKU-master packs, **free goods included**, the month plus the two before ÷ 3 | "Dispatched a month", calculated from invoices |
| `ordered_qty` | The order line as entered, before cuts for stock. On split lines it's on the first row only. A credit block holds the whole order, it doesn't cut it. | A cut line is a real stock shortfall |
| Re-orders | Cancelled balance is re-ordered (Sch 2 §2.4) | Unmet need counted once |
| Odd split lines (45) | Apply one stated rule; list them in the note | **Highest `ordered_qty` once per order line.** (Checked: gives the same result as today's rule on all 45.) |
| Scheme weeks | Use the **scheme code**, not a date window | Scheme lines = `scheme_code` present |
| Quarter-end orders | Remove only the part above a normal month; take the normal month from periods with no scheme | Scheme lines count only up to the normal month |
| Cover is judged against | Demand outside scheme weeks | Months of stock = stock ÷ normal monthly demand |
| National forecast, shares | **Not available.** Use **normal demand (non-scheme dispatches)** as the forecast stand-in, and the **FY25 shares implied by dispatches** as the split | Allocated volume = national normal demand × FY25 share, per product |
| Target | Top up to **2 months** of allocated volume; **one shipment ≤ 1.2 months** (Sch 2 §2.2) | Top-up = min(2 × allocated − stock, 1.2 × allocated) |
| Excess | Anything above 2 months | Return candidate, if the return rules below are met |
| Return rules | Only batches that **still have 60% shelf life after 10–14 days in transit**, and **not less than ₹5 lakh per SKU** | Batch must keep ≥ 60% shelf life and ≥ 60 days at +14 days; a return is listed only if its value is ≥ ₹5 L per SKU |
| CDC and plant stock | **Not available.** Assume the CDC can supply, since national stock is sufficient. | Stated on every top-up: "assumes the CDC can supply (client, 22 Nov)" |
| Dispatches under 60% shelf life | No approved exceptions: flag every one. Don't block; it goes out only with the stockist's agreement. Find where and why. | Flagged list, consent step, where-and-why breakdown |
| Restating figures | **Yes:** show old figure, new figure and reason side by side | Restatement table on screen and in the client note |

## 2. What the data showed

- **Report column vs real dispatches.** The report column is 44–48% of real dispatches at every
  snapshot from Sep 2025 to Sep 2026. By product it moves with dispatches (correlation 0.95).
- **Split order lines.** 2,784 repeat the quantity on every row, 2,959 have it on the first row
  only, and 45 follow neither pattern.
- **Scheme lines.**
  - All 12,610 scheme lines fall in quarter-end weeks.
  - 8,211 normal lines also fall in those weeks, and today's date rule wrongly drops them.
  - The scheme code fixes this.
- **Shares have drifted since FY25,** in the direction of the imbalance:

| Warehouse | FY25 share of national dispatches (value) | Apr–Sep 2026 share | Change |
|---|---|---|---|
| Kolkata | 18.5% | 15.1% | **−3.4 pts** |
| Lucknow | 15.3% | 18.4% | **+3.1 pts** |
| Gurugram | 17.1% | 18.6% | +1.5 |
| Chennai | 18.4% | 17.4% | −1.0 |
| Hyderabad | 15.5% | 15.0% | −0.5 |
| Bhiwandi | 15.2% | 15.5% | +0.3 |

## 3. What changes: old and new figures side by side

This is an estimate from analysis; final figures come from the build, step 1. Months of stock at
30 Sep 2026:

| Warehouse | Old (report column) | New: own normal demand | **New: FY25 allocated volume (client's rule)** | Reason |
|---|---|---|---|---|
| Kolkata | 3.31 | 1.86 | **1.43** | Report column ~half of real dispatches; FY25 share is higher than Kolkata's sales now |
| Lucknow | 0.32 | 0.16 | **0.19** | Same; FY25 share is lower than Lucknow's sales now |
| Gurugram | 1.25 | 0.64 | **0.69** | Report column |
| Chennai | 1.80 | 0.92 | **0.88** | Report column |
| Hyderabad | 2.23 | 0.97 | **0.97** | Report column |
| Bhiwandi | 1.85 | 1.07 | **1.07** | Report column |
| **National** | **1.74** | 0.89 | **0.89** | Report column |

| Other headline figure | Old | New (estimate) | Reason |
|---|---|---|---|
| Kolkata stock above 3 months | Rs 1.66 cr | Replaced by "above 2 months of allocated volume": **8 products at Kolkata** | Report column; client target is 2 months |
| Return candidates | 29 moves, Rs 1.14 cr | **6 returns, Rs 0.72 cr, all Kolkata** (≥ 60% shelf life after 14 days, ≥ Rs 5 L per SKU) | New return rules; less spare once demand is corrected |
| Unfilled orders coverable from spare | 49% | To be recalculated | Spare and scheme weeks redefined |
| Unfilled orders H1, outside scheme weeks | Rs 18.30 cr, Rs 3.54 cr | To be recalculated | Scheme lines by code, unmet need counted once |

Figures that **don't** change: claims, the back-test, expiry value under 60% (Rs 1.18 cr at Kolkata),
batch-order alert (71%), scheme claim rate and free goods over the cap. None of them use the
report column.

**What this means:**
- **The network is short.** It holds 0.89 months against a 2-month target.
- **The monthly top-up from the CDC is the main output.** Most of the gap is filled there, assumed
  available per the client.
- **Returns become a short list.** Six Kolkata products.

### Built figures (step 1, `python -m agent.demand`)

Normal months at 30 Sep 2026: **May, Jul, Aug 2026**. Sections 2–3 used Jul–Aug only, so the
numbers there differ a little.

| Warehouse | Old | New on FY25 shares | New on current shares | Share FY25 → current |
|---|---|---|---|---|
| Kolkata | 3.31 | 1.37 | 1.84 | 18.7% → 13.9% (−4.7 pts) |
| Gurugram | 1.25 | 0.66 | 0.61 | 16.9% → 18.5% (+1.6) |
| Lucknow | 0.32 | 0.18 | 0.14 | 15.5% → 20.8% (+5.3) |
| Chennai | 1.80 | 0.84 | 0.88 | 18.2% → 17.3% (−0.8) |
| Hyderabad | 2.23 | 0.92 | 0.97 | 15.5% → 14.8% (−0.7) |
| Bhiwandi | 1.85 | 1.02 | 1.07 | 15.3% → 14.6% (−0.7) |
| **National** | **1.74** | **0.85** | **0.85** | |

- **Returns to the CDC:** Rs 0.62 cr on FY25 shares; **Rs 0.92 cr on current shares**. All six
  products are at Kolkata, Rs 10–22 L each.
- **Lucknow on FY25 shares:** about Rs 0.93 cr a month short.
- **Months of stock and shares:** a bigger share means a bigger target. That's why Lucknow shows
  *fewer* months of stock on current shares (0.14) than on FY25 (0.18): it is shorter against what
  it should hold.
- **Unmet need counted once:** across all 1,085 lines cut for lack of stock, no stockist had two
  cuts for one product in one month. The rule is built and tested, but this extract never
  triggers it.

## 4. Definitions to build

All quantities are in SKU-master packs, per warehouse and product, from the sales extract.

1. **Dispatched a month** = invoiced + free packs, all lines, average of the month and the two
   before. Shown for reference.
2. **Normal demand** (client: "non-scheme dispatches"):
   - average monthly non-scheme dispatches over the last 3 months with no scheme lines
   - Apr, May, Jul and Aug 2026 qualify; quarter-end months don't
   - in a scheme month, scheme lines count only up to the normal month
3. **Unmet need** = ordered − invoiced − free, if above 0, counted once per stockist and product per
   month (the last order of the month).
   - It is reported in "orders not filled" and used to rank top-ups.
   - It is **not added** to normal demand, which follows the client's wording.
4. **Allocated volume** = national normal demand for the product × the warehouse's FY25 dispatch
   share of that product.
5. **Months of stock** = stock ÷ allocated volume: per product in packs, per warehouse in value at
   PTS. Own normal demand is shown beside it.
6. **Statuses:**

   | Status | When | Action |
   |---|---|---|
   | Out of stock | 0 on hand | Urgent top-up |
   | Below target | Under 2 months | Top-up at the monthly replenishment |
   | On target | 2 months | None |
   | Excess | Over 2 months | Return candidate |

   "Under 1 month" stays only as a priority marker.
7. **Top-up** = min(2 × allocated − stock, 1.2 × allocated), with the note "assumes the CDC can supply".
8. **Return** = billable stock above 2 months of allocated volume, made up only of batches that
   still have **≥ 60% shelf life and ≥ 60 days at +14 days**. Listed only if worth **≥ ₹5 L per SKU**.
   Via the CDC (Sch 2 §2.5).
9. **Odd order lines:** highest `ordered_qty` once per order line. The 45 lines are listed in the
   client note.

## 5. What changes in the pilot

| Part | Change |
|---|---|
| New `agent/demand.py` | Dispatches, normal demand, unmet need, FY25 shares, allocated volume. The only source of demand. |
| `agent/policy.py` | Target 2 months, shipment cap 1.2 months (CF Sch 2 §2.2); excess above 2 months; return rules (+14 days transit, ₹5 L per SKU; client 22 Nov); scheme by code (Annexure B); old 1- and 3-month bands removed. |
| Allocation screen | Months of stock on allocated volume, own demand beside it; new statuses; **Monthly top-up from the CDC** view per warehouse; returns list under the new rules; orders not filled (scheme by code, unmet once); **share drift** shown per warehouse. |
| Expiry & dispatch | The "will not sell in time" forecast uses normal demand. New **dispatches under 60% shelf life** view: each flagged, a "stockist agreed" step, where-and-why breakdown. |
| Weekly digest | New figures, plus a restatement panel (old, new, reason) until the client has seen it. |
| Wording | "Allocated volume: national normal demand × FY25 share (forecast and shares not available)". "Assumes the CDC can supply." |
| Tests | Pinned old figures (3.31, 0.32, 1.74, Rs 1.66 cr, 49%) replaced by the new ones, with the old ones kept in the restatement record; the QA suite and `scripts/qa_check.py` updated with an independent calculation of the new definitions. |
| Decision record | ADR 0017 "Demand from invoices; allocation on FY25 shares", replacing the cover parts of 0009 and 0015. |
| Client note | Report field not used, and why; definitions; old vs new table; the CDC assumption; the 45 lines; share drift. |

## 6. Suggested improvements

1. **Review the shares (recommended): Lucknow stays about 30% short on FY25 shares.**

   | Per month (PTS) | Lucknow | Gurugram | Kolkata |
   |---|---|---|---|
   | Allocated on FY25 shares | Rs 2.26 cr | Rs 2.45 cr | Rs 2.74 cr |
   | Real need: dispatched now + orders cut for lack of stock (Jul–Aug 2026, non-scheme) | Rs 3.23 cr | Rs 2.91 cr | Rs 2.10 cr |
   | Gap | **Rs 0.97 cr short (30%)** | Rs 0.45 cr short (16%) | **Rs 0.63 cr over (30%)** |

   - **Shares, FY25 against real need now:**
     - Lucknow 15.3% → 21.0%; Gurugram 17.1% → 18.8%; Chennai 18.4% → 17.3%
     - Hyderabad 15.5% → 14.9%; Bhiwandi 15.2% → 14.4%; Kolkata 18.5% → 13.7%
   - **The effect:** following FY25 shares keeps Lucknow out of stock and Kolkata overstocked.
     Kolkata's over-allocation would cover most of Lucknow's gap, so the national total barely moves.

   Options for the client:
   - **(a) Update shares now (recommended).** Move to current shares based on real need, through
     the Regional Distribution Manager's mid-year change (Sch 2 §2.2).
   - **(b) Interim floor.** FY25 shares, but no warehouse is topped up below its own real need. The
     CDC is assumed able to supply. This fixes Lucknow at once, but Kolkata keeps receiving its
     FY25 amount.
   - **(c) Keep FY25 as instructed** and show each warehouse's monthly gap. Lucknow stays short.

   **Our recommendation to the client (agreed 22 Nov): (a), update the shares now.**

   How the new shares are worked out:
   - **Share of a product at a warehouse** = that warehouse's real need ÷ national real need for the
     product. Real need = non-scheme dispatches + orders cut for lack of stock (counted once).
   - **Period:** the last 3 months with no scheme lines. The shares add to 100% for each product.
   - **When it changes:** the share is reviewed each quarter after the scheme month, and a change
     goes through the Regional Distribution Manager (Sch 2 §2.2).
   - **Steady limit (proposed):** no warehouse's share of a product moves more than 5 points in one
     review. Lucknow and Kolkata would take two reviews to reach their full new shares unless the
     client lifts the limit for this first change.
   - **Kolkata while it's over target:** it keeps getting allocated volume on the new share, but its
     top-up is zero until stock falls back under 2 months. Its extra stock is used up, not sent on
     top of.

   In the pilot, until the client approves:
   - Allocation shows months of stock and top-ups **on the new shares**, with FY25 beside them for
     reference.
   - Each warehouse shows its "share change requested" status.
   - The client note asks for approval of the new shares.
2. **Backtest allocation.** Replay past months: how many unfilled orders would the top-ups and
   returns have prevented?
3. **Batch-aware top-ups and returns.** Send batches that will sell at the receiving warehouse
   before they drop under 60%.
4. **Track stock in transit.** Recorded returns and top-ups reduce spare and need until the next
   extract.
5. **Scheme pre-build** within the 1.2-month cap.
6. **Re-run the expiry forecast backtest** on normal demand.
7. **Short-dated "where and why"**, combined with the batch-order check.

## 7. Open questions

None blocking the build. We will ask the client to approve **updating the shares now** (section 6,
item 1), and two details with it:
- the 5-point limit per review: keep it, or lift it for this first change
- quarterly review of shares from here on

On FY25 shares Lucknow stays about 30% (Rs 0.97 cr a month) short.

## 8. Order of work

| Step | What | Done when |
|---|---|---|
| 1 ✓ | `agent/demand.py` per section 4 | **Done.** 13 tests: normal month, unmet need, FY25 shares checked against a row-by-row calculation; top-up and return rules; 45 odd lines; restatement table. Run `python -m agent.demand` for the tables. |
| 2 ✓ | Allocation: statuses, top-up with 1.2 cap, returns rules, share drift, monthly top-up view | **Done 22 Nov.** Screen on current shares with an FY25 switch; views: By C&F, Top-up from CDC, Returns to CDC, Shares (with "Share change requested/approved" steps), What changed (old / new / reason), Schemes. Digest updated. Moves between C&Fs retired (top-ups come from the CDC). Unit 202, QA suite 208 + 3 known gaps, figures 30/30, consistency 141/141. |
| 3 ✓ | Expiry forecast on normal demand; re-run its backtest | **Done 22 Nov.** Forecast error now matches or beats the proportional baseline at every horizon. Flags: 43 at precision 0.84 / recall 0.20 (old field: 175 at 0.55 / 0.55). Today's "will not sell in time" list: 40 batches → 2. At-risk returns follow the client's rules (≥ Rs 5 L, 60% after 14 days). See Backtesting_Report.md, section 3b. **Plus** a "Not moving" watch list (sold under 5% since the last snapshot; 61 batches, Rs 3.77 cr today); with the forecast it catches 43% of leftovers. |
| 4 ✓ | Dispatches under 60% shelf life: flags, consent step, where and why | **Done 22 Nov.** 1,171 lines, Rs 6.262 cr (matches); none under 60 days. Why: 75% (Rs 4.69 cr) **arrived old from the CDC** (first seen under 70% shelf life; proposed cut-off); Kolkata's main reason is picking out of order. National "where and why" panel; per-C&F list with reason filters and "Agreed / No agreement" steps; digest line and to-do. |
| 5 ✓ | Allocation backtest | **Done 22 Nov.** Replay Mar–Aug 2026, plan at T with data up to T: unfilled normal orders Rs 2.47 cr on current shares vs Rs 3.53 cr on FY25 (Lucknow Rs 1.10 vs 2.15 cr) vs Rs 13.94 cr on the old method; actual was Rs 4.01 cr. 16 returns, none left a C&F short. Misses come in demand-spike months (May, Aug). See Backtesting_Report.md, section 5. |
| 6 | Restatement: ADR 0017, tests, digest panel, client note | Old / new / reason shown side by side; signed off |
