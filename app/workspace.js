"use client";

import { useCallback, useEffect, useRef, useState } from "react";

const states = {
  OPEN: "Awaiting payment", SUBMITTED: "Confirming", PAID: "Verified",
  NOT_STARTED: "Not started", PENDING: "Pending", COMPLETED: "Complete",
  QUOTED: "Quoted", ON_HOLD: "On hold", FAILED: "Failed", CANCELLED: "Cancelled",
};
const stages = { payment: "Settlement", conversion: "Conversion", payout: "Payout" };
const scenarios = [
  ["success", "Mudrex available"],
  ["mudrex_unavailable", "Mudrex unavailable before dispatch"],
  ["timeout", "Mudrex times out"],
  ["timeout_created", "Mudrex accepts, response lost"],
  ["fail", "Mudrex rejects the order"],
];
const dateFormat = new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" });
const date = seconds => dateFormat.format(new Date(seconds * 1000));
const label = value => states[value] ?? value.toLowerCase().replaceAll("_", " ");
const short = value => value.length > 22 ? `${value.slice(0, 10)}…${value.slice(-6)}` : value;

async function api(path, body, key) {
  const response = await fetch("/api/" + path, {
    cache: "no-store",
    ...(body ? { method: "POST", headers: { "Content-Type": "application/json", ...(key ? { "Idempotency-Key": key } : {}) }, body: JSON.stringify(body) } : {}),
  });
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || "SenFund could not complete the request.");
  return result;
}

function Status({ value }) {
  const tone = value === "PAID" || value === "COMPLETED" ? "good" :
    ["OPEN", "SUBMITTED", "ON_HOLD", "PENDING"].includes(value) ? "waiting" :
    value === "FAILED" ? "bad" : "quiet";
  return <span className={"state " + tone}>{label(value)}</span>;
}

function InvoiceForm({ busy, onCreate }) {
  return <form className="invoiceForm" id="new-invoice" onSubmit={onCreate}>
    <div className="sectionTitle"><h2>New invoice</h2><p>Enter the client and service details to generate a signed payment link.</p></div>
    <div className="fields">
      <label>Client<input name="customer" autoComplete="organization" maxLength={100} required /></label>
      <label>Service description<input name="description" maxLength={200} required /></label>
      <label>Amount in USD<input name="usd" inputMode="decimal" pattern="[0-9]+([.][0-9]{1,2})?" required /></label>
    </div>
    <div className="formFooter"><p>Demo pricing uses one test USDT per invoice USD.</p><button className="primary" disabled={busy}>{busy ? "Signing…" : "Sign invoice"}</button></div>
  </form>;
}

function InvoiceDetail({ invoice, config, busy, onAction, onClose, onCopy }) {
  const [hash, setHash] = useState("");
  const [scenario, setScenario] = useState("success");
  const conversion = invoice.operations.find(operation => operation.stage === "conversion");
  const payout = invoice.operations.find(operation => operation.stage === "payout");
  const decision = invoice.operations.find(operation => operation.stage === "cre");
  const canSimulate = invoice.payment === "PAID" && !invoice.needsReview;
  const txLink = invoice.txHash && config.explorer && `${config.explorer}/tx/${invoice.txHash}`;
  return <section className="detail" aria-labelledby="invoice-title">
    <div className="detailTop">
      <div><p className="reference">{invoice.id}</p><h2 id="invoice-title">{invoice.description}</h2><p className="muted">{invoice.customer}</p></div>
      <button className="plain" onClick={onClose}>Close details</button>
    </div>
    <dl className="facts">
      <div><dt>Invoice amount</dt><dd>${invoice.usd} USD</dd></div>
      <div><dt>Created</dt><dd>{date(invoice.createdAt)}</dd></div>
      {invoice.expiresAt && <div><dt>Checkout expires</dt><dd>{date(invoice.expiresAt)}</dd></div>}
      {invoice.recipient && <div><dt>Settlement recipient</dt><dd><code title={invoice.recipient}>{short(invoice.recipient)}</code></dd></div>}
    </dl>
    <div className="actions">
      {invoice.payment !== "PAID" && invoice.checkout && <>
        <a className="button primary" href={invoice.checkout} target="_blank" rel="noreferrer">Open checkout</a>
        <button onClick={() => onCopy(invoice.checkout)}>Copy payment link</button>
      </>}
      {txLink && <a className="button" href={txLink} target="_blank" rel="noreferrer">View transaction</a>}
      {invoice.receipt && <a className="button" href={`/api/invoices/${invoice.id}/receipt`} download>Download receipt</a>}
    </div>
    {invoice.needsReview && <p className="alert">Payment review required. Payout is paused while the settlement is reconciled.</p>}
    <div className="stageGrid">
      <section><h3>Whitechain settlement</h3><Status value={invoice.payment} />
        {invoice.receipt && <p>Block <code>{invoice.receipt.block}</code></p>}
        {invoice.payment === "SUBMITTED" && <button disabled={busy} onClick={() => onAction("verify", {})}>Verify payment</button>}
        {invoice.payment !== "PAID" && <form className="hashForm" onSubmit={event => { event.preventDefault(); onAction("submit", { tx_hash: hash }); }}>
          <label>Payment transaction hash<input value={hash} onChange={event => setHash(event.target.value)} required /></label>
          <button disabled={busy}>Submit hash</button>
        </form>}
      </section>
      <section><h3>USD conversion</h3><p className="caption">Simulation</p><Status value={invoice.conversion} />
        {conversion && <p>{conversion.detail.net_usd} USD net after a {conversion.detail.fee_usd} USD simulated fee.</p>}
        {canSimulate && invoice.conversion !== "COMPLETED" &&
          <button disabled={busy} onClick={() => onAction("convert", {})}>Simulate conversion</button>}
      </section>
      <section><h3>INR payout</h3><p className="caption">Simulation</p><Status value={invoice.payout} />
        {decision && <p>{decision.detail.source}: {decision.detail.reason}</p>}
        {payout && <p>{payout.detail.route === "p2p" ? "P2P fallback" : payout.detail.route === "mudrex" ? "Mudrex" : "Provider simulation"}{payout.detail.inr != null ? ` · ${payout.detail.inr} INR simulated` : ""}{payout.reference && <> · <code>{payout.reference}</code></>}</p>}
        {canSimulate && invoice.conversion === "COMPLETED" && !["COMPLETED", "FAILED"].includes(invoice.payout) &&
          <div className="hashForm"><label>Scenario<select value={scenario} onChange={event => setScenario(event.target.value)}>
            {scenarios.map(([value, text]) => <option value={value} key={value}>{text}</option>)}
          </select></label><button disabled={busy} onClick={() => onAction("payout", { scenario })}>{config.crePayouts ? "Run CRE simulation" : "Simulate payout"}</button></div>}
        {canSimulate && invoice.payout === "ON_HOLD" && payout?.detail.route === "p2p" && payout.reference &&
          <button disabled={busy} onClick={() => onAction("simulate-p2p-credit", {})}>Simulate bank credit</button>}
      </section>
    </div>
    {!!invoice.history.length && <section className="history"><h3>Activity</h3><ol>
      {[...invoice.history].reverse().map((entry, index) => <li key={index}>
        <div><strong>{stages[entry.stage] ?? entry.stage} · {label(entry.new)}</strong>{entry.reason && <p>{entry.reason}</p>}</div>
        <time dateTime={new Date(entry.at * 1000).toISOString()}>{date(entry.at)}</time>
      </li>)}
    </ol></section>}
  </section>;
}

export default function Workspace() {
  const [config, setConfig] = useState(null);
  const [invoices, setInvoices] = useState([]);
  const [selected, setSelected] = useState(null);
  const [showForm, setShowForm] = useState(false);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState("");
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");
  const creation = useRef(null);

  const refresh = useCallback(async () => {
    const [nextConfig, list] = await Promise.all([api("config"), api("invoices")]);
    setConfig(nextConfig);
    setInvoices(list);
  }, []);

  useEffect(() => {
    let active = true;
    refresh().catch(reason => { if (active) setError(reason.message); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [refresh]);

  async function run(key, task) {
    setBusy(key);
    setError("");
    setStatus("");
    try { await task(); }
    catch (reason) { setError(reason.message); }
    finally { setBusy(""); }
  }

  async function open(id) {
    setSelected(await api(`invoices/${id}`));
  }

  function create(event) {
    event.preventDefault();
    const body = Object.fromEntries(new FormData(event.currentTarget));
    const details = JSON.stringify(body);
    if (creation.current?.details !== details) {
      creation.current = { details, key: crypto.randomUUID() };
    }
    run("create", async () => {
      const invoice = await api("invoices", body, creation.current.key);
      creation.current = null;
      setSelected(invoice);
      setShowForm(false);
      setStatus("Invoice signed. The payment link is ready.");
      await refresh();
    });
  }

  function update(action, body) {
    const id = selected.id;
    run(action, async () => {
      const result = await api(`invoices/${id}/${action}`, body);
      await Promise.all([open(id), refresh()]);
      if (result.status === "rejected") throw new Error(result.detail ?? "The transaction does not match this invoice.");
      setStatus(result.status === "pending" ? "The transaction is awaiting confirmation." : "Invoice updated.");
    });
  }

  function reload() {
    run("refresh", async () => {
      await Promise.all([refresh(), selected ? open(selected.id) : Promise.resolve()]);
      setStatus("Invoice register refreshed.");
    });
  }

  const network = config?.chainId === 1874 ? "Whitechain Sepolia" :
    config ? `Local chain ${config.chainId}` : "Connection pending";

  return <div className="shell">
    <aside className="rail" aria-label="Workspace">
      <a className="brand" href="/">SenFund<span>Merchant workspace</span></a>
      <nav><a href="#invoices" aria-current="page">Invoices</a></nav>
      <div className="railFooter"><p>Settlement network</p><strong>{network}</strong>{config?.chainId === 1874 && <span>Chain 1874</span>}{config?.ensName && <span>{config.ensName}</span>}</div>
    </aside>
    <main id="invoices">
      <div className="topline"><span>Merchant workspace</span><span className="environment">{config?.env === "testnet" ? "Testnet" : config?.env ?? (loading ? "Connecting" : "Offline")}</span></div>
      <header className="heading">
        <div><h1>Invoices</h1><p>Issue USD invoices and verify test USDT payments.</p></div>
        <button className="primary" disabled={!config || !!busy} onClick={() => setShowForm(!showForm)}>{showForm ? "Close form" : "New invoice"}</button>
      </header>
      <p className="notice">Settlement uses test USDT. USD conversion and INR payout are simulations.</p>
      {error && <p role="alert" className="alert">{error}</p>}
      <div className="feedback" role="status">{status}</div>
      {showForm && <InvoiceForm busy={!!busy} onCreate={create} />}
      <section className="register" aria-labelledby="register-title">
        <div className="registerTop"><div><h2 id="register-title">Invoice register</h2>{config && <p>{invoices.length} {invoices.length === 1 ? "invoice" : "invoices"}</p>}</div><button disabled={!!busy || loading} onClick={reload}>{busy === "refresh" ? "Refreshing…" : "Refresh"}</button></div>
        {loading ? <p className="empty">Loading invoices…</p> :
          !config ? <p className="empty">Connect the local settlement service to view invoices.</p> :
          invoices.length === 0 ? <p className="empty">No invoices yet. Create an invoice to get a payment link.</p> :
          <div className="tableScroll"><table>
            <thead><tr><th scope="col">Invoice</th><th scope="col">Amount</th><th scope="col">Settlement</th><th scope="col">INR simulation</th><th scope="col">Details</th></tr></thead>
            <tbody>{invoices.map(invoice => <tr key={invoice.id} className={selected?.id === invoice.id ? "selected" : undefined}>
              <th scope="row"><strong>{invoice.customer || invoice.id}</strong><code>{invoice.id}</code></th>
              <td className="amount">${invoice.usd} <span>USD</span></td>
              <td><Status value={invoice.payment} /></td><td><Status value={invoice.payout} /></td>
              <td><button className="plain" disabled={!!busy} onClick={() => run("open", () => open(invoice.id))} aria-label={`Open invoice ${invoice.id}`}>Open</button></td>
            </tr>)}</tbody>
          </table></div>}
      </section>
      {selected && <InvoiceDetail key={selected.id} invoice={selected} config={config} busy={!!busy}
        onAction={update} onClose={() => setSelected(null)} onCopy={link => run("copy", async () => {
          await navigator.clipboard.writeText(link);
          setStatus("Payment link copied.");
        })} />}
    </main>
  </div>;
}
