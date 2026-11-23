import { useState } from "react";
import { api } from "../api.js";

// Where a new claim is in CO-POL-014 5.6: logged, verified at the CFA (10 working days),
// decided, credit note (30 days), closed. Approve and reject go through the decision bar.
const MOVES = {
  Received: ["Verified", "Awaiting info", "On hold"],
  "Awaiting info": ["Received", "Verified", "On hold"],
  Verified: ["On hold"],
  "On hold": ["Received", "Verified"],
  Approved: ["Credit note raised"],
  "Credit note raised": ["Closed"],
  Rejected: ["Closed"],
  Closed: [],
};
const MOVE_LABEL = {
  Verified: "Mark verified at CFA",
  "Awaiting info": "Waiting for stockist",
  "On hold": "Put on hold",
  Received: "Info received",
  "Credit note raised": "Record credit note",
  Closed: "Close",
};

export default function ClaimStatus({ claim, onChanged }) {
  const [note, setNote] = useState("");
  const [cn, setCn] = useState("");
  const [error, setError] = useState("");
  const due = claim.due || {};
  const moves = MOVES[claim.status] || [];

  async function move(status) {
    let by = "";
    try {
      by = localStorage.getItem("sankalp.decider") || "";
    } catch {
      /* no storage */
    }
    if (by.length < 2) return setError("Enter your name in the decision bar first.");
    setError("");
    try {
      await api("/api/intake/status", { claim_no: claim.claim_no, status, by, note, credit_note_no: cn || null });
      setNote("");
      setCn("");
      onChanged();
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <section className="card status-card">
      <header className="card-head">
        <h3>Status: {claim.status}</h3>
        <span className="hint">{due.days_open} days since received</span>
      </header>
      <div className="due">
        <span className={due.verify_overdue ? "overdue" : ""}>Verify by {due.verify_by}{due.verify_overdue && " · overdue"}</span>
        <span className={due.credit_overdue ? "overdue" : ""}>Credit note by {due.credit_by}{due.credit_overdue && " · overdue"}</span>
      </div>
      <ol className="timeline">
        {claim.history.map((h, i) => (
          <li key={i}>
            <strong>{h.status}</strong> <span className="hint">{h.at?.slice(0, 16).replace("T", " ")} · {h.by}</span>
            {h.credit_note_no && <span className="mono"> · {h.credit_note_no}</span>}
            {h.override && <span className="tag tag-warn">override</span>}
            {h.note && <div className="hint">{h.note}</div>}
          </li>
        ))}
      </ol>
      {moves.length > 0 && (
        <div className="moves">
          <input placeholder="Note (e.g. packs counted at the CFA)" value={note} onChange={(e) => setNote(e.target.value)} />
          {moves.includes("Credit note raised") && (
            <input placeholder="Credit note number" value={cn} onChange={(e) => setCn(e.target.value)} />
          )}
          {moves.map((m) => (
            <button key={m} className="secondary small" onClick={() => move(m)}>{MOVE_LABEL[m] || m}</button>
          ))}
        </div>
      )}
      {error && <p className="error">{error}</p>}
    </section>
  );
}
