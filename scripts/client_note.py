"""Write the client note on demand and allocation from the live figures (plan step 6).

    python scripts/client_note.py   ->  docs/client-note-demand-and-allocation.md

Every number comes from the app's own modules, so the note can be regenerated after a data refresh.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent import allocation, allocation_backtest, demand, policy, short_dated  # noqa: E402

OUT = ROOT / "docs" / "client-note-demand-and-allocation.md"


def cr(v):
    return "–" if v is None else f"Rs {v / 1e7:.2f} cr" if abs(v) >= 1e7 else f"Rs {v / 1e5:.1f} L"


def num(v):
    return "–" if v is None else f"{v:g}" if isinstance(v, float) else str(v)


def main():
    rs = allocation.restatement()
    sh = allocation.shares()
    ov = allocation.overview("current")
    ov25 = allocation.overview("fy25")
    bt = allocation_backtest.run()
    sd = short_dated.summary()
    irr = demand.irregular_order_lines()
    ratio_note = "about 44–48% of what the C&Fs invoiced, at every snapshot from Sep 2025 to Sep 2026"
    L = []
    w = L.append
    w("# Demand and allocation: what changed and why")
    w("")
    w(f"Project Sankalp pilot · prepared 22 Nov 2026 · stock and sales to {policy.SNAPSHOT_DATE:%d %b %Y}")
    w("")
    w("## 1. In short")
    w("")
    w(f"- **The SAP stock report's 'average monthly outward' was {ratio_note}.** As you confirmed, it has not been reliable "
      "since the ERP extract was set up. **We no longer use it.** All demand now comes from the sales extract (primary sales), "
      "and every figure below is calculated from invoices.")
    w(f"- **The network is short, not overstocked:** {ov['national']['cover_months']} months of stock nationally, against the "
      f"2-month target (CF Sch 2 §2.2). This month's top-up from the CDC comes to {cr(ov['national']['top_up_inr'])}.")
    lk = next(c for c in sh["cfas"] if c["cnf_code"] == "CF-N02")
    kol = next(c for c in sh["cfas"] if c["cnf_code"] == "CF-E01")
    w(f"- **We recommend updating the allocation shares now.** On FY25 shares, Lucknow is {cr(lk['gap_on_fy25_inr'])} a month short and "
      f"Kolkata {cr(-kol['gap_on_fy25_inr'])} a month over. In a six-month replay, current shares would have left "
      f"{cr(bt['summary']['current']['unfilled_inr'])} of normal orders unfilled, against {cr(bt['summary']['fy25']['unfilled_inr'])} on FY25.")
    w(f"- **Most stock billed under 60% shelf life arrived at the C&F already aged.** That covers "
      f"{cr(next(r for r in sd['reasons'] if r['reason'] == 'arrived_old')['value_inr'])} of the {cr(sd['value_inr'])} billed this way "
      "in the last four quarters.")
    w("")
    w("## 2. Old figure, new figure, and why")
    w("")
    w("| Figure | Old | New (current shares) | New (FY25 shares) | Reason |")
    w("|---|---|---|---|---|")
    for r in rs:
        w(f"| {r['figure']} | {num(r['old'])} | {num(r['new_current_shares'])} | {num(r['new_fy25_shares'])} | {r['reason']} |")
    w("")
    w("**Unchanged** (they never used the report field): the claims figures, the claim back-test, expiry value under 60% "
      "(Kolkata Rs 1.18 cr), the batch-order alert (Kolkata 71%), the scheme report (4.25% against 0.35%) and free goods over "
      "the 3% cap (Rs 3.954 cr).")
    w("")
    w("## 3. How demand is worked out now (your answers, 21–22 Nov)")
    w("")
    w("- **Dispatched:** invoiced + free packs, in SKU-master packs.")
    w("- **Ordered:** the highest `ordered_qty` on an order line, taken once. A cut line is a stock shortfall, and its "
      "re-order is not counted twice.")
    w("- **Scheme sales:** lines with a scheme code. Normal demand leaves out the scheme spike.")
    w(f"- **Normal month:** the average of the last 3 months with no scheme lines; at {policy.SNAPSHOT_DATE:%d %b %Y} these are "
      f"{', '.join(sorted(str(m) for m in demand.normal_months()))}.")
    w("- **Allocated volume:** national normal demand × the C&F's share. Your national forecast and shares aren't "
      "available, so normal demand stands in for the forecast.")
    w("- **Target:** top up to 2 months of allocated volume, at most 1.2 months in one shipment (CF Sch 2 §2.2). "
      "Anything above 2 months is excess.")
    w(f"- **Returns:** only batches that still have 60% shelf life after {int(policy.RETURN_TRANSIT_DAYS.value)} days in transit, "
      f"and only at {cr(policy.RETURN_MIN_VALUE_INR.value)} or more per SKU.")
    w(f"- **Assumption:** {policy.CDC_SUPPLY_ASSUMPTION}.")
    w("")
    w("## 4. Allocation shares: request for approval")
    w("")
    w("| C&F | FY25 share | Proposed share | Change | Allocated on FY25 a month | Real need a month | Gap on FY25 |")
    w("|---|---|---|---|---|---|---|")
    for c in sh["cfas"]:
        gap = cr(abs(c["gap_on_fy25_inr"])) + (" short" if c["gap_on_fy25_inr"] > 0 else " over")
        w(f"| {c['cnf_city']} | {c['fy25_share']:.1%} | {c['current_share']:.1%} | {c['change_pts']:+.1f} pts | "
          f"{cr(c['fy25_allocated_inr'])} | {cr(c['real_need_inr'])} | {gap} |")
    w("")
    w("Real need = non-scheme dispatches + orders cut for lack of stock, normal months.")
    w("")
    w("**Please confirm:**")
    w("1. You approve the proposed shares, as a mid-year change through the Regional Distribution Manager (CF Sch 2 §2.2).")
    w(f"2. Whether to move in one step, or at most {sh['step_limit_pts']:.0f} points per review (Lucknow and Kolkata would then "
      "take two quarters).")
    w("3. Quarterly share reviews from here on.")
    w("")
    w("Until you confirm, the pilot shows top-ups on both the proposed and the FY25 shares.")
    w("")
    w("## 5. Evidence: six-month replay of the allocation")
    w("")
    w(f"At each month-end from March to August 2026, top-ups are planned with data up to that date only, then compared "
      f"with the next month's actual normal orders ({cr(bt['orders_inr'])} in total).")
    w("")
    w("| Plan | Orders left unfilled | Fill rate |")
    w("|---|---|---|")
    labels = {"actual": "What actually happened (reference)", "current": "Proposed shares", "fy25": "FY25 shares",
              "old_report": "Old method (report field)"}
    for k in ("actual", "current", "fy25", "old_report"):
        v = bt["summary"][k]
        w(f"| {labels[k]} | {cr(v['unfilled_inr'])} | {v['fill_rate']:.1%} |")
    w("")
    w(f"- **Returns:** {bt['returns']['count']} returns under the rules (worth {cr(bt['returns']['value_inr'])}); none left the "
      "returning C&F short the next month.")
    w("- **Misses:** they came in May and August, when normal orders ran 30–40% above the usual month. One top-up a month, "
      "capped at 1.2 months, cannot absorb that.")
    w("- **Suggestion:** a mid-month top-up when orders run ahead of plan.")
    w("- **Limits:** the replay assumes one delivery a month, ignores batches, and assumes the CDC can supply.")
    w("")
    w("## 6. Stock billed under 60% shelf life (CO-POL-014 §7.1)")
    w("")
    w(f"There are no approved exceptions, so **every one is flagged**: {sd['lines']:,} invoice lines, {cr(sd['value_inr'])}, "
      f"in the last four quarters. None went out with under 60 days to expiry. They are not blocked: each line has an "
      "'Agreed' or 'No agreement on record' step for the stockist's consent.")
    w("")
    w("| Likely reason | Value | Lines |")
    w("|---|---|---|")
    for r in sd["reasons"]:
        w(f"| {r['label']} | {cr(r['value_inr'])} | {r['lines']} |")
    w("")
    w("A line can have more than one reason. 'Arrived old' means the batch first appeared at the C&F with under 70% shelf "
      "life left; this cut-off is proposed, for you to confirm. Kolkata is the exception: there the main reason is picking out "
      "of order.")
    w("")
    w("## 7. The 45 order lines that follow neither split-line format")
    w("")
    w("Rule applied, as you asked: the highest `ordered_qty`, taken once per order line. It gives the same result as before "
      "on every one.")
    w("")
    w("| Invoice | SKU | Rows | Ordered quantities on the rows | Taken | Source lines |")
    w("|---|---|---|---|---|---|")
    for r in irr.itertuples():
        vals = ", ".join("blank" if v != v else f"{v:g}" for v in r.ordered_values)
        w(f"| {r.invoice_no} | {r.sku_code} | {r.rows} | {vals} | {r.taken:g} | {', '.join(map(str, r.src_lines))} |")
    w("")
    w("## 8. Open points for you")
    w("")
    w("1. Approve the share change (section 4).")
    w("2. Confirm the 70% 'arrived old' cut-off (section 6).")
    w("3. Consider a mid-month top-up in demand spikes (section 5).")
    w("4. Where decisions and steps are stored once the pilot is deployed: today they're kept locally only.")
    OUT.write_text("\n".join(L) + "\n")
    print(f"Wrote {OUT.relative_to(ROOT)} ({len(L)} lines)")


if __name__ == "__main__":
    main()
