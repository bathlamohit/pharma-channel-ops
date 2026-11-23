# 0015. Allocation as a work screen: refill, too much, moves via the CDC, and schemes

- Status: Superseded in part by 0017 (bands, moves and cover now on demand from invoices; schemes view unchanged)
- Date: 2026-11-21

## Context
The Allocation tab had a "Run" button and two summaries: cover with unfilled orders, and the
scheme report. Demand Planning could see that Lucknow is at 0.32 months and Kolkata at 3.31, but
not which products to refill, where the stock should come from, or how to move it within the
C&F agreement. The NSM and CFO figures sat in one dense sentence. The product owner asked for
the same treatment as Expiry & dispatch (0014).

## Decision
**A plan per CFA and product** (`agent/allocation.py`, plain pandas, no model). It works on the
latest snapshot; months of stock = stock ÷ average monthly outward.

| Status | Band | Action |
|---|---|---|
| stock_out | nothing on hand, still sells | refill to 2 months |
| short | under 1 month | refill to 2 months |
| excess | over 3 months | pause replenishment; return spare via the CDC if a CFA is short |
| idle | stock, no sales | return via the CDC |
| ok | 1 to 3 months | none |

**The bands are not in CO-POL-014.** They are proposed planning norms and are labelled that way
on screen and in `policy.py`:
- 1 month (short) and 2 months (refill target, and what a donor keeps, from the Final Plan)
- 3 months for excess (the verified definition behind Kolkata's Rs 1.66 cr)

**Spare** = billable stock above 2 months. Billable means batches with at least 60% of shelf life
and 60 days left (CO-POL-014 7.1), so a move never sends short-dated stock to a stockist.

**Moves** match spare to need product by product, largest need first. Each move is a CDC return
from the donor plus an allocation to the receiver; CFAs never ship to each other (CF Sch 2 2.5).
Need left after the moves is shown as "from the CDC or the plant", because CDC stock is not in
the extract.

**The screen:**
- National figures: cover 1.74; Rs 18.30 cr unfilled in 6 months, Rs 3.54 cr of it outside
  scheme weeks; 49% coverable from spare.
- **By CFA:** cards with a cover bar against the 1 to 3 month band. For the chosen CFA, Refill,
  Too much and In range lists, each product with why, what to do and steps. Orders not filled,
  by product.
- **Moves between CFAs:** 29 moves, Rs 1.14 cr. Steps at the donor: Return requested → Return
  approved → Received at CDC. Steps at the receiver: Allocation raised → Dispatched from CDC.
- **Schemes (NSM, CFO):**
  - claim rate 4.25% against 0.35%, Rs 4.76 cr extra
  - free goods by quarter against the 3% cap (CO-POL-014 4.4), Rs 3.954 cr over in 7 quarters
  - the approval (4.3) and stock-norm (4.5) clauses
  - "Raised with NSM" and "Raised with CFO"

**Steps** go in the same action log as 0014 (`data/stock_actions.jsonl`). The order check now
also matches the product, so steps for one product never satisfy another.

**Policy clauses corrected from the text:** free-goods cap is CO-POL-014 4.4, the scheme stock norm
is 4.5, and scheme windows are Annexure B.

## Alternatives considered
- **Size moves on value instead of packs.** Rejected: people move packs. Value is shown beside
  each move.
- **Fill every need from spare first.** Rejected: spare is limited to billable stock above 2
  months, so a donor is never left short.

## Consequences
- The allocation and scheme figures reproduce the verified analysis, and tests pin them.
- The Weekly digest still uses the summary views; it is the only tab left on "Run".
- The action log does not persist on Vercel (0010).
