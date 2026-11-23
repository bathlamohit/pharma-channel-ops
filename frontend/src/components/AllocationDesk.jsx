import { useEffect, useMemo, useState } from "react";
import { api, inr, inrShort } from "../api.js";
import Citations from "./Citations.jsx";

// Allocation on demand from invoices (plan step 2; docs/allocation-demand-plan.md).
// Each C&F is topped up from the CDC to 2 months of its allocated volume, at most 1.2 months per
// shipment (CF Sch 2 2.2). Shares: current (recommended, awaiting the client) or FY25 (the client's
// instruction until then). Excess goes back to the CDC only under the client's return rules.

const STATUS = {
  "out of stock": { label: "Out of stock", tone: "bad" },
  "below target": { label: "Below target", tone: "warn" },
  excess: { label: "Excess", tone: "info" },
  "on target": { label: "On target", tone: "ok" },
};
const TOPUP_STEPS = ["Allocation raised", "Dispatched from CDC"];
const RETURN_STEPS = ["Return requested", "Return approved", "Received at CDC"];
const SHARE_STEPS = ["Share change requested", "Share change approved"];
const MAX_COVER = 4;
const packs = (n) => Number(n).toLocaleString("en-IN");
const pct = (v) => `${(v * 100).toFixed(1)}%`;
const fmtMonth = (d) => new Date(d).toLocaleDateString("en-IN", { month: "short", year: "numeric" });
const fmtDate = (d) => new Date(d).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" });

function useName() {
  const [name, setName] = useState(() => {
    try {
      return localStorage.getItem("sankalp.decider") || "";
    } catch {
      return "";
    }
  });
  return [name, (v) => {
    setName(v);
    try {
      localStorage.setItem("sankalp.decider", v);
    } catch {
      /* not remembered */
    }
  }];
}

function CoverBar({ months, target = 2 }) {
  const v = months == null ? 0 : Math.min(MAX_COVER, months);
  const tone = months == null ? "" : months < target - 0.05 ? "bad" : months > target + 0.05 ? "info" : "ok";
  return (
    <div className="cover" title={months == null ? "no allocation" : `${months} months of stock; target ${target}`}>
      <div className={`cover-fill ${tone}`} style={{ width: `${(v / MAX_COVER) * 100}%` }} />
      <div className="cover-target" style={{ left: `${(target / MAX_COVER) * 100}%` }} />
    </div>
  );
}

function Steps({ steps, done, onStep, busy }) {
  const next = steps.find((s) => !done.includes(s));
  return (
    <div className="steps">
      {steps.map((s) =>
        done.includes(s) ? (
          <span key={s} className="step done">✓ {s}</span>
        ) : s === next ? (
          <button key={s} className="small" disabled={busy} onClick={() => onStep(s)}>{s}</button>
        ) : (
          <span key={s} className="step todo">{s}</span>
        ),
      )}
    </div>
  );
}

function stepsFor(p) {
  if (p.action === "top_up") return TOPUP_STEPS;
  if (p.action === "excess") return p.return_qty > 0 ? RETURN_STEPS : ["Replenishment paused"];
  return [];
}

function ProductRow({ p, done, onStep, busy, period }) {
  const s = STATUS[p.status];
  return (
    <article className={`task tone-${s.tone === "ok" ? "" : s.tone}`}>
      <header>
        <span className={`tag tag-${s.tone}`}>{s.label}</span>
        <strong>{p.product}</strong>
        <span className="mono hint">{p.sku_code}</span>
      </header>
      <div className="task-facts">
        <div><span>Stock</span><strong>{packs(p.stock)} packs</strong></div>
        <div><span>Allocated a month</span><strong>{packs(Math.round(p.allocated_month))}</strong></div>
        <div>
          <span>Months of stock</span>
          <CoverBar months={p.months_of_stock} />
          <small>{p.months_of_stock == null ? "no allocation" : `${p.months_of_stock.toFixed(2)} of 2`}</small>
        </div>
        {p.top_up > 0 && <div><span>Top-up from the CDC</span><strong>{packs(p.top_up)} packs</strong><small>{inr(p.top_up_inr)}</small></div>}
        {p.return_qty > 0 && <div><span>Return to the CDC</span><strong>{packs(p.return_qty)} packs</strong><small>{inr(p.return_inr)}</small></div>}
      </div>
      <p className="task-why"><strong>Why:</strong> {p.why}.</p>
      {p.action !== "none" && (
        <>
          <p className="task-do"><strong>What to do:</strong> {p.do}</p>
          <div className="task-foot">
            <span className="clause">{p.clause}</span>
            <Steps steps={stepsFor(p)} done={done} busy={busy}
              onStep={(step) => onStep({ cnf_code: p.cnf_code, sku_code: p.sku_code, step,
                qty: p.action === "top_up" ? p.top_up : p.return_qty || undefined,
                note: p.action === "top_up" ? `Top-up for ${period}` : p.return_qty > 0 ? "Return to the CDC" : `Hold for ${period}` })} />
          </div>
        </>
      )}
    </article>
  );
}

function stepsDone(actions, cfa, sku, note) {
  return (actions || []).filter((a) => a.cnf_code === cfa && a.sku_code === sku && (a.note || "") === note).map((a) => a.step);
}

function Shares({ s, onStep, busy }) {
  const done = (s.actions || []).map((a) => a.step);
  const max = Math.max(...s.cfas.flatMap((c) => [c.fy25_share, c.current_share])) * 1.15;
  return (
    <div className="schemes">
      <p className="hint">
        <strong>{s.status}.</strong> Current share = each C&F's share of real need now (non-scheme dispatches plus orders cut for
        lack of stock). FY25 shares send Lucknow less and Kolkata more than they now need.
      </p>
      <section className="card">
        <h3>Share of national allocation, FY25 against current</h3>
        <div className="share-rows">
          {s.cfas.map((c) => (
            <div key={c.cnf_code} className="share-row">
              <span className="q-label">{c.cnf_city}</span>
              <div className="share-bars">
                <div className="share-bar fy25" style={{ width: `${(c.fy25_share / max) * 100}%` }} title={`FY25 ${pct(c.fy25_share)}`} />
                <div className="share-bar now" style={{ width: `${(c.current_share / max) * 100}%` }} title={`Current ${pct(c.current_share)}`} />
              </div>
              <span className="q-val">
                {pct(c.fy25_share)} → <strong>{pct(c.current_share)}</strong> ({c.change_pts > 0 ? "+" : ""}{c.change_pts} pts)
                {c.over_step_limit && <span className="tag tag-warn">over {s.step_limit_pts}-pt limit</span>}
              </span>
              <span className={`q-gap ${c.gap_on_fy25_inr > 0 ? "short" : ""}`}>
                {c.gap_on_fy25_inr > 0 ? `${inrShort(c.gap_on_fy25_inr)} a month short on FY25` : `${inrShort(-c.gap_on_fy25_inr)} a month over on FY25`}
              </span>
            </div>
          ))}
        </div>
        <p className="hint"><span className="legend fy25" /> FY25 share <span className="legend now" /> current share</p>
      </section>
      <section className="card">
        <h3>Products whose share moved most</h3>
        <div className="scroll">
          <table>
            <thead><tr><th>C&F</th><th>Product</th><th>FY25</th><th>Current</th></tr></thead>
            <tbody>
              {s.largest_product_changes.map((r) => (
                <tr key={`${r.cnf_code}-${r.sku_code}`}><td>{r.cnf_city}</td><td>{r.product}</td><td>{pct(r.fy25_share)}</td><td>{pct(r.current_share)}</td></tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
      <div className="task-foot">
        <span className="hint">Mid-year change via the Regional Distribution Manager (CF Sch 2 2.2):</span>
        <Steps steps={SHARE_STEPS} done={done} busy={busy}
          onStep={(step) => onStep({ cnf_code: "NATIONAL", step, note: "Move to current shares" })} />
      </div>
    </div>
  );
}

function Schemes({ s, onStep, busy }) {
  const done = (s.actions || []).map((a) => a.step);
  const maxShare = Math.max(...s.quarters.map((q) => q.share), s.cap_share) * 1.15;
  return (
    <div className="schemes">
      <div className="summary">
        <div className="stat stat-reject"><span>Claims on scheme products</span><strong>{(s.scheme_rate * 100).toFixed(2)}% of sales</strong></div>
        <div className="stat"><span>On other products</span><strong>{(s.other_rate * 100).toFixed(2)}% of sales</strong></div>
        <div className="stat"><span>Extra claims from schemes, last 4 quarters</span><strong>{inrShort(s.excess_claims_inr)}</strong></div>
        <div className="stat stat-reject"><span>Free goods over the 3% cap</span><strong>{inrShort(s.over_cap_inr)} in {s.quarters_over} quarters</strong></div>
      </div>
      <p className="hint">
        Products sold under quarter-end schemes come back as expiry claims about {Math.round(s.scheme_rate / s.other_rate)} times as
        often as other products. Free goods in a quarter may not pass {Math.round(s.cap_share * 100)}% of that quarter's sales
        ({s.cap_clause}); above the cap the CFO must approve ({s.approval_clause}). No scheme may go to a stockist holding over{" "}
        {s.stock_norm_months} months of stock ({s.stock_norm_clause}).
      </p>
      <section className="card">
        <h3>Free goods against the cap, by quarter</h3>
        <div className="qbars">
          {s.quarters.map((q) => (
            <div key={q.quarter} className="qbar" title={`${q.quarter}: ${(q.share * 100).toFixed(2)}% of sales`}>
              <span className="q-label">{q.quarter}</span>
              <div className="q-track">
                <div className={`q-fill ${q.over_cap_inr > 0 ? "over" : ""}`} style={{ width: `${(q.share / maxShare) * 100}%` }} />
                <div className="q-cap" style={{ left: `${(s.cap_share / maxShare) * 100}%` }} />
              </div>
              <span className="q-val">{(q.share * 100).toFixed(2)}%{q.over_cap_inr > 0 && ` · ${inrShort(q.over_cap_inr)} over`}</span>
            </div>
          ))}
        </div>
      </section>
      <div className="task-foot">
        <span className="hint">Take it to the people who set scheme terms:</span>
        <div className="steps">
          {["Raised with NSM", "Raised with CFO"].map((st) =>
            done.includes(st) ? (
              <span key={st} className="step done">✓ {st}</span>
            ) : (
              <button key={st} className="small" disabled={busy}
                onClick={() => onStep({ cnf_code: "NATIONAL", step: st, note: `Scheme claims ${(s.scheme_rate * 100).toFixed(2)}%; ${inrShort(s.over_cap_inr)} over cap` })}>
                {st}
              </button>
            ),
          )}
        </div>
      </div>
    </div>
  );
}

function Restatement({ rows }) {
  const fmt = (v) => (v == null ? "–" : v);
  return (
    <section className="card">
      <h3>What changed, and why</h3>
      <p className="hint">The client asked to see the old figure, the new figure and the reason side by side (22 Nov 2026).</p>
      <div className="scroll">
        <table className="restate">
          <thead><tr><th>Figure</th><th>Old</th><th>New, current shares</th><th>New, FY25 shares</th><th>Reason</th></tr></thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.figure}>
                <td>{r.figure}</td><td>{fmt(r.old)}</td><td><strong>{fmt(r.new_current_shares)}</strong></td><td>{fmt(r.new_fy25_shares)}</td>
                <td className="hint">{r.reason}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

export default function AllocationDesk({ focus }) {
  const [basis, setBasis] = useState("current");
  const [view, setView] = useState("cfa");
  const [overview, setOverview] = useState(null);
  const [cfa, setCfa] = useState(null);
  const [plan, setPlan] = useState(null);
  const [kind, setKind] = useState("act");
  const [data, setData] = useState({});
  const [name, setName] = useName();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const loadOverview = (b) =>
    api(`/api/allocation/overview?basis=${b}`).then((o) => {
      setOverview(o);
      setCfa((cur) => cur || o.cards[0]?.cnf_code);
    }).catch((e) => setError(e.message));
  const loadPlan = (code, b) => api(`/api/allocation/plan?cfa=${encodeURIComponent(code)}&basis=${b}`).then(setPlan).catch((e) => setError(e.message));
  const URL = {
    topups: (b) => `/api/allocation/topups?basis=${b}`,
    returns: (b) => `/api/allocation/returns?basis=${b}`,
    shares: () => "/api/allocation/shares",
    changes: () => "/api/allocation/restatement",
    schemes: () => "/api/allocation/schemes",
  };
  const loadView = (v, b) => URL[v] && api(URL[v](b)).then((d) => setData((m) => ({ ...m, [v]: d }))).catch((e) => setError(e.message));

  useEffect(() => {
    loadOverview(basis);
    setData((m) => ({ shares: m.shares, changes: m.changes, schemes: m.schemes }));
  }, [basis]);
  useEffect(() => {
    if (!cfa) return;
    setPlan(null);
    loadPlan(cfa, basis);
  }, [cfa, basis]);
  useEffect(() => {
    if (view !== "cfa" && !data[view]) loadView(view, basis);
  }, [view, basis, data]);
  useEffect(() => {
    const ref = focus?.ref;
    if (!ref) return;
    const alias = { moves: "returns" };
    if (["topups", "returns", "shares", "changes", "schemes", "moves"].includes(ref)) setView(alias[ref] || ref);
    else if (ref.startsWith("CF-")) {
      setView("cfa");
      setCfa(ref);
      setKind("act");
    }
  }, [focus?.n]);

  const groups = useMemo(() => {
    const g = { act: [], excess: [], ok: [] };
    for (const p of plan?.products || []) g[p.status === "excess" ? "excess" : p.status === "on target" ? "ok" : "act"].push(p);
    return g;
  }, [plan]);

  const period = overview ? fmtMonth(new Date(new Date(overview.as_of).getTime() + 86400000)) : "";

  async function record(body) {
    if (name.trim().length < 2) {
      setError("Enter your name at the top first.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      await api("/api/stock/action", { ...body, by: name.trim() });
      await Promise.all([cfa && loadPlan(cfa, basis), view !== "cfa" && loadView(view, basis)]);
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  const card = overview?.cards.find((c) => c.cnf_code === cfa);
  const n = overview?.national;
  const doneFor = (p) => stepsDone(plan?.actions, p.cnf_code, p.sku_code,
    p.action === "top_up" ? `Top-up for ${period}` : p.return_qty > 0 ? "Return to the CDC" : `Hold for ${period}`);

  return (
    <section className="stockdesk">
      <div className="stock-intro">
        <div>
          <h2>Allocation</h2>
          <p className="hint">
            Stock as of <strong>{overview ? fmtDate(overview.as_of) : "…"}</strong>. Each C&F is topped up from the CDC to{" "}
            <strong>2 months</strong> of its allocated volume, at most 1.2 months in one shipment (CF Sch 2 2.2). Demand comes from
            invoices; normal months {overview?.normal_months.slice().sort().map((m) => fmtMonth(`${m}-01`)).join(", ")}.
          </p>
        </div>
        <label className="name-field">
          Your name
          <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Recorded with each action" />
        </label>
      </div>
      <div className="basis-row">
        <span className="hint">Shares:</span>
        <div className="seg seg-inline" role="tablist" aria-label="Share basis">
          <button className={basis === "current" ? "on" : ""} onClick={() => setBasis("current")}>Current (recommended)</button>
          <button className={basis === "fy25" ? "on" : ""} onClick={() => setBasis("fy25")}>FY25 (client's instruction)</button>
        </div>
        <span className="hint">{basis === "current" ? "Awaiting the client's approval of the share change." : "FY25 leaves Lucknow about 30% short."}</span>
      </div>
      <details className="rules-box">
        <summary>How this is worked out</summary>
        <ul>{overview?.assumptions.map((a) => <li key={a}>{a}</li>)}</ul>
      </details>

      {error && <p className="status error">{error}</p>}
      {!overview && !error && <div className="loading">Loading allocation…</div>}

      {n && (
        <div className="summary">
          <div className="stat stat-reject"><span>Months of stock, national</span><strong>{n.cover_months} of 2</strong></div>
          <div className="stat"><span>Top-up from the CDC this month</span><strong>{inrShort(n.top_up_inr)}</strong><small className="hint">{n.top_up_lines} product lines</small></div>
          <div className="stat"><span>Returns to the CDC</span><strong>{inrShort(n.return_inr)}</strong><small className="hint">{n.return_lines} products</small></div>
          <div className="stat stat-reject"><span>Orders not filled, 6 months</span><strong>{inrShort(n.unfilled_6m_inr)}</strong><small className="hint">plus {inrShort(n.scheme_cut_6m_inr)} of scheme orders cut</small></div>
        </div>
      )}

      {overview && (
        <div className="seg seg-inline view-switch wide-switch" role="tablist">
          {[["cfa", "By C&F"], ["topups", "Top-up from CDC"], ["returns", "Returns to CDC"], ["shares", "Shares"],
            ["changes", "What changed"], ["schemes", "Schemes (NSM, CFO)"]].map(([id, label]) => (
            <button key={id} className={view === id ? "on" : ""} onClick={() => setView(id)}>{label}</button>
          ))}
        </div>
      )}

      {overview && view === "cfa" && (
        <>
          <div className="cfa-grid">
            {overview.cards.map((c) => (
              <button key={c.cnf_code} className={`cfa ${c.cnf_code === cfa ? "active" : ""} ${c.cover_months < 1 ? "alerting" : ""}`}
                onClick={() => setCfa(c.cnf_code)}>
                <div className="cfa-top"><strong>{c.cnf_city}</strong><span className="mono">{c.cnf_code}</span></div>
                <div className="cfa-money">{c.cover_months} months</div>
                <CoverBar months={c.cover_months} />
                <div className="hint">{basis === "current" ? "FY25" : "current"} shares: {c.cover_months_other_basis}</div>
                <div className="cfa-chips">
                  {c.out_of_stock > 0 && <span className="tag tag-bad">{c.out_of_stock} out of stock</span>}
                  {c.below_target > 0 && <span className="tag tag-warn">{c.below_target} below target</span>}
                  {c.excess > 0 && <span className="tag">{c.excess} excess</span>}
                </div>
                <div className="hint">Top-up {inrShort(c.top_up_inr)}{c.return_inr > 0 && ` · return ${inrShort(c.return_inr)}`}</div>
              </button>
            ))}
          </div>

          {card && (
            <div className="cfa-work">
              <header className="cfa-work-head">
                <h3>{card.cnf_city} <span className="mono hint">{card.cnf_code}</span></h3>
                <div className="kind-filter">
                  <button className={kind === "act" ? "chip on" : "chip"} onClick={() => setKind("act")}>Top up {groups.act.length}</button>
                  <button className={kind === "excess" ? "chip on" : "chip"} onClick={() => setKind("excess")}>Excess {groups.excess.length}</button>
                  <button className={kind === "ok" ? "chip on" : "chip"} onClick={() => setKind("ok")}>On target {groups.ok.length}</button>
                  <button className={kind === "unfilled" ? "chip on" : "chip"} onClick={() => setKind("unfilled")}>Orders not filled</button>
                </div>
              </header>
              <p className="hint">
                Share of national allocation: FY25 {pct(card.share_fy25)}, current {pct(card.share_current)} ({card.share_change_pts > 0 ? "+" : ""}
                {card.share_change_pts} pts). Months of stock on its own normal demand: {card.cover_on_own_demand}.
              </p>
              {!plan && <div className="loading">Working out {card.cnf_city}…</div>}
              {plan && kind !== "unfilled" && (
                <div className="tasks">
                  {!groups[kind].length && <p className="card">Nothing here for {card.cnf_city}.</p>}
                  {groups[kind].map((p) => (
                    <ProductRow key={p.sku_code} p={p} done={doneFor(p)} onStep={record} busy={busy} period={period} />
                  ))}
                </div>
              )}
              {plan && kind === "unfilled" && (
                <section>
                  <p className="task-why">
                    In the last 6 months {card.cnf_city} could not fill <strong>{inr(plan.unfilled.total_inr)}</strong> of normal orders
                    (counted once per stockist and month), plus {inr(plan.unfilled.scheme_cut_inr)} of quarter-end scheme orders.
                  </p>
                  <div className="scroll">
                    <table>
                      <thead><tr><th>Product</th><th>Cut lines</th><th>Normal orders not filled</th><th>Scheme orders cut</th></tr></thead>
                      <tbody>
                        {plan.unfilled.by_product.map((u) => (
                          <tr key={u.sku_code}><td>{u.product}</td><td>{u.cut_lines}</td><td>{inr(u.unfilled_inr)}</td><td>{inr(u.scheme_cut_inr)}</td></tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </section>
              )}
              {plan && <Citations citations={plan.citations} />}
            </div>
          )}
        </>
      )}

      {view === "topups" && (
        <div className="cfa-work">
          {!data.topups && <div className="loading">Working out this month's top-up…</div>}
          {data.topups && (
            <>
              <p className="hint">
                {data.topups.lines} product lines, {inrShort(data.topups.total_inr)} for {period}. {data.topups.assumption}.
              </p>
              {data.topups.cfas.map((c) => (
                <details key={c.cnf_code} className="card topup-cfa" open={c === data.topups.cfas[0]}>
                  <summary>
                    <strong>{c.cnf_city}</strong> · {c.lines.length} products · {packs(c.packs)} packs · {inrShort(c.value_inr)}
                    {c.out_of_stock > 0 && <span className="tag tag-bad">{c.out_of_stock} out of stock</span>}
                  </summary>
                  <div className="scroll">
                    <table>
                      <thead><tr><th>Product</th><th>Status</th><th>Stock</th><th>Allocated a month</th><th>Top-up</th><th>Value</th><th>Steps</th></tr></thead>
                      <tbody>
                        {c.lines.map((p) => (
                          <tr key={p.sku_code}>
                            <td>{p.product}</td><td>{STATUS[p.status].label}</td><td>{packs(p.stock)}</td>
                            <td>{packs(Math.round(p.allocated_month))}</td><td><strong>{packs(p.top_up)}</strong></td><td>{inrShort(p.top_up_inr)}</td>
                            <td>
                              <Steps steps={TOPUP_STEPS} busy={busy}
                                done={stepsDone(data.topups.actions, p.cnf_code, p.sku_code, `Top-up for ${period}`)}
                                onStep={(step) => record({ cnf_code: p.cnf_code, sku_code: p.sku_code, step, qty: p.top_up, note: `Top-up for ${period}` })} />
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </details>
              ))}
            </>
          )}
        </div>
      )}

      {view === "returns" && (
        <div className="cfa-work">
          {!data.returns && <div className="loading">Checking which stock can go back…</div>}
          {data.returns && (
            <>
              <ul className="facts-list">{data.returns.rules.map((r) => <li key={r}>{r}</li>)}</ul>
              {!data.returns.returns.length && <p className="card">No return meets the rules.</p>}
              <div className="tasks">
                {data.returns.returns.map((r) => (
                  <article key={`${r.cnf_code}-${r.sku_code}`} className="task tone-info">
                    <header>
                      <strong>{r.product}</strong>
                      <span className="move-route">{r.cnf_city} → CDC</span>
                      <span className="move-qty">{packs(r.return_qty)} packs · {inr(r.value_inr)}</span>
                    </header>
                    <p className="task-why">
                      {packs(r.spare_packs)} packs above 2 months. Batches that qualify (oldest first):{" "}
                      {r.batches.map((b) => `${b.batch_no} (exp ${fmtMonth(b.expiry_date)}, ${packs(b.qty)}, ${Math.round(b.shelf_after_transit * 100)}% after transit)`).join("; ")}.
                    </p>
                    <div className="task-foot">
                      <span className="clause">CF Sch 2 2.5; client 22 Nov</span>
                      <Steps steps={RETURN_STEPS} busy={busy} done={stepsDone(data.returns.actions, r.cnf_code, r.sku_code, "Return to the CDC")}
                        onStep={(step) => record({ cnf_code: r.cnf_code, sku_code: r.sku_code, step, qty: r.return_qty, note: "Return to the CDC" })} />
                    </div>
                  </article>
                ))}
              </div>
            </>
          )}
        </div>
      )}

      {view === "shares" && (
        <div className="cfa-work">
          {!data.shares && <div className="loading">Loading shares…</div>}
          {data.shares && <Shares s={data.shares} onStep={record} busy={busy} />}
        </div>
      )}

      {view === "changes" && (
        <div className="cfa-work">
          {!data.changes && <div className="loading">Loading…</div>}
          {data.changes && <Restatement rows={data.changes.rows} />}
        </div>
      )}

      {view === "schemes" && (
        <div className="cfa-work">
          {!data.schemes && <div className="loading">Loading scheme figures…</div>}
          {data.schemes && <Schemes s={data.schemes} onStep={record} busy={busy} />}
        </div>
      )}
    </section>
  );
}
