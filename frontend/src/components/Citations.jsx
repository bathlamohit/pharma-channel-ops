import { useState } from "react";
import SourceRows from "./SourceRows.jsx";

const SHOWN = 12;

export default function Citations({ citations }) {
  const [open, setOpen] = useState(null);
  if (!citations?.length) return null;
  return (
    <details className="sources">
      <summary>Sources ({citations.length})</summary>
      <ul>
        {citations.map((c, i) => (
          <li key={`${c.file}-${i}`}>
            <span className="mono">{c.file}</span> lines {c.rows.slice(0, SHOWN).join(", ")}
            {c.rows.length > SHOWN && ` … (${c.rows.length} rows)`} · snapshot {c.snapshot}{" "}
            <button className="link" onClick={() => setOpen(open === i ? null : i)}>
              {open === i ? "Hide rows" : "Show rows"}
            </button>
            {open === i && <SourceRows citation={c} />}
          </li>
        ))}
      </ul>
    </details>
  );
}
