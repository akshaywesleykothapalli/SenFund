import test from "node:test";
import assert from "node:assert/strict";
import { GET, POST } from "../app/api/[...path]/route.js";

const id = "inv_0123456789ab";
const headers = { origin: "http://127.0.0.1:3000", host: "127.0.0.1:3000", "content-type": "application/json" };
const ctx = (...path) => ({ params: Promise.resolve({ path }) });
let sent;
globalThis.fetch = async (url, init = {}) => {
  sent = { url, body: init.body && JSON.parse(init.body) };
  return Response.json(url.endsWith("/evidence") ? { invoice: id, corridor: "EU" } : { id, corridor: "EU", operations: [] });
};

test("corridor forwarded, bad corridor rejected", async () => {
  const body = { usd: "10", customer: "A", description: "B", corridor: "EU" };
  const ok = await POST(new Request("http://127.0.0.1:3000/api/invoices", { method: "POST", headers, body: JSON.stringify(body) }), ctx("invoices"));
  assert.equal(sent.body.corridor, "EU");
  assert.ok(ok.status < 300);
  const bad = await POST(new Request("http://127.0.0.1:3000/api/invoices", { method: "POST", headers, body: JSON.stringify({ ...body, corridor: "US" }) }), ctx("invoices"));
  assert.equal(bad.status, 400);
});

test("evidence pack downloads as named JSON", async () => {
  const res = await GET(new Request(`http://127.0.0.1:3000/api/invoices/${id}/evidence`, { headers }), ctx("invoices", id, "evidence"));
  assert.equal(res.status, 200);
  assert.match(res.headers.get("content-disposition"), new RegExp(`senfund-evidence-${id}\\.json`));
  assert.equal((await res.json()).corridor, "EU");
});
