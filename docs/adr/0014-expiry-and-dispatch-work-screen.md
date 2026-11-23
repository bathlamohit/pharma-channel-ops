# 0014. Expiry and dispatch as a work screen: what to block, bill with consent, return and pick

- Status: Accepted
- Date: 2026-11-21

## Context
The Expiry & dispatch tab had one "Run" button that printed three summaries:
- the expiry radar
- the batch-order alert
- short-dated billing

The rows behind them were raw. A person at a CFA or in Supply Chain could see a problem, but not
what to do about it, in what order, or under which rule. The product owner asked for a screen
anyone can use to act on expiry and dispatch.

The policy text answers what to do:
- **CO-POL-014 7.1.** Bill with at least 60% of shelf life left; a stockist may refuse less.
  Nothing with under 60 days to expiry is dispatched. This confirms decision D1: both rules
  apply.
- **CO-POL-014 7.2, CF Sch 2 2.3.4 and 2.7.** Under 60 days, stock is blocked, never picked, and
  destroyed under witness.
- **CF 6.3, Sch 2 2.3.** Pick oldest expiry first; another batch only with a logged override.
- **CF Sch 2 2.5.** CFAs never ship to each other. Excess returns to the CDC on the Regional
  Distribution Manager's request and the Head of Supply Chain's approval, in 10 to 14 days.

## Decision
**A plan per batch** (`agent/stock.py`, plain pandas, no model). It works on the latest snapshot,
one row per CFA, product and batch; bin rows are merged. Batches are taken oldest expiry first:

| Status | Rule | Action shown |
|---|---|---|
| block | under 60 days to expiry | block in SAP, add to the destruction list |
| short_dated | under 60% shelf life | bill only with the stockist's written agreement; block at 60 days |
| at_risk | at this CFA's outward, part will not sell before its 60% date | return to the CDC for CFAs that can sell it (14 days' transit allowed), or push in dispatch |
| pick_first / in_line | sells in time | pick the oldest sellable batch first |

- **Return amount.** A CDC return asks only for what the receiving CFAs can sell in time; the
  rest is pushed in dispatch here.
- **Act-by date on every task:** now for a block; the block date for consent; the 60% date, less
  transit, for a return. Tasks are sorted by it, and lateness is judged against the stock date.

**The screen:**
- One card per CFA: value needing action, counts by kind, and the batch-order share.
- For the chosen CFA, three views:
  - **To do**, filterable by kind. Each task gives why, what to do, the clause, the CFAs that
    could take it, and step buttons.
  - **Pick order**: per product, batches in order, with "Pick now". It can be printed or marked
    as sent to the CFA.
  - **Batch-order check**: 12 months against the 35% line, the products most often picked out of
    order, and "Raise with the CFA".

**Action log** (`agent/stock_log.py`): `data/stock_actions.jsonl`, append-only and gitignored, the
same pattern as the claims store (0013). Steps record who and when. A CDC return must be
requested before it is approved, and approved before it is received.

## Alternatives considered
- **Keep the three summaries, add explanations.** Rejected: still a report, not a list of jobs.
- **Suggest CFA-to-CFA transfers.** Rejected: the C&F agreement forbids them (Sch 2 2.5).
- **Treat short-dated stock as unsellable.** Rejected: 7.1 lets a stockist accept it. Only the
  60-day block is absolute.

## Consequences
- The verified figure still holds: Kolkata Rs 1.18 cr under 60% of shelf life.
- The projection uses each CFA's average monthly outward. Seasonal or scheme-month swings are
  not modelled, and actions in the log do not change the plan until the next stock extract.
- Like the other stores, the action log does not persist on Vercel (0010).
- The Allocation and Weekly digest tabs still use the summary view.

## Amendment, 22 Nov 2026 (plan step 3)

**Selling rate.** The forecast now sells each C&F's **normal demand from invoices** (`agent/demand.py`),
not the SAP outward field, which the client confirmed is unreliable. The backtest shows:
- forecast error matches or beats a proportional baseline at every horizon
- flags are right 84% of the time, but catch 20% of leftovers (the old field: 55% / 55%)

**At-risk returns** follow the client's rules: the batch keeps 60% shelf life after 14 days in transit,
and the return is worth at least Rs 5 lakh. Otherwise the advice is "push in dispatch".

**"Not moving" watch list.** A sellable batch that sold under 5% since the previous snapshot is listed
on its own view, labelled "watch list, not a forecast".
- There's a "Checked with CFA" step.
- Together with the forecast it catches 43% of leftovers, at 55% precision.
- Evidence: `testing-report/Backtesting_Report.md`, section 3b.

**Dispatches under 60% shelf life (plan step 4).** Every invoice line in the last four quarters billed under
60% shelf life is flagged: 1,171 lines, Rs 6.262 cr. None went out with under 60 days to expiry (§7.1).
- **Reasons per line,** from data available at the time:
  - arrived old from the CDC: first seen at the C&F under 70% shelf life (proposed cut-off)
  - too much stock: over 2 months of normal demand at the previous snapshot
  - picked out of order: over 35% in the months before
  - scheme push: a scheme code on the line
- **Main reason:** 75% of the value arrived old from the CDC. At Kolkata it's picking out of order.
- **Each line** gets an "Agreed" or "No agreement on record" step (not blocked, per the client).
- **Code:** `agent/short_dated.py`.
