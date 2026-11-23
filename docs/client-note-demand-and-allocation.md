# Demand and allocation: what changed and why

Project Sankalp pilot · prepared 22 Nov 2026 · stock and sales to 30 Sep 2026

## 1. In short

- **The SAP stock report's 'average monthly outward' was about 44–48% of what the C&Fs invoiced, at every snapshot from Sep 2025 to Sep 2026.** As you confirmed, it has not been reliable since the ERP extract was set up. **We no longer use it.** All demand now comes from the sales extract (primary sales), and every figure below is calculated from invoices.
- **The network is short, not overstocked:** 0.85 months of stock nationally, against the 2-month target (CF Sch 2 §2.2). This month's top-up from the CDC comes to Rs 13.52 cr.
- **We recommend updating the allocation shares now.** On FY25 shares, Lucknow is Rs 93.1 L a month short and Kolkata Rs 63.5 L a month over. In a six-month replay, current shares would have left Rs 2.47 cr of normal orders unfilled, against Rs 3.53 cr on FY25.
- **Most stock billed under 60% shelf life arrived at the C&F already aged.** That covers Rs 4.69 cr of the Rs 6.26 cr billed this way in the last four quarters.

## 2. Old figure, new figure, and why

| Figure | Old | New (current shares) | New (FY25 shares) | Reason |
|---|---|---|---|---|
| Months of stock, Kolkata | 3.31 | 1.84 | 1.37 | Old used the SAP report field (about half of real dispatches); new uses invoices |
| Months of stock, Gurugram | 1.25 | 0.61 | 0.66 | Old used the SAP report field (about half of real dispatches); new uses invoices |
| Months of stock, Lucknow | 0.32 | 0.14 | 0.18 | Old used the SAP report field (about half of real dispatches); new uses invoices |
| Months of stock, Chennai | 1.8 | 0.88 | 0.84 | Old used the SAP report field (about half of real dispatches); new uses invoices |
| Months of stock, Hyderabad | 2.23 | 0.97 | 0.92 | Old used the SAP report field (about half of real dispatches); new uses invoices |
| Months of stock, Bhiwandi | 1.85 | 1.07 | 1.02 | Old used the SAP report field (about half of real dispatches); new uses invoices |
| Months of stock, national | 1.74 | 0.85 | 0.85 | Same; shares do not change the national figure |
| Orders not filled, last 6 months (Rs cr) | 18.3 | 4.01 | 4.01 | Old counted every cut line. New counts cuts on non-scheme lines once per stockist and month; the rest of the old figure is cut scheme loading (next rows): new + scheme cuts = old |
| Of which outside scheme weeks (Rs cr) | 3.54 | 4.01 | 4.01 | Scheme sales now identified by scheme code; all counted cuts are non-scheme |
| Cuts on scheme orders, last 6 months (Rs cr) | – | 14.29 | 14.29 | Quarter-end loading the C&F could not fill; reported, not counted as demand |
| Kolkata stock above 3 months (Rs cr) | 1.66 | – | – | Replaced by 'above 2 months of allocated volume' (client target, CF Sch 2 2.2); see returns |
| Unfilled orders coverable from other C&Fs' spare | 0.491 | – | – | Retired: top-ups now come from the CDC (assumed able to supply); returns go to the CDC |
| Returns to the CDC (Rs cr) | – | 0.92 | 0.62 | Spare above 2 months; batches keep 60% after 14 days; at least Rs 5 L per SKU |

**Unchanged** (they never used the report field): the claims figures, the claim back-test, expiry value under 60% (Kolkata Rs 1.18 cr), the batch-order alert (Kolkata 71%), the scheme report (4.25% against 0.35%) and free goods over the 3% cap (Rs 3.954 cr).

## 3. How demand is worked out now (your answers, 21–22 Nov)

- **Dispatched:** invoiced + free packs, in SKU-master packs.
- **Ordered:** the highest `ordered_qty` on an order line, taken once. A cut line is a stock shortfall, and its re-order is not counted twice.
- **Scheme sales:** lines with a scheme code. Normal demand leaves out the scheme spike.
- **Normal month:** the average of the last 3 months with no scheme lines; at 30 Sep 2026 these are 2026-05, 2026-07, 2026-08.
- **Allocated volume:** national normal demand × the C&F's share. Your national forecast and shares aren't available, so normal demand stands in for the forecast.
- **Target:** top up to 2 months of allocated volume, at most 1.2 months in one shipment (CF Sch 2 §2.2). Anything above 2 months is excess.
- **Returns:** only batches that still have 60% shelf life after 14 days in transit, and only at Rs 5.0 L or more per SKU.
- **Assumption:** Assumes the CDC can supply: national stock is sufficient (client, 22 Nov 2026).

## 4. Allocation shares: request for approval

| C&F | FY25 share | Proposed share | Change | Allocated on FY25 a month | Real need a month | Gap on FY25 |
|---|---|---|---|---|---|---|
| Kolkata | 18.7% | 14.0% | -4.7 pts | Rs 2.84 cr | Rs 2.21 cr | Rs 63.5 L over |
| Gurugram | 16.9% | 18.5% | +1.6 pts | Rs 2.57 cr | Rs 2.94 cr | Rs 37.2 L short |
| Lucknow | 15.5% | 20.8% | +5.3 pts | Rs 2.36 cr | Rs 3.29 cr | Rs 93.1 L short |
| Chennai | 18.1% | 17.3% | -0.8 pts | Rs 2.76 cr | Rs 2.76 cr | Rs 0.4 L over |
| Hyderabad | 15.5% | 14.8% | -0.7 pts | Rs 2.37 cr | Rs 2.36 cr | Rs 0.7 L over |
| Bhiwandi | 15.3% | 14.6% | -0.7 pts | Rs 2.33 cr | Rs 2.31 cr | Rs 2.0 L over |

Real need = non-scheme dispatches + orders cut for lack of stock, normal months.

**Please confirm:**
1. You approve the proposed shares, as a mid-year change through the Regional Distribution Manager (CF Sch 2 §2.2).
2. Whether to move in one step, or at most 5 points per review (Lucknow and Kolkata would then take two quarters).
3. Quarterly share reviews from here on.

Until you confirm, the pilot shows top-ups on both the proposed and the FY25 shares.

## 5. Evidence: six-month replay of the allocation

At each month-end from March to August 2026, top-ups are planned with data up to that date only, then compared with the next month's actual normal orders (Rs 85.81 cr in total).

| Plan | Orders left unfilled | Fill rate |
|---|---|---|
| What actually happened (reference) | Rs 4.01 cr | 95.3% |
| Proposed shares | Rs 2.47 cr | 97.1% |
| FY25 shares | Rs 3.53 cr | 95.9% |
| Old method (report field) | Rs 13.94 cr | 83.8% |

- **Returns:** 16 returns under the rules (worth Rs 1.23 cr); none left the returning C&F short the next month.
- **Misses:** they came in May and August, when normal orders ran 30–40% above the usual month. One top-up a month, capped at 1.2 months, cannot absorb that.
- **Suggestion:** a mid-month top-up when orders run ahead of plan.
- **Limits:** the replay assumes one delivery a month, ignores batches, and assumes the CDC can supply.

## 6. Stock billed under 60% shelf life (CO-POL-014 §7.1)

There are no approved exceptions, so **every one is flagged**: 1,171 invoice lines, Rs 6.26 cr, in the last four quarters. None went out with under 60 days to expiry. They are not blocked: each line has an 'Agreed' or 'No agreement on record' step for the stockist's consent.

| Likely reason | Value | Lines |
|---|---|---|
| Arrived old from the CDC | Rs 4.69 cr | 844 |
| Too much stock at the C&F | Rs 21.0 L | 45 |
| Picked out of order | Rs 77.9 L | 173 |
| Scheme push | Rs 12.2 L | 24 |
| No clear reason in the data | Rs 1.03 cr | 197 |

A line can have more than one reason. 'Arrived old' means the batch first appeared at the C&F with under 70% shelf life left; this cut-off is proposed, for you to confirm. Kolkata is the exception: there the main reason is picking out of order.

## 7. The 45 order lines that follow neither split-line format

Rule applied, as you asked: the highest `ordered_qty`, taken once per order line. It gives the same result as before on every one.

| Invoice | SKU | Rows | Ordered quantities on the rows | Taken | Source lines |
|---|---|---|---|---|---|
| INV/W01/2406/006828 | PFL1402 | 3 | 989, 989, blank | 989 | 5726, 5727, 5728 |
| INV/S01/2406/007456 | PFL1601 | 3 | 1677, 1677, blank | 1677 | 5784, 5785, 5786 |
| INV/W01/2407/009566 | PFL1102 | 3 | 248, 248, blank | 248 | 11195, 11196, 11197 |
| INV/E01/2408/011700 | PFL1301 | 3 | 2055, 2055, blank | 2055 | 11568, 11569, 11570 |
| INV/N02/2408/011258 | PFL1202 | 3 | 1975, 1975, blank | 1975 | 12509, 12510, 12511 |
| INV/N02/2409/014293 | PFL1008 | 3 | 1539, 1539, blank | 1539 | 15859, 15860, 15861 |
| INV/W01/2409/015170 | PFL1002 | 3 | 1251, 1251, blank | 1251 | 16845, 16846, 16847 |
| INV/N01/2411/019135 | PFL1203 | 3 | 953, 953, blank | 953 | 20879, 20880, 20881 |
| INV/W01/2411/020618 | PFL1303 | 3 | 723, 723, blank | 723 | 21259, 21260, 21261 |
| INV/S01/2411/020951 | PFL1404 | 3 | 1094, 1094, blank | 1094 | 22265, 22266, 22267 |
| INV/W01/2411/020500 | PFL1103 | 3 | 712, 712, blank | 712 | 22941, 22942, 22943 |
| INV/N02/2411/019525 | PFL1202 | 3 | 910, 910, blank | 910 | 22983, 22984, 22985 |
| INV/S02/2412/024655 | PFL1006 | 3 | 1237, 1237, blank | 1237 | 24496, 24497, 24498 |
| INV/N01/2501/025497 | PFL1505 | 3 | 2197, 2197, blank | 2197 | 28756, 28757, 28758 |
| INV/S01/2502/029681 | PFL1006 | 3 | 1054, 1054, blank | 1054 | 30474, 30475, 30476 |
| INV/S02/2502/029862 | PFL1201 | 3 | 1592, 1592, blank | 1592 | 31347, 31348, 31349 |
| INV/N01/2502/027764 | PFL1103 | 3 | 984, 984, blank | 984 | 31493, 31494, 31495 |
| INV/S01/2502/029409 | PFL1004 | 3 | 455, 455, blank | 455 | 32307, 32308, 32309 |
| INV/S01/2503/032789 | PFL1008 | 3 | 2720, 2720, blank | 2720 | 33415, 33416, 33417 |
| INV/S01/2503/033151 | PFL1401 | 3 | 9897, 9897, blank | 9897 | 35765, 35766, 35767 |
| INV/W01/2504/035377 | PFL1603 | 3 | 558, 558, blank | 558 | 36868, 36869, 36870 |
| INV/N02/2505/036947 | PFL1402 | 3 | 745, 745, blank | 745 | 39560, 39561, 39562 |
| INV/W01/2505/037689 | PFL1102 | 3 | 1751, 1751, blank | 1751 | 39599, 39600, 39601 |
| INV/S02/2505/038683 | PFL1401 | 3 | 1290, 1290, blank | 1290 | 41999, 42000, 42001 |
| INV/E01/2507/043711 | PFL1504 | 3 | 2189, 2189, blank | 2189 | 46951, 46952, 46953 |
| INV/N01/2507/042825 | PFL1502 | 3 | 724, 724, blank | 724 | 47323, 47324, 47325 |
| INV/E01/2507/043740 | PFL1008 | 3 | 1496, 1496, blank | 1496 | 47776, 47777, 47778 |
| INV/S02/2508/047151 | PFL1001 | 3 | 2001, 2001, blank | 2001 | 48727, 48728, 48729 |
| INV/W01/2508/046581 | PFL1103 | 3 | 1154, 1154, blank | 1154 | 48752, 48753, 48754 |
| INV/N02/2508/045506 | PFL1003 | 3 | 1619, 1619, blank | 1619 | 50026, 50027, 50028 |
| INV/E01/2508/046149 | PFL1004 | 3 | 859, 859, blank | 859 | 50983, 50984, 50985 |
| INV/E01/2511/054712 | PFL1103 | 3 | 707, 707, blank | 707 | 58239, 58240, 58241 |
| INV/N01/2511/054061 | PFL1505 | 3 | 2599, 2599, blank | 2599 | 58758, 58759, 58760 |
| INV/W01/2511/055299 | PFL1006 | 3 | 2535, 2535, blank | 2535 | 59838, 59839, 59840 |
| INV/N01/2511/054092 | PFL1302 | 3 | 1367, 1367, blank | 1367 | 60545, 60546, 60547 |
| INV/S01/2601/062028 | PFL1304 | 3 | 1081, 1081, blank | 1081 | 66034, 66035, 66036 |
| INV/S02/2602/065135 | PFL1507 | 3 | 834, 834, blank | 834 | 68621, 68622, 68623 |
| INV/N01/2603/065875 | PFL1504 | 3 | 3083, 3083, blank | 3083 | 71046, 71047, 71048 |
| INV/S02/2603/069138 | PFL1502 | 3 | 712, 712, blank | 712 | 72235, 72236, 72237 |
| INV/E01/2604/070186 | PFL1205 | 3 | 585, blank, 585 | 585 | 76500, 76501, 76502 |
| INV/N02/2605/072593 | PFL1008 | 3 | 1020, 1020, blank | 1020 | 78247, 78248, 78249 |
| INV/N01/2605/071979 | PFL1204 | 3 | 948, 948, blank | 948 | 78684, 78685, 78686 |
| INV/S01/2607/080282 | PFL1505 | 3 | 2317, 2317, blank | 2317 | 84529, 84530, 84531 |
| INV/N01/2608/081128 | PFL1506 | 3 | 1603, 1603, blank | 1603 | 88375, 88376, 88377 |
| INV/S02/2608/082913 | PFL1004 | 3 | 512, 512, blank | 512 | 88504, 88505, 88506 |

## 8. Open points for you

1. Approve the share change (section 4).
2. Confirm the 70% 'arrived old' cut-off (section 6).
3. Consider a mid-month top-up in demand spikes (section 5).
4. Where decisions and steps are stored once the pilot is deployed: today they're kept locally only.
