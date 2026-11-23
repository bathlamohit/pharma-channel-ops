// Same origin as FastAPI (or proxied by Vite in dev), so no CORS setup is needed.
export async function api(path, body) {
  const res = await fetch(
    path,
    body === undefined
      ? undefined
      : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) },
  );
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = Array.isArray(data.detail) ? data.detail.map((d) => `${d.loc?.at(-1)}: ${d.msg}`).join("; ") : data.detail;
    throw new Error(data.error || detail || `Server returned ${res.status}`);
  }
  return data;
}

export const ROUTE_LABEL = {
  clean: "All checks pass · for a person to sign",
  to_person: "A person must review",
  reject: "Recommend reject",
  needs_person: "Record missing · a person must look",
  reply: "Draft reply · check and send",
  already_decided: "Already settled · do not credit again",
};

// Short labels for list tags and line pills.
export const ROUTE_SHORT = {
  clean: "Ready to sign",
  to_person: "Review",
  reject: "Reject",
  needs_person: "Info missing",
  reply: "Reply",
  already_decided: "Settled",
};

export const CHECK_LABEL = {
  duplicate: "Duplicate",
  window: "Claim window",
  supplied: "Supplied to stockist",
  quantity: "Quantity limit",
  invoice_ref: "Invoice reference",
  batch: "Batch and expiry",
  value: "Value",
  cfa: "Billing CFA",
};

export const ACTION_LABEL = {
  approve: "Credit",
  approve_part: "Credit in part",
  reject: "Reject",
  review: "Review",
  missing_info: "Ask the stockist",
  already_decided: "No action",
};

// Indian digit grouping: 3,31,728.30
export const inr = (v) =>
  typeof v === "number" ? `₹${v.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` : "n/a";

// Short money for cards: Rs 1.77 cr, Rs 61.2 L, Rs 45,000.
export const inrShort = (v) => {
  if (typeof v !== "number") return "n/a";
  if (Math.abs(v) >= 1e7) return `₹${(v / 1e7).toFixed(2)} cr`;
  if (Math.abs(v) >= 1e5) return `₹${(v / 1e5).toFixed(1)} L`;
  return `₹${Math.round(v).toLocaleString("en-IN")}`;
};

// Decisions that go against the recommendation need a written reason (mirrors app.py).
export const isOverride = (recommended, decision) =>
  (["reject", "needs_person"].includes(recommended) && decision === "approve") ||
  (recommended === "clean" && decision === "reject");
