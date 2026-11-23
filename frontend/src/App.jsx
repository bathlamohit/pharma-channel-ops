import { useState } from "react";
import AllocationDesk from "./components/AllocationDesk.jsx";
import ClaimsDesk from "./components/ClaimsDesk.jsx";
import DigestDesk from "./components/DigestDesk.jsx";
import StockDesk from "./components/StockDesk.jsx";

const TABS = [
  { id: "weekly", label: "Weekly digest", owner: "All owners" },
  { id: "claims", label: "Claims desk", owner: "Commercial Finance" },
  { id: "watch", label: "Expiry & dispatch", owner: "Supply Chain" },
  { id: "allocation", label: "Allocation", owner: "Demand Planning" },
];

export default function App() {
  const [tab, setTab] = useState("weekly");
  // A digest item opens the screen where the work is done, on the right CFA, claim or view.
  const [focus, setFocus] = useState(null);
  const current = TABS.find((t) => t.id === tab);

  function openFrom(target, ref) {
    setFocus({ tab: target, ref, n: Date.now() });
    setTab(target);
    window.scrollTo(0, 0);
  }
  const focusFor = (id) => (focus?.tab === id ? focus : null);

  return (
    <div className="shell wide">
      <header className="top">
        <div>
          <h1>Project Sankalp pilot</h1>
          <p className="hint">Every number cites its file and rows. A person signs every credit note.</p>
        </div>
        <span className="owner">{current.owner}</span>
      </header>

      <nav className="tabs" role="tablist">
        {TABS.map((t) => (
          <button
            key={t.id}
            role="tab"
            aria-selected={tab === t.id}
            className={tab === t.id ? "tab active" : "tab"}
            onClick={() => setTab(t.id)}
          >
            {t.label}
          </button>
        ))}
      </nav>

      {/* Keep each tab mounted so work in progress survives switching tabs. */}
      <div hidden={tab !== "weekly"}>
        <DigestDesk active={tab === "weekly"} onOpen={openFrom} />
      </div>
      <div hidden={tab !== "claims"}>
        <ClaimsDesk focus={focusFor("claims")} />
      </div>
      <div hidden={tab !== "watch"}>
        <StockDesk focus={focusFor("watch")} />
      </div>
      <div hidden={tab !== "allocation"}>
        <AllocationDesk focus={focusFor("allocation")} />
      </div>
    </div>
  );
}
