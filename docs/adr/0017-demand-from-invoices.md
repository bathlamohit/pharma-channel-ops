# 0017. Demand from invoices, not the SAP stock report; allocation on current shares

- Status: Accepted (22 Nov 2026). Supersedes the cover, unfilled-order and donor definitions in 0009, and the
  bands and moves in 0015. The share change awaits the client's approval.
- Date: 2026-11-22
- Plan: `docs/allocation-demand-plan.md`, steps 1–6. Client note: `docs/client-note-demand-and-allocation.md`.

## Context
Every cover figure used `avg_monthly_outward_packs` from the CFA stock report.
- **The field is wrong.** At every snapshot from Sep 2025 to Sep 2026 it was 44–48% of what the C&Fs
  actually invoiced. The client confirmed it has been unreliable since the ERP extract was set up, and
  told us not to use it.
- **What the client gave us, in two rounds of answers:**
  - the definitions of outward, orders, scheme sales and normal demand
  - the agreement's target: top up to 2 months of allocated volume, at most 1.2 months per shipment
    (CF Sch 2 §2.2)
  - the return rules
  - that the CDC can supply
  - that FY25 shares stand in for the allocation split, as no forecast or shares are available

## Decision
**1. One source of demand: `agent/demand.py`, from invoices.**
- Each order line takes the highest `ordered_qty` once. That covers the 45 irregular split lines,
  which are listed in the client note.
- Dispatched = invoiced + free.
- Scheme sales are identified by **scheme code**, not by date.
- Unmet need on non-scheme lines is counted once per stockist, SKU and month.
- Normal month = the last 3 months with no scheme lines.
- Real need = normal month + unmet need.

**2. Allocation (`agent/allocation.py`).** Allocated volume = national normal demand × share.
- **Statuses:** out of stock / below target / on target / excess.
- **Top-up** = min(2 × allocated − stock, 1.2 × allocated), shown with "assumes the CDC can supply".
- **Returns** only for batches that keep 60% shelf life and 60 days after 14 days in transit, and only
  at ≥ Rs 5 lakh per SKU.
- **Moves between C&Fs are retired:** top-ups come from the CDC, and returns go back to it.

**3. Shares.**
- **Current** (each C&F's share of real need) is shown by default as the recommendation, labelled
  "awaiting approval".
- **FY25** (the client's instruction) is one click away.
- The reason: on FY25 shares Lucknow is about 30% short every month and Kolkata about 30% over. The
  allocation backtest (step 5) found current shares leave Rs 2.47 cr of normal orders unfilled over
  six months, against Rs 3.53 cr on FY25.

**4. Expiry forecast (`agent/stock.py`).**
- It sells each C&F's normal demand. At-risk returns follow the same return rules.
- A separate **"Not moving" watch list** (sold under 5% since the previous snapshot) sits beside it,
  because the forecast alone catches only 20% of leftovers.

**5. Dispatches under 60% shelf life (`agent/short_dated.py`).**
- Every line in the last four quarters is flagged (1,171 lines, Rs 6.262 cr), with likely reasons and
  consent steps. None is blocked.

**6. Restatement.**
- The screens show the new figures.
- `GET /api/allocation/restatement` and the Allocation "What changed" view show **old, new and
  reason side by side**, as the client asked. The digest carries a notice.
- The tests keep the old verified figures pinned in the "old" column, so the restatement itself is
  checked.

## Old and new (30 Sep 2026)

| Figure | Old | New (current shares) | New (FY25 shares) |
|---|---|---|---|
| Months of stock, national | 1.74 | 0.85 | 0.85 |
| Kolkata | 3.31 | 1.84 | 1.37 |
| Lucknow | 0.32 | 0.14 | 0.18 |
| Orders not filled, 6 months | Rs 18.30 cr | Rs 4.01 cr, plus Rs 14.29 cr of cut scheme orders (4.01 + 14.29 = 18.30) | same |
| Kolkata above 3 months | Rs 1.66 cr | Replaced by "above 2 months": 14 products, Rs 0.92 cr returnable | |
| Coverable from other C&Fs' spare | 49% | Retired (top-ups come from the CDC) | |

**Unchanged** (they never used the field): the claims figures, the claim back-test, expiry value under
60% (Rs 1.18 cr at Kolkata), the batch-order alert, the scheme report and free goods over the cap.

## Alternatives considered
- **Keep the report field with a correction factor (×2).** Rejected: the client said don't use it,
  and the factor varies by C&F and SKU.
- **FY25 shares only.** Rejected as the default: the backtest shows it leaves Lucknow short. It's kept
  one click away until the client decides.
- **Count unmet need on every cut line.** Rejected: re-orders would double-count. In this extract no
  stockist had two cuts for one SKU in one month, so the totals are the same, but the rule is built
  for data where it matters.

## Consequences
- **Headline figures change.** The client gets the note with old, new and reason, and must approve
  the share change.
- **Open items:**
  - share approval, and the 5-point limit per review
  - the 70% "arrived old" cut-off (proposed)
  - a possible mid-month top-up in demand spikes (the backtest misses come in May and August)
- **Every assumption is stated on screen:** CDC supply, FY25 shares, and normal demand standing in for
  the forecast.
