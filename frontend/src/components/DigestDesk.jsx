import { useEffect, useState } from "react";
import { api } from "../api.js";
import Citations from "./Citations.jsx";

// The weekly digest (ADR 0016): one section per owner with the figures that matter, the top
// things to do (each opens the screen where it is done) and what has been recorded as done.
// Built by code from the same plans as the work screens; no model. Copy gives an email text.

const fmtDate = (d) => new Date(d).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" });
const SCREEN = { claims: "Claims desk", watch: "Expiry & dispatch", allocation: "Allocation" };

function Section({ s, onOpen }) {
  return (
    <section className="digest-section">
      <header className="digest-head">
        <div>
          <h3>{s.title}</h3>
          <span className="owner">{s.owner}</span>
        </div>
        <button className="secondary small" onClick={() => onOpen(s.screen, null)}>Open {SCREEN[s.screen]} →</button>
      </header>
      {s.notice && (
        <p className="digest-notice">
          <strong>Restated.</strong> {s.notice.text}{" "}
          <button className="link" onClick={() => onOpen(s.notice.tab, s.notice.ref)}>What changed →</button>
        </p>
      )}
      <div className="summary">
        {s.stats.map((x) => (
          <div key={x.label} className={`stat ${x.tone === "bad" ? "stat-reject" : ""}`}>
            <span>{x.label}</span>
            <strong>{x.value}</strong>
            {x.sub && <small className="hint">{x.sub}</small>}
          </div>
        ))}
      </div>
      <div className="digest-cols">
        <div>
          <h4>To do</h4>
          {s.todo.length ? (
            <ol className="digest-todo">
              {s.todo.map((t, i) => (
                <li key={i}>
                  <button className="link digest-link" onClick={() => onOpen(t.tab, t.ref)}>{t.text}</button>
                </li>
              ))}
            </ol>
          ) : (
            <p className="hint">Nothing open.</p>
          )}
        </div>
        <div>
          <h4>Done</h4>
          {s.done.length ? (
            <ul className="digest-done">
              {s.done.map((d, i) => (
                <li key={i}>✓ {d.text} <span className="hint">· {d.by}, {fmtDate(d.at)}</span></li>
              ))}
            </ul>
          ) : (
            <p className="hint">Nothing recorded yet.</p>
          )}
        </div>
      </div>
      {s.citations && <Citations citations={s.citations} />}
    </section>
  );
}

export default function DigestDesk({ active, onOpen }) {
  const [d, setD] = useState(null);
  const [error, setError] = useState("");
  const [copied, setCopied] = useState(false);

  const load = () => api("/api/digest").then(setD).catch((e) => setError(e.message));
  // Refresh whenever the tab is shown, so work recorded on other screens appears under Done.
  useEffect(() => {
    if (active) load();
  }, [active]);

  async function copy() {
    try {
      await navigator.clipboard.writeText(d.text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      setError("Could not copy; select the text below instead.");
    }
  }

  return (
    <section className="stockdesk">
      <div className="stock-intro">
        <div>
          <h2>Weekly digest</h2>
          <p className="hint">
            Stock and claims register as of <strong>{d ? fmtDate(d.as_of) : "…"}</strong>. One section per owner: the figures that
            matter, the top things to do and what has been done. Click a to-do to open it where the work is done.
          </p>
        </div>
        {d && (
          <div className="row">
            <button className="secondary small" onClick={() => window.print()}>Print</button>
            <button className="small" onClick={copy}>{copied ? "Copied" : "Copy as email text"}</button>
          </div>
        )}
      </div>
      {error && <p className="status error">{error}</p>}
      {!d && !error && <div className="loading">Putting the week together…</div>}
      {d?.sections.map((s) => <Section key={s.title} s={s} onOpen={onOpen} />)}
      {d && (
        <details className="rules-box">
          <summary>Email text (what Copy puts on the clipboard)</summary>
          <pre className="reply">{d.text}</pre>
        </details>
      )}
    </section>
  );
}
