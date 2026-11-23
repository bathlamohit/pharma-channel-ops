import { useState } from "react";
import { api } from "../api.js";

// A new claim enters in one of two ways: an email that arrived in the claims mailbox, or the
// stockist's claim form typed in by the desk or C&F (CO-POL-014 5.3). Either way it is checked
// at once, logged with a claim number, and an acknowledgement is drafted.
const TYPES = ["", "Near expiry", "Expired", "Breakage in transit", "Short supply"];
const EMPTY_LINE = { sku_text: "", batch_no: "", qty_claimed: "", claim_type: "", invoice_ref: "", expiry_text: "" };
// Local date (QA D-07): toISOString() is UTC, a day behind in India before 05:30.
const today = () => {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
};

function StockistPicker({ stockists, value, onChange, optional }) {
  return (
    <>
      <input
        list="stockist-list"
        placeholder={optional ? "Stockist account of the mailbox (leave blank if unknown)" : "Stockist code or name"}
        value={value}
        onChange={(e) => {
          const v = e.target.value;
          const hit = stockists.find((s) => v === `${s.stockist_code} · ${s.stockist_name}` || v.toUpperCase() === s.stockist_code);
          onChange(v, hit?.stockist_code || "");
        }}
      />
      <datalist id="stockist-list">
        {stockists.map((s) => (
          <option key={s.stockist_code} value={`${s.stockist_code} · ${s.stockist_name}`}>{s.city}</option>
        ))}
      </datalist>
    </>
  );
}

export default function NewClaim({ stockists, onDone }) {
  const [mode, setMode] = useState("email");
  const [stkText, setStkText] = useState("");
  const [stk, setStk] = useState("");
  const [date, setDate] = useState(today());
  const [fromName, setFromName] = useState("");
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  const [lines, setLines] = useState([{ ...EMPTY_LINE }]);
  const [by, setBy] = useState(() => {
    try {
      return localStorage.getItem("sankalp.decider") || "";
    } catch {
      return "";
    }
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const setLine = (i, k, v) => setLines(lines.map((l, j) => (j === i ? { ...l, [k]: v } : l)));

  async function submit(e) {
    e.preventDefault();
    setError("");
    if (stkText && !stk) return setError("Pick the stockist from the list, or clear the field.");
    if (mode === "form" && !stk) return setError("Pick the stockist whose claim form this is.");
    if (mode === "form" && by.trim().length < 2) return setError("Enter your name.");
    if (mode === "email" && !body.trim()) return setError("Paste the email text.");
    setBusy(true);
    try {
      const out =
        mode === "email"
          ? await api("/api/intake/email", {
              stockist_code: stk || null,
              from_name: fromName,
              subject,
              body,
              received_date: date,
            })
          : await api("/api/intake/form", {
              stockist_code: stk,
              received_date: date,
              entered_by: by.trim(),
              lines: lines
                .filter((l) => Object.values(l).some((v) => String(v).trim()))
                .map((l) => ({ ...l, qty_claimed: l.qty_claimed === "" ? null : Number(l.qty_claimed), claim_type: l.claim_type || null })),
            });
      onDone(out, {
        kind: "intake",
        id: out.registered?.[0] || "New claim",
        title: mode === "email" ? subject || "New email" : "Claim form",
        who: stockists.find((s) => s.stockist_code === stk)?.stockist_name || fromName || "Unknown sender",
        date,
        raw: { mode, subject, body, from_name: fromName, stockist_code: stk },
      });
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="case new-claim" onSubmit={submit}>
      <header className="case-head">
        <h2>New claim</h2>
        <p className="hint">
          Checked at once against CO-POL-014 section 5, logged with a claim number (CLM-yymm-nnnnn) and acknowledged.
          Nothing is approved here.
        </p>
      </header>
      <div className="seg seg-inline" role="tablist">
        <button type="button" className={mode === "email" ? "on" : ""} onClick={() => setMode("email")}>Paste an email</button>
        <button type="button" className={mode === "form" ? "on" : ""} onClick={() => setMode("form")}>Enter a claim form</button>
      </div>

      <section className="card form-grid">
        <label>
          {mode === "email" ? "Mailbox account" : "Stockist"}
          <StockistPicker stockists={stockists} value={stkText} optional={mode === "email"}
            onChange={(text, code) => { setStkText(text); setStk(code); }} />
          {mode === "email" && (
            <span className="hint">The account is taken from the mailbox the email came to, never from what the email says.</span>
          )}
        </label>
        <label>
          Received on
          <input type="date" value={date} max={today()} onChange={(e) => setDate(e.target.value)} />
        </label>
        {mode === "email" ? (
          <>
            <label>
              Sender name
              <input value={fromName} onChange={(e) => setFromName(e.target.value)} placeholder="As shown in the email" />
            </label>
            <label>
              Subject
              <input value={subject} onChange={(e) => setSubject(e.target.value)} />
            </label>
            <label className="span-2">
              Email text
              <textarea rows={9} value={body} onChange={(e) => setBody(e.target.value)}
                placeholder="Paste the email body. Batch, quantity, expiry and invoice are read by rules." />
            </label>
          </>
        ) : (
          <>
            <label>
              Entered by
              <input value={by} onChange={(e) => setBy(e.target.value)} placeholder="Your name" />
            </label>
            <div className="span-2">
              <div className="form-lines">
                <div className="form-line head">
                  <span>Product</span><span>Batch</span><span>Packs</span><span>Type</span><span>Invoice</span><span>Expiry</span><span />
                </div>
                {lines.map((l, i) => (
                  <div className="form-line" key={i}>
                    <input aria-label="Product" value={l.sku_text} onChange={(e) => setLine(i, "sku_text", e.target.value)} />
                    <input aria-label="Batch" value={l.batch_no} onChange={(e) => setLine(i, "batch_no", e.target.value)} placeholder="K2430146" />
                    <input aria-label="Packs" type="number" min="1" step="1" value={l.qty_claimed} onChange={(e) => setLine(i, "qty_claimed", e.target.value)} />
                    <select aria-label="Type" value={l.claim_type} onChange={(e) => setLine(i, "claim_type", e.target.value)}>
                      {TYPES.map((t) => <option key={t} value={t}>{t || "From expiry"}</option>)}
                    </select>
                    <input aria-label="Invoice" value={l.invoice_ref} onChange={(e) => setLine(i, "invoice_ref", e.target.value)} placeholder="INV/S01/2502/029631" />
                    <input aria-label="Expiry" value={l.expiry_text} onChange={(e) => setLine(i, "expiry_text", e.target.value)} placeholder="Oct-26" />
                    <button type="button" className="secondary small" aria-label="Remove line" disabled={lines.length === 1}
                      onClick={() => setLines(lines.filter((_, j) => j !== i))}>×</button>
                  </div>
                ))}
              </div>
              <button type="button" className="secondary small" onClick={() => setLines([...lines, { ...EMPTY_LINE }])}>+ Add line</button>
              <p className="hint">Leave the type on “From expiry” for expiry claims: near expiry or expired is set from the batch master.</p>
            </div>
          </>
        )}
      </section>
      {error && <p className="error">{error}</p>}
      <div className="row">
        <button type="submit" disabled={busy}>{busy ? "Checking…" : "Check and log claim"}</button>
      </div>
    </form>
  );
}
