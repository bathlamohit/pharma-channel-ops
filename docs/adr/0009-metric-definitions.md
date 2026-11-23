# 0009. Metric definitions for the watch views

- Status: Accepted; cover, unfilled-order and donor definitions superseded by 0017 (demand from invoices)
- Date: 2026-11-19

## Context
Several figures could be computed more than one way, and only one way reproduces the verified
analysis. Two traps recur in the extracts: values repeated on every batch row of an order or a
CFA-SKU, and spikes in quarter-end scheme months.

## Decision
| View (owner) | Definition | Verified figure |
|---|---|---|
| Expiry radar (Supply Chain) | stock with remaining shelf life under 60%: (expiry - snapshot) / (shelf life x 30.44 days), at PTS | Kolkata Rs 1.18 cr |
| Batch-order alert (Supply Chain) | share of packs shipped while the same CFA shipped an older batch of the same SKU within the next 90 days; alert above 35% over a rolling 3 months | Kolkata from Mar 2026; FY27Q2 70.7%; no other CFA |
| Short-dated billing (Supply Chain) | invoice lines in the last four quarters with remaining shelf life under 60% at invoice date | about Rs 6.3 cr |
| Cover (Demand Planning) | stock value / monthly outward value at PTS; outward taken once per CFA-SKU; zero outward shown as n/a | Kolkata 3.31, Lucknow 0.32, national 1.74 |
| Unfilled orders | (ordered - invoiced - free, floored at 0) x PTS, once per invoice and SKU; scheme window = 22nd to month-end of Mar, Jun, Sep, Dec | H1 Rs 18.30 cr, Rs 3.54 cr outside windows |
| Donor cover | per product and month, outside-window need against stock above 2 months' cover at the previous month-end in CFAs not short of that product, capped at the need; doubled for a year | 49%, about Rs 3.5 cr a year |
| Scheme report (NSM, CFO) | near-expiry + expired claims / sales, scheme SKUs vs others, last four quarters; free goods (free x line PTS) vs 3% of all sales per quarter | 4.25% vs 0.35%, Rs 4.76 cr; Rs 3.954 cr over cap |
| Claims ageing (Commercial Finance) | pending count and value; credited claims' days from claim to credit note | 360, Rs 95.9 L; mean 45, median 42 days |

## Alternatives considered
- **Cover on packs.** Gives 3.80 / 0.24 / 1.90; the verified analysis uses value.
- **Monthly batch-order alert.** Other CFAs pass 35% in scheme-loading months; a test pins why
  the window is 3 months.

## Consequences
- The plan's "69% of claims over 30 days" is not shown: neither we nor the evidence log
  reproduce it.
- Figures assume the snapshot of 30 Sep 2026 as "now" (`policy.SNAPSHOT_DATE`).
