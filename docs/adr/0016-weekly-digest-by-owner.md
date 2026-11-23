# 0016. Weekly digest: one page per owner, linked to the work screens

- Status: Accepted
- Date: 2026-11-21

## Context
The Weekly digest tab was the last one with a "Run" button. It ran all six watch views and
printed one summary sentence per view, grouped by owner. After 0012 to 0015 the real work happens
on four screens. The digest should tell each owner where things stand this week and take them
straight to the work.

## Decision
`agent/digest.py` builds the digest from the same plans the work screens use (`stock.plan`,
`allocation`, the claims register and the new-claims store, and the action log). It uses no model
and is served at `GET /api/digest`. One section per owner:

| Section | Owner | Figures | To do |
|---|---|---|---|
| Claims | Commercial Finance | pending (360, Rs 95.9 L); pending over 30 days; days to credit note (45 against 30); new claims open and overdue | overdue new claims, then the oldest pending claims |
| Expiry and dispatch | Supply Chain | stock needing action; bill-with-consent batches; batches that will not sell in time; batch-order alert | the five tasks with the earliest act-by date across CFAs; any batch-order alert |
| Allocation | Demand Planning | national cover 1.74; unfilled orders Rs 18.30 cr; stock-outs; moves via the CDC | CFAs under 1 month; the largest moves |
| Schemes | NSM and CFO | 4.25% against 0.35%; Rs 4.76 cr extra; Rs 3.95 cr over the cap; latest quarter | review scheme terms |

- **Links.** Every to-do opens the screen where it is done, on the right claim, CFA, moves view
  or schemes view.
- **Done.** Each section lists the latest steps recorded on its screens: claim status changes
  from the claims store, stock and allocation steps from the action log. Batch steps belong to
  Supply Chain, product steps to Demand Planning, national steps to the NSM and CFO.
- **Email text.** A plain-text version of the same facts is shown, with Copy and Print. The tool
  never sends it.
- **First tab.** The digest is now the first tab, so the page opens on what needs doing this week.
  It refreshes each time the tab is shown.
- **Removed.** The old WatchPanel and Status components. `POST /api/watch` and the watch views
  stay: they back the verified-figure tests.

## Consequences
- "Pending over 30 days" counts register claims pending at the snapshot (129 of 360). The plan's
  "69% over 30 days" is still not reproduced (0009).
- The digest is as current as the data extract (30 Sep 2026) and the logs. On Vercel the logs do
  not persist (0010), so Done would be empty there.
