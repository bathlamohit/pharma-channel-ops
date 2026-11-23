import { useEffect, useState } from "react";
import { api, inr, inrShort } from "../api.js";
import Citations from "./Citations.jsx";

// Dispatches under 60% shelf life (plan step 4). CO-POL-014 7.1: no approved exceptions, so every one
// is flagged; not blocked, it may go with the stockist's agreement. Where it piles up, and why.

const REASON_TONE = {
  arrived_old: "warn",
  too_much: "info",
  out_of_order: "bad",
  scheme: "info",
  none: "",
};
const fmtDate = (d) => new Date(d).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" });
const packs = (n) => Number(n).toLocaleString("en-IN");

function ReasonBars({ reasons, total }) {
  return (
    <div className="reason-bars">
      {reasons.filter((r) => r.lines).map((r) => (
        <div key={r.reason} className="reason-bar">
          <span className="q-label">{r.label}</span>
          <div className="q-track"><div className={`q-fill tone-${REASON_TONE[r.reason]}`} style={{ width: `${(r.value_inr / total) * 100}%` }} /></div>
          <span className="q-val">{inrShort(r.value_inr)} · {r.lines} lines</span>
        </div>
      ))}
    </div>
  );
}

export function ShortDatedNational({ s }) {
  if (!s) return null;
  return (
    <details className="rules-box short-dated-national">
      <summary>
        <strong>Dispatched under 60% shelf life, last four quarters: {inrShort(s.value_inr)}</strong> · {packs(s.lines)} invoice
        lines · {s.stockists} stockists · {s.batches} batches · where it piles up, and why
      </summary>
      <p className="hint">{s.rule} {s.under_60_days === 0 && "None went out with under 60 days to expiry."}</p>
      <h4>Why (a line can have more than one reason)</h4>
      <ReasonBars reasons={s.reasons} total={s.value_inr} />
      <p className="hint">{s.reason_note}</p>
      <div className="sd-grid">
        <section>
          <h4>By C&F</h4>
          <table>
            <thead><tr><th>C&F</th><th>Value</th><th>Of its dispatch</th><th>Main reason</th></tr></thead>
            <tbody>
              {s.cfas.map((c) => (
                <tr key={c.cnf_code}><td>{c.cnf_city}</td><td>{inrShort(c.value_inr)}</td><td>{(c.share_of_dispatch * 100).toFixed(1)}%</td>
                  <td>{c.main_reason} ({Math.round(c.main_reason_share * 100)}%)</td></tr>
              ))}
            </tbody>
          </table>
        </section>
        <section>
          <h4>Batches it came from</h4>
          <table>
            <thead><tr><th>Batch</th><th>C&F</th><th>Value</th><th>Shelf life when first seen</th></tr></thead>
            <tbody>
              {s.batches_top.map((b) => (
                <tr key={`${b.cnf_code}-${b.batch_no}`}><td><span className="mono">{b.batch_no}</span> {b.product_description}</td><td>{b.cnf_city}</td>
                  <td>{inrShort(b.value_inr)}</td><td>{Math.round(b.share_first_seen * 100)}%</td></tr>
              ))}
            </tbody>
          </table>
        </section>
        <section>
          <h4>Stockists who received most</h4>
          <table>
            <thead><tr><th>Stockist</th><th>Lines</th><th>Value</th><th>Later claimed</th></tr></thead>
            <tbody>
              {s.stockists_top.map((r) => (
                <tr key={`${r.stockist_code}-${r.cnf_code}`}><td>{r.stockist_name}</td><td>{r.lines}</td><td>{inrShort(r.value_inr)}</td>
                  <td>{r.claimed ? `${r.claimed} lines` : "–"}</td></tr>
              ))}
            </tbody>
          </table>
        </section>
      </div>
      <p className="hint">
        So far, dispatches worth {inrShort(s.claimed_later_value_inr)} went to stockists who later claimed the same batch as expiry.
        Consent recorded:{" "}
        {s.consent.agreed} agreed, {s.consent.no_agreement} with no agreement on record.
      </p>
    </details>
  );
}

export function ShortDatedCfa({ cfa, city, card, name, onRecord, busy }) {
  const [reason, setReason] = useState("");
  const [offset, setOffset] = useState(0);
  const [data, setData] = useState(null);
  const [error, setError] = useState("");

  const load = () =>
    api(`/api/stock/short-dated/lines?cfa=${encodeURIComponent(cfa)}&offset=${offset}${reason ? `&reason=${reason}` : ""}`)
      .then(setData).catch((e) => setError(e.message));
  useEffect(() => {
    setData(null);
    load();
  }, [cfa, reason, offset]);

  async function step(r, s) {
    await onRecord({ cnf_code: cfa, sku_code: r.sku_code, batch_no: r.batch_no, qty: r.packs, step: s, note: `Invoice ${r.invoice_no}` });
    load();
  }
  const doneFor = (r) => (data?.actions || []).filter((a) => a.batch_no === r.batch_no && a.note === `Invoice ${r.invoice_no}`).map((a) => a.step);

  return (
    <div className="short-dated">
      {card && (
        <>
          <p className="hint watch-note">
            <strong>{city}: {inrShort(card.value_inr)} billed under 60% shelf life</strong> in the last four quarters, {(card.share_of_dispatch * 100).toFixed(1)}% of
            what it dispatched, to {card.stockists} stockists from {card.batches} batches. Main reason: <strong>{card.main_reason}</strong>{" "}
            ({Math.round(card.main_reason_share * 100)}% of the value). Each line is flagged; record whether the stockist agreed (CO-POL-014 7.1).
          </p>
          <ReasonBars reasons={card.reasons} total={card.value_inr} />
        </>
      )}
      <div className="kind-filter">
        <button className={!reason ? "chip on" : "chip"} onClick={() => { setReason(""); setOffset(0); }}>All {card?.lines}</button>
        {card?.reasons.filter((r) => r.lines).map((r) => (
          <button key={r.reason} className={reason === r.reason ? "chip on" : "chip"} onClick={() => { setReason(r.reason); setOffset(0); }}>
            {r.label} {r.lines}
          </button>
        ))}
      </div>
      {error && <p className="error">{error}</p>}
      {!data && !error && <div className="loading">Loading dispatches…</div>}
      {data && (
        <>
          <div className="scroll">
            <table className="sd-lines">
              <thead><tr><th>Date</th><th>Invoice</th><th>Stockist</th><th>Product / batch</th><th>Packs</th><th>Value</th><th>Shelf left</th><th>Why</th><th>Stockist agreed?</th></tr></thead>
              <tbody>
                {data.rows.map((r) => {
                  const done = doneFor(r);
                  return (
                    <tr key={`${r.invoice_no}-${r.batch_no}-${r.src_line}`}>
                      <td>{fmtDate(r.invoice_date)}</td><td className="mono">{r.invoice_no}</td><td>{r.stockist_name}</td>
                      <td>{r.product}<br /><span className="mono hint">{r.batch_no}</span></td>
                      <td>{packs(r.packs)}</td><td>{inr(r.value_inr)}</td><td>{Math.round(r.shelf_share * 100)}%</td>
                      <td>{r.reasons.map((x) => <span key={x} className="tag reason-tag">{x}</span>)}{r.claimed_later && <span className="tag tag-bad">claimed later</span>}</td>
                      <td>
                        {done.length ? <span className="step done">✓ {done[done.length - 1]}</span> : (
                          <div className="steps">
                            <button className="small" disabled={busy || !name} onClick={() => step(r, "Stockist agreed")}>Agreed</button>
                            <button className="small secondary" disabled={busy || !name} onClick={() => step(r, "No agreement on record")}>No agreement</button>
                          </div>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <div className="pager">
            <span className="hint">{data.offset + 1}–{Math.min(data.offset + 50, data.total)} of {data.total}</span>
            <button className="secondary small" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - 50))}>Previous</button>
            <button className="secondary small" disabled={offset + 50 >= data.total} onClick={() => setOffset(offset + 50)}>Next</button>
          </div>
          {!name && <p className="hint">Enter your name at the top to record consent.</p>}
          <Citations citations={data.citations} />
        </>
      )}
    </div>
  );
}
