import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, ROUTE_SHORT } from "../api.js";
import ClaimResult from "./ClaimResult.jsx";
import NewClaim from "./NewClaim.jsx";

// One inbox for the claims desk. New claims (logged here, ADR 0013), mailbox emails and pending
// register claims are sources of the same work, so they sit in one list. Opening an email or
// register claim checks it (rules only, no model); a new claim shows its stored check and status.
const FILTERS = [
  { id: "all", label: "All" },
  { id: "new", label: "New" },
  { id: "email", label: "Mailbox" },
  { id: "register", label: "Register" },
];
const SRC_LABEL = { new: "New", email: "Email", register: "Register", intake: "New" };
const PAGE = 60;

function toItems(emails, claims) {
  const mail = emails.map((e) => ({
    kind: "email",
    id: e.email_id,
    title: e.subject || "(no subject)",
    who: e.from_name || "Unknown sender",
    date: e.received_date,
    preview: (e.body || "").replace(/\s+/g, " ").slice(0, 110),
    unverified: !e.stockist_code_by_mailbox_rule,
    raw: e,
  }));
  const reg = claims.map((c) => ({
    kind: "register",
    id: c.claim_no,
    title: c.product || c.sku_code,
    who: c.stockist_name || c.stockist_code,
    date: c.claim_date,
    preview: `${c.claim_type} · batch ${c.batch_no} · ${Number(c.qty_claimed)} packs`,
    raw: c,
  }));
  return [...mail, ...reg];
}

function newItems(stored, names) {
  return stored.map((c) => ({
    kind: "new",
    id: c.claim_no,
    title: c.sku_text || (c.batch_no ? `Batch ${c.batch_no}` : "Claim line"),
    who: names[c.stockist_code] || c.intake?.from_name || "Unknown sender",
    date: c.claim_date,
    preview: `${c.claim_type || "Type from expiry"} · batch ${c.batch_no || "not given"} · ${c.qty_claimed ?? "?"} packs`,
    unverified: !c.stockist_code,
    overdue: c.due?.verify_overdue || c.due?.credit_overdue,
    raw: c,
  }));
}

// A stored new claim shown with the same case view as a fresh check.
export function storedToResult(c) {
  return {
    route: c.route,
    audit_id: c.audit_id,
    read_by: c.source === "email" ? "rules" : undefined,
    citations: [],
    lines: [{ claim: { ...c }, checks: c.checks || {}, route: c.route, errors: c.errors || [], recommendation: c.recommendation }],
  };
}

function InboxItem({ item, active, result, decided, onOpen }) {
  const route = result?.route;
  return (
    <li>
      <button className={`item ${active ? "active" : ""}`} onClick={() => onOpen(item)} aria-current={active}>
        <div className="item-top">
          <span className={`src src-${item.kind}`}>{SRC_LABEL[item.kind]}</span>
          <span className="item-who">{item.who}</span>
          <span className="item-date">{item.date?.slice(5)}</span>
        </div>
        <div className="item-title">{item.title}</div>
        <div className="item-preview">{item.preview}</div>
        <div className="item-foot">
          <span className="mono">{item.id}</span>
          {item.unverified && <span className="tag tag-warn">sender not verified</span>}
          {item.kind === "new" && <span className={`tag status-tag`}>{item.raw.status}</span>}
          {item.overdue && <span className="tag tag-bad">overdue</span>}
          {item.kind !== "new" &&
            (decided ? (
              <span className={`tag decided decided-${decided}`}>✓ {decided}</span>
            ) : (
              route && <span className={`tag route-tag-${route}`}>{ROUTE_SHORT[route] || route}</span>
            ))}
        </div>
      </button>
    </li>
  );
}

export default function ClaimsDesk({ focus }) {
  const [base, setBase] = useState([]);
  const [stored, setStored] = useState([]);
  const [stockists, setStockists] = useState([]);
  const [filter, setFilter] = useState("all");
  const [query, setQuery] = useState("");
  const [shown, setShown] = useState(PAGE);
  const [selected, setSelected] = useState(null);
  const [results, setResults] = useState({});
  const [busy, setBusy] = useState(null);
  const [decided, setDecided] = useState({});
  const [error, setError] = useState("");
  const detailRef = useRef(null);

  const refreshStored = useCallback(
    () => api("/api/intake").then((s) => {
      setStored(s);
      return s;
    }),
    [],
  );

  useEffect(() => {
    Promise.all([api("/api/emails"), api("/api/claims?status=Pending&limit=400"), api("/api/stockists"), refreshStored()])
      .then(([e, c, s]) => {
        setBase(toItems(e, c));
        setStockists(s);
      })
      .catch((err) => setError(`Could not load the inbox: ${err.message}`));
  }, [refreshStored]);

  const names = useMemo(() => Object.fromEntries(stockists.map((s) => [s.stockist_code, s.stockist_name])), [stockists]);
  const items = useMemo(() => [...newItems(stored, names), ...base], [stored, names, base]);

  const counts = useMemo(() => {
    const n = { all: items.length };
    for (const f of ["new", "email", "register"]) n[f] = items.filter((i) => i.kind === f).length;
    return n;
  }, [items]);

  const visible = useMemo(() => {
    const q = query.trim().toLowerCase();
    return items.filter(
      (i) =>
        (filter === "all" || i.kind === filter) &&
        (!q || [i.id, i.title, i.who, i.preview, i.raw.batch_no, i.raw.stockist_code].join(" ").toLowerCase().includes(q)),
    );
  }, [items, filter, query]);

  function focusDetail() {
    if (window.matchMedia("(max-width: 860px)").matches) {
      setTimeout(() => detailRef.current?.scrollIntoView({ behavior: "smooth" }), 0);
    }
  }

  async function open(item) {
    setSelected(item);
    setError("");
    focusDetail();
    if (item.kind === "new" || results[item.id]) return;
    setBusy(item.id);
    try {
      const out =
        item.kind === "email"
          ? await api("/api/claim/email", { email_id: item.id })
          : await api("/api/claim/register", { claim_no: item.id });
      setResults((r) => ({ ...r, [item.id]: out }));
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(null);
    }
  }

  // Opened from the digest on a claim: find it in the inbox and open it.
  useEffect(() => {
    const ref = focus?.ref;
    if (!ref || !items.length) return;
    const hit = items.find((i) => i.id === ref);
    setFilter("all");
    setQuery(ref);
    if (hit) open(hit);
  }, [focus?.n, items.length > 0]);

  function step(delta) {
    if (!visible.length) return;
    const i = selected ? visible.findIndex((v) => v.id === selected.id) : -1;
    const next = visible[Math.min(visible.length - 1, Math.max(0, i + delta))];
    if (next && next.id !== selected?.id) open(next);
  }

  async function storedChanged() {
    const s = await refreshStored();
    setSelected((cur) => {
      if (cur?.kind !== "new") return cur;
      const fresh = s.find((c) => c.claim_no === cur.id);
      return fresh ? { ...cur, raw: fresh } : cur;
    });
  }

  function intakeDone(out, item) {
    const key = `intake:${item.id}`;
    setResults((r) => ({ ...r, [key]: out }));
    setSelected({ ...item, key });
    refreshStored();
  }

  const selectedResult =
    selected?.kind === "new" ? storedToResult(selected.raw) : selected ? results[selected.key || selected.id] : null;

  return (
    <section className={`desk ${selected ? "has-selection" : ""}`}>
      <aside className="inbox" aria-label="Claims inbox">
        <div className="inbox-head">
          <button className="new-btn" onClick={() => { setSelected({ kind: "compose", id: "compose" }); focusDetail(); }}>
            + New claim
          </button>
          <div className="seg" role="tablist" aria-label="Source">
            {FILTERS.map((f) => (
              <button
                key={f.id}
                role="tab"
                aria-selected={filter === f.id}
                className={filter === f.id ? "on" : ""}
                onClick={() => {
                  setFilter(f.id);
                  setShown(PAGE);
                }}
              >
                {f.label} <span className="count">{counts[f.id]}</span>
              </button>
            ))}
          </div>
          <input
            type="search"
            className="search"
            placeholder="Search stockist, batch, claim or email id"
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setShown(PAGE);
            }}
            onKeyDown={(e) => {
              if (e.key === "ArrowDown") {
                e.preventDefault();
                step(1);
              }
              if (e.key === "ArrowUp") {
                e.preventDefault();
                step(-1);
              }
            }}
          />
        </div>
        {error && !selected && <p className="status error">{error}</p>}
        <ul className="list">
          {visible.slice(0, shown).map((i) => (
            <InboxItem key={`${i.kind}:${i.id}`} item={i} active={selected?.id === i.id && selected?.kind === i.kind}
              result={results[i.id]} decided={decided[i.id]} onOpen={open} />
          ))}
          {!visible.length && items.length > 0 && (
            <li className="empty-list">{query ? `Nothing matches “${query}”.` : "No new claims yet. Use + New claim."}</li>
          )}
        </ul>
        {visible.length > shown && (
          <button className="secondary more" onClick={() => setShown(shown + PAGE)}>
            Show more ({visible.length - shown} left)
          </button>
        )}
      </aside>

      <div className="detail" ref={detailRef}>
        {!selected && (
          <div className="placeholder">
            <h2>Pick an item, or log a new claim</h2>
            <p className="hint">
              Opening an item checks it against CO-POL-014 section 5: eight rules, run as code. You see the
              recommendation, the reasons with clauses, and a draft to the stockist. A person decides.
            </p>
            <p className="hint">Tip: in the search box, ↑ and ↓ move through the list.</p>
          </div>
        )}
        {selected && (
          <button className="back secondary" onClick={() => setSelected(null)}>
            ← Inbox
          </button>
        )}
        {selected?.kind === "compose" && <NewClaim stockists={stockists} onDone={intakeDone} />}
        {selected && selected.kind !== "compose" && (
          <ClaimResult
            item={selected}
            result={selectedResult}
            busy={busy === selected.id}
            error={busy ? "" : error}
            onNext={() => step(1)}
            onDecided={(d) => (selected.kind === "new" ? storedChanged() : setDecided((m) => ({ ...m, [selected.id]: d })))}
            onStatusChanged={storedChanged}
            onOpenClaim={async (no) => {
              // The list may still be refreshing after a new claim is logged (QA D-06): refresh, then open.
              let list = stored;
              if (!list.some((c) => c.claim_no === no)) list = await refreshStored();
              const target = newItems(list, names).find((n) => n.id === no);
              if (target) open(target);
              else setError(`${no} is not in the list yet; try again in a moment.`);
            }}
          />
        )}
      </div>
    </section>
  );
}
