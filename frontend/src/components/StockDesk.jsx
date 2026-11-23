import { useEffect, useMemo, useState } from "react";
import { api, inr, inrShort } from "../api.js";
import Citations from "./Citations.jsx";
import { ShortDatedCfa, ShortDatedNational } from "./ShortDated.jsx";

// Expiry & dispatch, as work to do: pick a CFA, see what to block, what needs the stockist's
// agreement, what to send back through the CDC, and which batch to pick first. Every task says
// why, what to do and the clause; a person records what they did. Plan: agent/stock.py (ADR 0014).

const KIND = {
  block: { label: "Block", tone: "bad", steps: ["Blocked in SAP", "Added to destruction list"] },
  consent: { label: "Bill with consent", tone: "warn", steps: ["Offered with stockist consent"] },
  cdc_return: { label: "Return to CDC", tone: "warn", steps: ["Return requested", "Return approved", "Received at CDC"] },
  push: { label: "Push in dispatch", tone: "info", steps: ["Pushed in dispatch"] },
};
const STEP_WHO = {
  "Return requested": "Regional Distribution Manager",
  "Return approved": "Head of Supply Chain",
  "Blocked in SAP": "CFA",
  "Added to destruction list": "CFA",
};
const STATUS_LABEL = {
  pick_first: "Pick now",
  in_line: "Next",
  at_risk: "Pick now · part at risk",
  short_dated: "Consent only",
  block: "Blocked",
};
const fmtDate = (d) => new Date(d).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" });
const packs = (n) => Number(n).toLocaleString("en-IN");

function useName() {
  const [name, setName] = useState(() => {
    try {
      return localStorage.getItem("sankalp.decider") || "";
    } catch {
      return "";
    }
  });
  const save = (v) => {
    setName(v);
    try {
      localStorage.setItem("sankalp.decider", v);
    } catch {
      /* not remembered */
    }
  };
  return [name, save];
}

function CfaCard({ c, active, onPick }) {
  return (
    <button className={`cfa ${active ? "active" : ""} ${c.fefo_alert ? "alerting" : ""}`} onClick={() => onPick(c.cnf_code)}>
      <div className="cfa-top">
        <strong>{c.cnf_city}</strong>
        <span className="mono">{c.cnf_code}</span>
      </div>
      <div className="cfa-money">{inrShort(c.action_value_inr)}</div>
      <div className="hint">needs action, of {inrShort(c.stock_value_inr)} in stock</div>
      <div className="cfa-chips">
        {c.to_block > 0 && <span className="tag tag-bad">{c.to_block} to block</span>}
        {c.short_dated > 0 && <span className="tag tag-warn">{c.short_dated} consent only</span>}
        {c.at_risk > 0 && <span className="tag tag-warn">{c.at_risk} at risk</span>}
        {c.not_moving > 0 && <span className="tag tag-info">{c.not_moving} not moving</span>}
        {c.fefo_alert ? (
          <span className="tag tag-bad">Batch order {Math.round(c.fefo_share * 100)}%</span>
        ) : (
          <span className="tag">Batch order {Math.round(c.fefo_share * 100)}%</span>
        )}
      </div>
    </button>
  );
}

function ShelfBar({ share }) {
  const pct = Math.max(0, Math.min(1, share)) * 100;
  return (
    <div className="shelf" title={`${Math.round(pct)}% of shelf life left`}>
      <div className={`shelf-fill ${share < 0.6 ? "low" : ""}`} style={{ width: `${pct}%` }} />
      <div className="shelf-mark" />
    </div>
  );
}

function TaskCard({ t, done, onStep, busy, asOf }) {
  const kind = KIND[t.action] || { label: t.title, steps: [] };
  const next = kind.steps.find((s) => !done.includes(s));
  const finished = kind.steps.length > 0 && !next;
  return (
    <article className={`task tone-${kind.tone} ${finished ? "finished" : ""}`}>
      <header>
        <span className={`tag tag-${kind.tone}`}>{kind.label}</span>
        <strong>{t.product}</strong>
        <span className="mono">{t.batch_no}</span>
        {t.act_by && !finished && (
          <span className={`act-by ${t.act_by <= asOf ? "late" : ""}`}>
            {t.act_by <= asOf ? `Overdue since ${fmtDate(t.act_by)}` : `Act by ${fmtDate(t.act_by)}`}
          </span>
        )}
      </header>
      <div className="task-facts">
        <div><span>Packs</span><strong>{packs(t.qty)}</strong></div>
        <div><span>Value</span><strong>{inr(t.value_inr)}</strong></div>
        <div><span>Expires</span><strong>{fmtDate(t.expiry_date)}</strong></div>
        <div><span>Shelf life left</span><ShelfBar share={t.shelf_share} /><small>{Math.round(t.shelf_share * 100)}%</small></div>
      </div>
      <p className="task-why"><strong>Why:</strong> {t.why}.</p>
      <p className="task-do"><strong>What to do:</strong> {t.do}.</p>
      {t.takers?.length > 0 && (
        <div className="takers">
          Could sell it:{" "}
          {t.takers.map((k) => (
            <span key={k.cnf_code} className="tag">{k.cnf_city} · up to {packs(k.can_take)}</span>
          ))}
        </div>
      )}
      <div className="task-foot">
        <span className="clause">{t.clause}</span>
        <div className="steps">
          {kind.steps.map((s) =>
            done.includes(s) ? (
              <span key={s} className="step done">✓ {s}</span>
            ) : s === next ? (
              <button key={s} className="small" disabled={busy} onClick={() => onStep(t, s)}>
                {s}
                {STEP_WHO[s] && <span className="who"> · {STEP_WHO[s]}</span>}
              </button>
            ) : (
              <span key={s} className="step todo">{s}</span>
            ),
          )}
        </div>
      </div>
    </article>
  );
}

function PickOrder({ list, query }) {
  const q = query.trim().toLowerCase();
  const rows = list.filter((p) => !q || `${p.product} ${p.sku_code} ${p.batches.map((b) => b.batch_no).join(" ")}`.toLowerCase().includes(q));
  return (
    <div className="pick">
      {rows.map((p) => (
        <section key={p.sku_code} className="pick-row">
          <div className="pick-head">
            <strong>{p.product}</strong>
            <span className="hint">
              {packs(p.stock_packs)} packs · normal demand {packs(p.outward_per_month)} a month
              {p.cover_months != null && ` · ${p.cover_months} months of stock`}
            </span>
          </div>
          <ol className="pick-batches">
            {p.batches.map((b) => (
              <li key={b.batch_no} className={`pb pb-${b.status} ${b.pick_now ? "now" : ""}`}>
                <span className="pb-tag">{b.pick_now ? "Pick now" : STATUS_LABEL[b.status]}</span>
                {b.not_moving && <span className="pb-tag pb-still">not moving</span>}
                <span className="mono">{b.batch_no}</span>
                <span>exp {fmtDate(b.expiry_date)}</span>
                <span>{packs(b.qty)} packs</span>
              </li>
            ))}
          </ol>
        </section>
      ))}
      {!rows.length && <p className="hint">No product matches.</p>}
    </div>
  );
}

function BatchOrder({ fefo, city, actions, onRaise, busy }) {
  const months = Object.entries(fefo.share_by_month);
  const raised = actions.filter((a) => a.step === "Raised with CFA");
  return (
    <div className="fefo">
      <p className={fefo.alert ? "fefo-say alert" : "fefo-say"}>
        {fefo.alert ? "Alert: " : ""}
        In the last 3 months <strong>{Math.round(fefo.latest * 100)}%</strong> of packs shipped from {city} went out while an
        older batch of the same product was still there. The rule is oldest expiry first ({fefo.clause}); the alert line is{" "}
        {Math.round(fefo.threshold * 100)}%.
      </p>
      <div className="bars" role="img" aria-label="Share of packs that skipped an older batch, by month">
        {months.map(([m, v]) => (
          <div key={m} className="bar-col" title={`${m}: ${Math.round(v * 100)}%`}>
            <div className="bar-area">
              <div className={`bar ${v > fefo.threshold ? "over" : ""}`} style={{ height: `${Math.min(100, v * 100)}%` }} />
              <div className="bar-line" style={{ bottom: `${fefo.threshold * 100}%` }} />
            </div>
            <span>{new Date(`${m}-01`).toLocaleDateString("en-IN", { month: "short" })} {m.slice(2, 4)}</span>
            <span className="bar-pct">{Math.round(v * 100)}%</span>
          </div>
        ))}
      </div>
      {fefo.top_products.length > 0 && (
        <>
          <h4>Products most often picked out of order (last 3 months)</h4>
          <ul className="facts-list">
            {fefo.top_products.map((p) => (
              <li key={p.sku_code}>{p.product}: {packs(p.packs)} packs</li>
            ))}
          </ul>
        </>
      )}
      <div className="fefo-act">
        {raised.map((a, i) => (
          <span key={i} className="step done">✓ Raised with CFA by {a.by}, {fmtDate(a.at)}</span>
        ))}
        {fefo.alert && (
          <button className="small" disabled={busy} onClick={onRaise}>Raise with the CFA</button>
        )}
      </div>
      <Citations citations={fefo.citations} />
    </div>
  );
}

export default function StockDesk({ focus }) {
  const [overview, setOverview] = useState(null);
  const [cfa, setCfa] = useState(null);
  const [plan, setPlan] = useState(null);
  const [view, setView] = useState("todo");
  const [kind, setKind] = useState("all");
  const [query, setQuery] = useState("");
  const [name, setName] = useName();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [shortDated, setShortDated] = useState(null);

  const loadShortDated = () => api("/api/stock/short-dated").then(setShortDated).catch((e) => setError(e.message));
  useEffect(() => {
    loadShortDated();
  }, []);

  useEffect(() => {
    api("/api/stock/overview")
      .then((o) => {
        setOverview(o);
        setCfa((cur) => cur || o.cards[0]?.cnf_code);
      })
      .catch((e) => setError(e.message));
  }, []);

  useEffect(() => {
    const ref = focus?.ref || "";
    if (ref.startsWith("CF-")) {
      setCfa(ref);
      setView("todo");
    } else if (ref.startsWith("watch:")) {
      setCfa(ref.slice(6));
      setView("watch");
    } else if (ref.startsWith("short:")) {
      setCfa(ref.slice(6));
      setView("short");
    }
  }, [focus?.n]);

  const load = (code) =>
    api(`/api/stock/plan?cfa=${encodeURIComponent(code)}`)
      .then(setPlan)
      .catch((e) => setError(e.message));

  useEffect(() => {
    if (!cfa) return;
    setPlan(null);
    setKind("all");
    load(cfa);
  }, [cfa]);

  const doneFor = (t) => (plan?.actions || []).filter((a) => a.batch_no === t.batch_no && a.sku_code === t.sku_code).map((a) => a.step);

  const tasks = useMemo(() => (plan?.todo || []).filter((t) => kind === "all" || t.action === kind), [plan, kind]);
  const kindCounts = useMemo(() => {
    const n = {};
    for (const t of plan?.todo || []) n[t.action] = (n[t.action] || 0) + 1;
    return n;
  }, [plan]);
  const openCount = (plan?.todo || []).filter((t) => {
    const steps = KIND[t.action]?.steps || [];
    return steps.some((s) => !doneFor(t).includes(s));
  }).length;

  async function record(body) {
    if (name.trim().length < 2) {
      setError("Enter your name at the top first.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      await api("/api/stock/action", { ...body, by: name.trim() });
      await load(cfa);
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  const card = overview?.cards.find((c) => c.cnf_code === cfa);

  return (
    <section className="stockdesk">
      <div className="stock-intro">
        <div>
          <h2>Expiry and dispatch</h2>
          <p className="hint">
            Stock as of <strong>{overview ? fmtDate(overview.as_of) : "…"}</strong> (latest CFA snapshot). Pick a CFA to see what to
            block, what needs the stockist's agreement, what to send back through the CDC, and which batch to pick first.
          </p>
        </div>
        <label className="name-field">
          Your name
          <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Recorded with each action" />
        </label>
      </div>
      <details className="rules-box">
        <summary>The rules this follows</summary>
        <ul>
          <li><strong>Under 60 days to expiry:</strong> blocked, never picked, destroyed under witness (CO-POL-014 7.1, 7.2; CF Sch 2 2.3.4, 2.7).</li>
          <li><strong>Under 60% of shelf life left:</strong> a stockist may refuse it; bill only with their agreement (CO-POL-014 7.1).</li>
          <li><strong>Will not sell in time:</strong> at this CFA's normal monthly demand (from invoices; the SAP outward figure is not used), oldest batch first, part of the batch will still be here when it drops under 60%. A return goes to the CDC only if the batch keeps 60% shelf life after 14 days in transit and is worth at least ₹5 lakh; otherwise push it in dispatch (CF Sch 2 2.5; client, 22 Nov). This forecast is right about 84% of the time when it flags a batch, but misses many: backtest in the testing report.</li>
          <li><strong>Pick order:</strong> oldest expiry first; another batch only with a logged supervisor override (CF 6.3; Sch 2 2.3).</li>
        </ul>
      </details>

      {error && <p className="status error">{error}</p>}
      {!overview && !error && <div className="loading">Loading stock…</div>}

      <ShortDatedNational s={shortDated} />

      {overview && (
        <div className="cfa-grid">
          {overview.cards.map((c) => (
            <CfaCard key={c.cnf_code} c={c} active={c.cnf_code === cfa} onPick={setCfa} />
          ))}
        </div>
      )}

      {card && (
        <div className="cfa-work">
          <header className="cfa-work-head">
            <h3>{card.cnf_city} <span className="mono hint">{card.cnf_code}</span></h3>
            <div className="seg seg-inline" role="tablist">
              <button className={view === "todo" ? "on" : ""} onClick={() => setView("todo")}>
                To do <span className="count">{plan ? openCount : ""}</span>
              </button>
              <button className={view === "watch" ? "on" : ""} onClick={() => setView("watch")}>
                Not moving <span className="count">{plan ? plan.watch.length : ""}</span>
              </button>
              <button className={view === "short" ? "on" : ""} onClick={() => setView("short")}>
                Short-dated dispatches <span className="count">{shortDated?.cfas.find((c) => c.cnf_code === cfa)?.lines ?? ""}</span>
              </button>
              <button className={view === "pick" ? "on" : ""} onClick={() => setView("pick")}>Pick order</button>
              <button className={view === "fefo" ? "on" : ""} onClick={() => setView("fefo")}>
                Batch-order check {card.fefo_alert && <span className="dot" />}
              </button>
            </div>
          </header>

          {!plan && <div className="loading">Working out the plan for {card.cnf_city}…</div>}

          {plan && view === "todo" && (
            <>
              <div className="kind-filter">
                <button className={kind === "all" ? "chip on" : "chip"} onClick={() => setKind("all")}>All {plan.todo.length}</button>
                {Object.entries(KIND).map(([k, v]) =>
                  kindCounts[k] ? (
                    <button key={k} className={kind === k ? "chip on" : "chip"} onClick={() => setKind(k)}>
                      {v.label} {kindCounts[k]}
                    </button>
                  ) : null,
                )}
              </div>
              {!plan.todo.length && <p className="card">Nothing to do at {card.cnf_city}: every batch sells in time and none is short-dated.</p>}
              <div className="tasks">
                {tasks.map((t) => (
                  <TaskCard key={`${t.sku_code}-${t.batch_no}`} t={t} done={doneFor(t)} busy={busy} asOf={plan.as_of}
                    onStep={(task, step) => record({ cnf_code: cfa, sku_code: task.sku_code, batch_no: task.batch_no, qty: task.action === "cdc_return" ? task.return_qty : task.qty, step })} />
                ))}
              </div>
            </>
          )}

          {plan && view === "watch" && (
            <>
              <p className="hint watch-note">
                <strong>Watch list, not a forecast.</strong> Sellable batches at {card.cnf_city} that sold under 5% since{" "}
                {plan.watch_since ? fmtDate(plan.watch_since) : "the previous snapshot"}. {plan.watch_note}
              </p>
              {!plan.watch.length && <p className="card">Every sellable batch at {card.cnf_city} moved since the last snapshot.</p>}
              <div className="tasks">
                {plan.watch.map((w) => {
                  const done = (plan.actions || []).filter((a) => a.batch_no === w.batch_no && a.sku_code === w.sku_code).map((a) => a.step);
                  return (
                    <article key={`${w.sku_code}-${w.batch_no}`} className={`task ${w.pick_now ? "tone-warn" : "tone-info"}`}>
                      <header>
                        <span className={`tag ${w.pick_now ? "tag-warn" : "tag-info"}`}>{w.pick_now ? "Pick-first batch" : "Behind an older batch"}</span>
                        <strong>{w.product}</strong>
                        <span className="mono">{w.batch_no}</span>
                        {w.status === "at_risk" && <span className="tag tag-bad">also forecast to be left over</span>}
                      </header>
                      <div className="task-facts">
                        <div><span>Packs now</span><strong>{packs(w.qty)}</strong></div>
                        <div><span>At {fmtDate(plan.watch_since)}</span><strong>{packs(w.prev_qty)}</strong></div>
                        <div><span>Sold since</span><strong>{Math.max(0, Math.round((w.sold_share || 0) * 100))}%</strong></div>
                        <div><span>Value</span><strong>{inr(w.value_inr)}</strong></div>
                        <div><span>Shelf life left</span><ShelfBar share={w.shelf_share} /><small>{Math.round(w.shelf_share * 100)}%</small></div>
                      </div>
                      <p className="task-why"><strong>{w.title}:</strong> {w.why}.</p>
                      <p className="task-do"><strong>What to do:</strong> {w.do}.</p>
                      <div className="task-foot">
                        <span className="clause">{w.clause}</span>
                        <div className="steps">
                          {done.includes("Checked with CFA") ? (
                            <span className="step done">✓ Checked with CFA</span>
                          ) : (
                            <button className="small" disabled={busy}
                              onClick={() => record({ cnf_code: cfa, sku_code: w.sku_code, batch_no: w.batch_no, qty: w.qty, step: "Checked with CFA" })}>
                              Checked with CFA
                            </button>
                          )}
                        </div>
                      </div>
                    </article>
                  );
                })}
              </div>
            </>
          )}

          {view === "short" && (
            <ShortDatedCfa cfa={cfa} city={card.cnf_city} card={shortDated?.cfas.find((c) => c.cnf_code === cfa)}
              name={name.trim().length >= 2 ? name : ""} busy={busy}
              onRecord={async (body) => { await record(body); loadShortDated(); }} />
          )}

          {plan && view === "pick" && (
            <>
              <div className="pick-tools">
                <input type="search" className="search" placeholder="Find a product or batch" value={query} onChange={(e) => setQuery(e.target.value)} />
                <button className="secondary small" onClick={() => window.print()}>Print pick order</button>
                <button className="small" disabled={busy}
                  onClick={() => record({ cnf_code: cfa, step: "Picking order confirmed", note: `Pick order as of ${plan.as_of} sent to ${card.cnf_city}` })}>
                  Confirm sent to CFA
                </button>
              </div>
              {(plan.actions || []).filter((a) => a.step === "Picking order confirmed").slice(-1).map((a, i) => (
                <p key={i} className="hint">✓ Last sent by {a.by}, {fmtDate(a.at)}</p>
              ))}
              <PickOrder list={plan.pick_list} query={query} />
            </>
          )}

          {plan && view === "fefo" && (
            <BatchOrder fefo={plan.fefo} city={card.cnf_city} actions={plan.actions || []} busy={busy}
              onRaise={() => record({ cnf_code: cfa, step: "Raised with CFA", note: `${Math.round(plan.fefo.latest * 100)}% over 3 months` })} />
          )}

          {plan && <Citations citations={plan.citations} />}
        </div>
      )}
    </section>
  );
}
