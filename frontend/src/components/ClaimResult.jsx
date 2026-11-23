import { useState } from "react";
import { ACTION_LABEL, CHECK_LABEL, inr, ROUTE_LABEL, ROUTE_SHORT } from "../api.js";
import Citations from "./Citations.jsx";
import ClaimStatus from "./ClaimStatus.jsx";
import DecisionBar from "./DecisionBar.jsx";

const BAD = ["fail", "flag"];
const OPEN = ["Received", "Awaiting info", "Verified", "On hold"];
const SRC = { email: "Email", register: "Register claim", new: "New claim", intake: "New claim" };

function Recommendation({ rec }) {
  if (!rec) return null;
  const credit = rec.action === "approve" || rec.action === "approve_part";
  return (
    <div className={`rec rec-${rec.action}`}>
      <div className="rec-main">
        <span className="rec-action">{ACTION_LABEL[rec.action] || rec.action}</span>
        {credit && (
          <span className="rec-money">
            {rec.qty} packs · <strong>{inr(rec.credit_inr)}</strong>
          </span>
        )}
        {rec.action === "review" && rec.credit_if_approved_inr != null && (
          <span className="rec-money">{inr(rec.credit_if_approved_inr)} if approved in full</span>
        )}
        <span className="codes">
          {rec.reason_codes?.map((c) => (
            <span key={c} className="code">{c}</span>
          ))}
        </span>
      </div>
      {rec.note && <p className="rec-note">{rec.note}</p>}
    </div>
  );
}

function LineCard({ line, index, total }) {
  const c = line.claim || {};
  const checks = Object.values(line.checks || {});
  const bad = checks.filter((r) => BAD.includes(r.outcome));
  const passed = checks.filter((r) => r.outcome === "pass").length;
  return (
    <article className={`line route-${line.route}`}>
      <header>
        {total > 1 && <span className="line-no">Line {index + 1}</span>}
        <strong className="line-product">{c.sku_text || c.sku_code || "Product not given"}</strong>
        <span className={`pill pill-${line.route}`}>{ROUTE_SHORT[line.route] || line.route}</span>
      </header>
      <dl className="facts">
        <div><dt>Batch</dt><dd className="mono">{c.batch_no || "not given"}</dd></div>
        <div><dt>Quantity</dt><dd>{c.qty_claimed ?? "not given"} packs</dd></div>
        <div><dt>Type</dt><dd>{c.claim_type || "n/a"}</dd></div>
        <div><dt>Invoice</dt><dd className="mono">{c.invoice_ref || "not given"}</dd></div>
      </dl>

      <Recommendation rec={line.recommendation} />

      {(bad.length > 0 || line.errors?.length > 0) && (
        <ul className="reasons">
          {line.errors?.map((e) => (
            <li key={e} className="reason-missing">{e}</li>
          ))}
          {bad.map((r) => (
            <li key={r.check} className={`reason-${r.outcome}`}>
              <span className="reason-check">{CHECK_LABEL[r.check] || r.check}</span>
              {r.detail}
              <span className="clause">{r.clause}</span>
            </li>
          ))}
        </ul>
      )}
      {checks.length > 0 && (
        <details className="all-checks">
          <summary>
            {passed} of {checks.length} checks passed · show all
          </summary>
          <table>
            <tbody>
              {checks.map((r) => (
                <tr key={r.check} className={r.outcome}>
                  <td>{CHECK_LABEL[r.check] || r.check}</td>
                  <td className="outcome">{r.outcome}</td>
                  <td>{r.detail}</td>
                  <td className="mono clause-cell">{r.clause}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </details>
      )}
    </article>
  );
}

function Letter({ text }) {
  const [copied, setCopied] = useState(false);
  async function copy() {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      setCopied(false);
    }
  }
  return (
    <section className="card letter">
      <header className="card-head">
        <h3>Draft to the stockist</h3>
        <button className="secondary small" onClick={copy}>{copied ? "Copied" : "Copy"}</button>
      </header>
      <pre className="reply">{text}</pre>
      <p className="hint">Check before sending. The tool never sends anything.</p>
    </section>
  );
}

function Intake({ item }) {
  const r = item.raw;
  const text = item.kind === "new" ? r.intake : r;
  return (
    <section className="card source">
      <header className="card-head">
        <h3>{text?.body ? "Email as received" : "Claim form"}</h3>
        <span className="hint">{item.date}</span>
      </header>
      <p className="email-meta">
        <strong>{item.who}</strong>
        {r.stockist_code ? <span className="mono"> · {r.stockist_code}</span> : <span className="tag tag-warn">account not known</span>}
      </p>
      {text?.subject && <p className="email-subject">{text.subject}</p>}
      {text?.body ? (
        <pre className="email-body">{text.body}</pre>
      ) : (
        <p className="hint">Entered from the stockist's claim form{r.by ? ` by ${r.by}` : ""}.</p>
      )}
    </section>
  );
}

function Source({ item }) {
  if (item.kind === "new" || item.kind === "intake") return <Intake item={item} />;
  const r = item.raw;
  if (item.kind === "email") {
    return (
      <section className="card source">
        <header className="card-head">
          <h3>Original email</h3>
          <span className="hint">{r.received_date}</span>
        </header>
        <p className="email-meta">
          <strong>{r.from_name || "Unknown sender"}</strong>
          {r.stockist_code_by_mailbox_rule ? (
            <span className="mono"> · {r.stockist_code_by_mailbox_rule}</span>
          ) : (
            <span className="tag tag-warn">not a registered mailbox</span>
          )}
        </p>
        <p className="email-subject">{r.subject}</p>
        <pre className="email-body">{r.body}</pre>
      </section>
    );
  }
  const rows = [
    ["Stockist", `${r.stockist_name} · ${r.stockist_code}`],
    ["Product", r.product],
    ["Batch", r.batch_no],
    ["Claim type", r.claim_type],
    ["Quantity", `${Number(r.qty_claimed)} packs`],
    ["Value claimed", r.claim_value_inr ? inr(Number(r.claim_value_inr)) : "blank"],
    ["Expiry as claimed", r.expiry_date_as_claimed || "blank"],
    ["Invoice", r.original_invoice_ref || "not given"],
    ["CFA", r.cnf_code],
    ["Lodged", r.claim_date],
  ];
  return (
    <section className="card source">
      <header className="card-head">
        <h3>Register entry</h3>
        <span className="hint">as lodged by the C&F</span>
      </header>
      <dl className="record">
        {rows.map(([k, v]) => (
          <div key={k}>
            <dt>{k}</dt>
            <dd>{v}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}

function Summary({ result, onOpenClaim }) {
  const lines = result.lines || [];
  const credit = lines.reduce(
    (s, l) => s + (["approve", "approve_part"].includes(l.recommendation?.action) ? l.recommendation.credit_inr || 0 : 0),
    0,
  );
  const atStake = lines.reduce((s, l) => s + (l.recommendation?.credit_if_approved_inr || 0), 0);
  const readBy = { rules: "Rules", model: "Model (fallback)", nobody: "Not read" }[result.read_by];
  return (
    <div className="summary">
      <div className={`stat stat-${result.route}`}>
        <span>Outcome</span>
        <strong>{ROUTE_LABEL[result.route] || result.route}</strong>
      </div>
      {lines.length > 0 && (credit > 0 || atStake === 0) && (
        <div className="stat">
          <span>Credit recommended</span>
          <strong>{inr(credit)}</strong>
        </div>
      )}
      {atStake > 0 && (
        <div className="stat">
          <span>Awaiting review</span>
          <strong>{inr(atStake)}</strong>
        </div>
      )}
      {lines.length > 0 && (
        <div className="stat">
          <span>Claim lines</span>
          <strong>{lines.length}</strong>
        </div>
      )}
      {result.registered?.length > 0 && (
        <div className="stat stat-logged">
          <span>Logged as</span>
          <strong className="logged">
            {result.registered.map((no) => (
              <button key={no} className="link mono" onClick={() => onOpenClaim?.(no)}>{no}</button>
            ))}
          </strong>
        </div>
      )}
      {result.read_by && (
        <div className="stat">
          <span>Read by</span>
          <strong>{readBy}</strong>
        </div>
      )}
    </div>
  );
}

export default function ClaimResult({ item, result, busy, error, onNext, onDecided, onStatusChanged, onOpenClaim }) {
  const lines = result?.lines || [];
  const isNew = item.kind === "new";
  const showDecision = lines.length > 0 && item.kind !== "intake" && (!isNew || OPEN.includes(item.raw.status));
  return (
    <article className="case">
      <header className="case-head">
        <div className="case-meta">
          <span className={`src src-${item.kind}`}>{SRC[item.kind]}</span>
          <span className="mono">{item.id}</span>
          <span className="hint">{item.date}</span>
        </div>
        <h2>{item.title}</h2>
        <p className="hint">{item.who}</p>
      </header>

      {busy && <div className="loading">Checking against CO-POL-014…</div>}
      {error && <p className="status error">Something went wrong: {error}</p>}

      {result && !busy && (
        <>
          <Summary result={result} onOpenClaim={onOpenClaim} />
          {result.errors?.length > 0 && <p className="warn notice">{result.errors.join("; ")}</p>}

          <div className="case-grid">
            <div className="case-main">
              {isNew && <ClaimStatus claim={item.raw} onChanged={onStatusChanged} />}
              {lines.map((line, i) => (
                <LineCard key={line.claim?.claim_no || i} line={line} index={i} total={lines.length} />
              ))}
              {item.kind === "intake" && result.registered?.length > 0 && (
                <p className="hint">Each line is now a claim in the inbox under New. Open it to record the CFA's verification and decide.</p>
              )}
              {!lines.length && result.explanation && <p className="card">{result.explanation}</p>}
              {result.status_facts?.length > 0 && (
                <section className="card">
                  <h3>{result.status_facts[0].startsWith("Forward to") ? "Routing" : "From the register"}</h3>
                  <ul className="facts-list">
                    {result.status_facts.map((f) => (
                      <li key={f} className={f.includes("over the") ? "overdue" : ""}>{f}</li>
                    ))}
                  </ul>
                </section>
              )}
              {result.reply && <Letter text={result.reply} />}
            </div>
            <div className="case-side">
              <Source item={item} />
              <Citations citations={result.citations} />
            </div>
          </div>

          {showDecision && (
            <DecisionBar
              auditId={result.audit_id}
              recommended={result.route}
              onNext={onNext}
              onDecided={onDecided}
              claimNo={isNew ? item.id : null}
              approveNeeds={isNew && !["Verified", "On hold"].includes(item.raw.status) ? "Approve after the CFA's physical verification (CO-POL-014 5.6)" : ""}
            />
          )}
        </>
      )}
    </article>
  );
}
