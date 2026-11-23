import { useEffect, useState } from "react";
import { api, isOverride } from "../api.js";

const NAME_KEY = "sankalp.decider";
const readName = () => {
  try {
    return localStorage.getItem(NAME_KEY) || "";
  } catch {
    return "";
  }
};

// The graph stops at a recommendation; a person's decision is a second request.
// Sticky at the bottom of the case so it is always in reach while reading.
export default function DecisionBar({ auditId, recommended, onNext, onDecided, claimNo, approveNeeds }) {
  const [who, setWho] = useState(readName);
  const [note, setNote] = useState("");
  const [saved, setSaved] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    setSaved(null);
    setError("");
    setNote("");
  }, [auditId, claimNo]);

  async function decide(decision) {
    if (who.trim().length < 2) {
      setError("Enter your name first.");
      return;
    }
    if (isOverride(recommended, decision) && note.trim().length < 10) {
      setError("This goes against the recommendation: give the reason (at least 10 characters).");
      return;
    }
    setError("");
    try {
      localStorage.setItem(NAME_KEY, who.trim());
    } catch {
      /* private window: the name is just not remembered */
    }
    try {
      const rec = await api("/api/decision", { audit_id: auditId, decided_by: who.trim(), decision, note, recommended, claim_no: claimNo || null });
      setSaved(rec);
      onDecided?.(rec.decision);
    } catch (err) {
      setError(err.message);
    }
  }

  if (saved) {
    return (
      <div className="decision done">
        <span>
          Recorded <strong>{saved.decision}</strong> by {saved.decided_by}
          {saved.override && " · override, reason logged"}
          {saved.stored === false && " · not stored on this server, keep a copy"}
        </span>
        {onNext && <button onClick={onNext}>Next item →</button>}
      </div>
    );
  }
  const settled = recommended === "already_decided";
  return (
    <div className="decision">
      <div className="decision-fields">
        <input aria-label="Your name" placeholder="Your name" value={who} onChange={(e) => {
          // Saved as typed: the status panel on a new claim uses the same name (QA D-05).
          setWho(e.target.value);
          try {
            localStorage.setItem(NAME_KEY, e.target.value.trim());
          } catch {
            /* private window: not remembered */
          }
        }} />
        <input
          aria-label="Reason"
          placeholder="Reason (required if you go against the recommendation)"
          value={note}
          onChange={(e) => setNote(e.target.value)}
        />
      </div>
      <div className="decision-actions">
        {!settled && (
          <button className="approve" disabled={Boolean(approveNeeds)} title={approveNeeds || undefined} onClick={() => decide("approve")}>
            Approve
          </button>
        )}
        <button className="reject" onClick={() => decide("reject")}>Reject</button>
        <button className="secondary" onClick={() => decide("hold")}>Hold</button>
      </div>
      {approveNeeds && <p className="hint decision-error">{approveNeeds}</p>}
      {error && <p className="error decision-error">{error}</p>}
    </div>
  );
}
