import { useEffect, useState } from "react";
import { api } from "../api.js";

// The rows a citation points at, as they are after cleaning. A cell the build changed is
// marked; its original value is listed under the table. Server text is shown as text only.
export default function SourceRows({ citation }) {
  const [offset, setOffset] = useState(0);
  const [data, setData] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let live = true;
    setError("");
    api("/api/source", { file: citation.file, rows: citation.rows, offset })
      .then((d) => live && setData(d))
      .catch((e) => live && setError(e.message));
    return () => { live = false; };
  }, [citation, offset]);

  if (error) return <p className="error">{error}</p>;
  if (!data) return <p className="status">Loading rows…</p>;

  const cols = data.columns;
  const changed = (line, col) => (data.fixes[line] || []).find((f) => f.field === col);
  const fixList = Object.entries(data.fixes).flatMap(([line, fs]) => fs.map((f) => ({ line, ...f })));
  const end = data.offset + data.rows.length + data.missing.length;
  const page = 50;

  return (
    <div className="source-rows">
      <p className="hint">
        {data.file} · rows {data.offset + 1}–{end} of {data.total}
        {data.total > page && (
          <span className="pager">
            <button className="secondary small" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - page))}>Previous</button>
            <button className="secondary small" disabled={end >= data.total} onClick={() => setOffset(offset + page)}>Next</button>
          </span>
        )}
      </p>
      <div className="scroll">
        <table>
          <thead>
            <tr>{cols.map((c) => <th key={c}>{c === "src_line" ? "line" : c}</th>)}</tr>
          </thead>
          <tbody>
            {data.rows.map((r) => (
              <tr key={r.src_line}>
                {cols.map((c) => {
                  const f = changed(r.src_line, c);
                  const v = r[c] ?? "";
                  return (
                    <td key={c} className={`${f ? "fixed" : ""} ${String(v).length > 60 ? "long" : ""}`}
                        title={f ? `Was "${f.before}" (${f.fix})` : String(v)}>
                      {v}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {data.missing.length > 0 && (
        <p className="hint warn">Lines {data.missing.join(", ")} were dropped in cleaning (exact duplicates).</p>
      )}
      {fixList.length > 0 && (
        <details>
          <summary>Changed in cleaning ({fixList.length})</summary>
          <ul className="fixes">
            {fixList.map((f, i) => (
              <li key={i}>
                line {f.line}, {f.field}: <span className="mono">"{f.before}"</span> → <span className="mono">"{f.after}"</span> ({f.fix})
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}
