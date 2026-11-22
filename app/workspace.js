"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Logo from "./logo";
import { AnimatePresence, MotionConfig, motion, useReducedMotion } from "framer-motion";

const expired = invoice => invoice.payment === "OPEN" && invoice.expiresAt && invoice.expiresAt * 1000 < Date.now();

const states = {
  OPEN: "Awaiting payment", SUBMITTED: "Confirming", PAID: "Verified",
  NOT_STARTED: "Not started", PENDING: "Pending", COMPLETED: "Complete",
  QUOTED: "Quoted", ON_HOLD: "On hold", FAILED: "Failed", CANCELLED: "Cancelled",
};
const stages = { payment: "Settlement", conversion: "Conversion", payout: "Payout" };
const scenarios = [
  ["success", "Mudrex available"],
  ["mudrex_unavailable", "Licensed provider unavailable (needs identity verification)"],
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
  if (!response.ok) throw Object.assign(new Error(result.error || "SenFund could not complete the request."), { status: response.status });
  return result;
}

function NavIcon({ d }) {
  return <svg aria-hidden="true" viewBox="0 0 24 24" width="17" height="17" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"><path d={d} /></svg>;
}
const navIcons = {
  overview: "M3 3h8v8H3zM13 3h8v8h-8zM3 13h8v8H3zM13 13h8v8h-8z",
  invoices: "M7 3h7l4 4v14H7zM14 3v4h4M10 12h6M10 16h6",
  explorer: "M14 4h6v6M20 4l-9 9M18 14v6H4V6h6",
  how: "M4 6h16M4 12h10M4 18h6",
  wallet: "M3 7h16v12H3zM3 7l3-4h11v4M16 13h2",
  account: "M12 12a4 4 0 100-8 4 4 0 000 8zM4 21c0-4 3.6-6 8-6s8 2 8 6",
};

function Status({ value }) {
  const tone = value === "PAID" || value === "COMPLETED" ? "good" :
    ["OPEN", "SUBMITTED", "ON_HOLD", "PENDING"].includes(value) ? "waiting" :
    value === "FAILED" ? "bad" : "quiet";
  return <span className={"state " + tone}>{label(value)}</span>;
}

// Mirrors backend advisor_line wording.
function advisor(invoice, payout) {
  const amt = `${payout.detail.amount} ${payout.detail.currency} (simulated)`;
  if (invoice.payout === "COMPLETED") return `Your payout of ${amt} is complete.`;
  if (invoice.payout === "ON_HOLD" && payout.detail.route === "p2p") return `Your P2P payout of ${amt} is waiting for simulated bank credit.`;
  if (invoice.payout === "ON_HOLD") return `Your payout of ${amt} is on hold. The provider may have accepted the order, so we are checking before doing anything else.`;
  return "";
}

function nextStep(invoice, payout) {
  if (invoice.needsReview) return "Next: settlement review. Payout is paused.";
  if (invoice.payment !== "PAID") return expired(invoice) ? "Checkout link expired. Create a new invoice." : invoice.payment === "SUBMITTED" ? "Next: verify the submitted payment." : `Waiting for the client to pay in test ${invoice.asset ?? "USDT"}.`;
  if (invoice.asset === "WBT") return "Paid. Wrapped WBT was sent to the settlement recipient.";
  if (invoice.conversion !== "COMPLETED") return "Paid. Next: run the simulated conversion.";
  if (invoice.payout === "COMPLETED") return "Complete. Receipt and evidence pack are ready.";
  if (invoice.payout === "FAILED") return "Simulated payout failed. See the payout section.";
  if (invoice.payout === "ON_HOLD") return payout?.detail.route === "p2p" ? "Pending bank credit (simulated). Next: simulate bank credit." : "Provider hold. Checking order status before any retry.";
  return "Converted. Next: run the simulated payout.";
}

function InvoiceSummary({ invoices, onSelect }) {
  const groups = [
    { id: "awaiting", title: "Awaiting payment", count: invoices.filter(i => ["OPEN", "SUBMITTED"].includes(i.payment) && !expired(i)).length, note: "Open links and confirmations", icon: navIcons.invoices },
    { id: "paid", title: "Settled onchain", count: invoices.filter(i => i.payment === "PAID").length, note: "Verified testnet payments", icon: navIcons.wallet },
    { id: "attention", title: "Needs attention", count: invoices.filter(i => i.needsReview || i.payout === "ON_HOLD" || i.payout === "FAILED" || expired(i)).length, note: "Reviews, holds and expired links", icon: navIcons.how },
    { id: "complete", title: "Payout complete", count: invoices.filter(i => i.payout === "COMPLETED").length, note: "Simulated bank payouts", icon: navIcons.explorer },
  ];
  return <section className="summaryGrid" aria-label="Invoice overview">
    {groups.map(group => <motion.button key={group.id} className="summaryCard" onClick={() => onSelect(group.id)}
      whileHover={{ y: -3 }} whileTap={{ scale: 0.99 }}>
      <span className="summaryLabel"><NavIcon d={group.icon} />{group.title}</span>
      <strong>{group.count}</strong><small>{group.note}</small>
    </motion.button>)}
  </section>;
}

function InvoiceForm({ busy, onCreate, corridors, assets }) {
  const [asset, setAsset] = useState("USDT");
  const [note, setNote] = useState("");
  const [drafting, setDrafting] = useState(false);
  const [pasted, setPasted] = useState("");
  useEffect(() => { fetch("/api/draft-invoice").then(r => r.ok ? r.json() : {}).then(r => setDrafting(!!r.enabled)).catch(() => {}); }, []);
  async function fill(event) {
    const f = event.currentTarget.form;
    try {
      const r = await api("draft-invoice", { text: pasted });
      f.customer.value = r.client_name; f.usd.value = r.amount_usd; f.description.value = r.description;
      setNote(`Due ${r.due_date}. Check every field before you sign.`);
    } catch (error) { setNote(error.message); }
  }
  async function draft(event) {
    const f = event.currentTarget.form;
    try {
      const r = await api("draft-note", { payer: f.customer.value, amount: f.usd.value, description: f.description.value });
      setNote(r.note);
    } catch (error) { setNote(error.message); }
  }
  return <form className="invoiceForm" id="new-invoice" onSubmit={onCreate}>
    <div className="sectionTitle"><h2>New invoice</h2><p>Enter the client and service details to generate a signed payment link.</p></div>
    {drafting && asset === "USDT" && <fieldset className="fields">
      <legend>Paste a message</legend>
      <label className="wide">Client message<textarea value={pasted} onChange={e => setPasted(e.target.value)} maxLength={4000} rows={3} /><small>Fills the form. Nothing is signed until you press Sign invoice.</small></label>
      <button type="button" onClick={fill} disabled={!pasted.trim()}>Fill from message</button>
    </fieldset>}
    <fieldset className="fields">
      <legend>Bill to</legend>
      <label className="wide">Client name or company<input name="customer" autoComplete="organization" placeholder="Acme Studio Ltd." maxLength={100} required /></label>
    </fieldset>
    <fieldset className="fields">
      <legend>Work</legend>
      <label className="wide">Service description<input name="description" placeholder="Brand identity design, October 2026" maxLength={200} required /><small>Shown to the client on the payment page.</small></label>
    </fieldset>
    <fieldset className="fields">
      <legend>Payment</legend>
      {assets?.includes("WBT") && <label>Payment asset<select name="asset" value={asset} onChange={event => {
        setAsset(event.target.value);
        event.currentTarget.form.usd.value = "";
        setNote("");
      }}><option value="USDT">USDT (test)</option><option value="WBT">WBT (test)</option></select></label>}
      <label>Amount ({asset})<span className="affix"><input name="usd" inputMode="decimal" placeholder={asset === "WBT" ? "0.01" : "250.00"} pattern="[0-9]+([.][0-9]{1,2})?" required /><b>{asset}</b></span>
        <small>{asset === "WBT" ? "Client can wrap WBT at checkout. You receive wrapped WBT." : "Client pays in test USDT."}</small></label>
      {asset === "USDT" && <label>Payout corridor<select name="corridor" defaultValue="IN">
        {Object.entries(corridors || { IN: { currency: "INR" } }).map(([code, c]) => <option key={code} value={code}>{code} · {c.currency} (simulated)</option>)}
      </select><small>Local currency you receive. No real money moves.</small></label>}
    </fieldset>
    {note && <p className="note">{note}</p>}
    <div className="formFooter"><p>{asset === "WBT" ? "Wrapped WBT settles to your testnet wallet." : "Client pays in USDT. SenFund routes the simulated payout."}</p>{asset === "USDT" && <button type="button" onClick={draft}>Draft note</button>}<button className="primary" disabled={busy}>{busy ? "Signing…" : "Sign invoice"}</button></div>
  </form>;
}

function InvoiceDetail({ invoice, config, busy, onAction, onClose, onCopy }) {
  const [hash, setHash] = useState("");
  const [scenario, setScenario] = useState("success");
  const conversion = invoice.operations.find(operation => operation.stage === "conversion");
  const payout = invoice.operations.find(operation => operation.stage === "payout");
  const decision = invoice.operations.find(operation => operation.stage === "cre");
  const cashOut = invoice.operations.some(operation => operation.stage === "cash-out");
  const asset = invoice.asset ?? "USDT";
  const canSimulate = invoice.payment === "PAID" && !invoice.needsReview;
  const txLink = invoice.txHash && config.explorer && `${config.explorer}/tx/${invoice.txHash}`;
  return <section className="detail" aria-labelledby="invoice-title">
    <div className="detailTop">
      <div><p className="reference">{invoice.id}</p><h2 id="invoice-title" tabIndex={-1}>{invoice.description}</h2><p className="muted">{invoice.customer}</p></div>
      <button className="plain" onClick={onClose}>Close details</button>
    </div>
    <p className={`nextStep ${invoice.payout === "ON_HOLD" && payout?.detail.route !== "p2p" ? "hold" : ""}`} role="status">{cashOut && invoice.payout === "NOT_STARTED" ? "Resume this cash-out from Wallet." : nextStep(invoice, payout)}</p>
    <dl className="facts">
      <div><dt>Amount</dt><dd className="amount">{invoice.usd} {asset}</dd></div>
      <div><dt>Settlement</dt><dd>{expired(invoice) ? <span className="state bad">Expired</span> : <Status value={invoice.payment} />}</dd></div>
      {invoice.expiresAt && <div><dt>Checkout expires</dt><dd>{date(invoice.expiresAt)}</dd></div>}
      <div><dt>Created</dt><dd>{date(invoice.createdAt)}</dd></div>
      <div><dt>Network</dt><dd>Whitechain Sepolia · {config.chainId}</dd></div>
      {asset === "USDT" && <div><dt>Payout corridor</dt><dd>{invoice.corridor ?? "IN"} · {config.corridors?.[invoice.corridor ?? "IN"]?.currency ?? "Local currency"} (simulated)</dd></div>}
      {invoice.recipient && <div className="wide"><dt>Settlement recipient</dt><dd><code>{invoice.recipient}</code></dd></div>}
      {invoice.txHash && <div className="wide"><dt>Transaction</dt><dd><code>{invoice.txHash}</code></dd></div>}
    </dl>
    <div className="actions" aria-label="Invoice actions">
      {invoice.payment !== "PAID" && invoice.checkout && !expired(invoice) && <>
        <a className="button primary" href={invoice.checkout} target="_blank" rel="noreferrer">Open checkout</a>
        <button onClick={() => onCopy(invoice.checkout)}>Copy payment link</button>
      </>}
      {txLink && <a className="button" href={txLink} target="_blank" rel="noreferrer">View transaction</a>}
      {invoice.receipt && <a className="button" href={`/api/invoices/${invoice.id}/receipt`} download>Download receipt</a>}
      {invoice.receipt && <a className="button" href={`/api/invoices/${invoice.id}/evidence`} download={`senfund-evidence-${invoice.id}.json`}>Download evidence pack</a>}
    </div>
    {invoice.needsReview && <p className="alert">Payment review required. Payout is paused while the settlement is reconciled.</p>}
    <div className="stageGrid">
      <section><h3>Onchain settlement</h3><p className="caption">Test {asset === "WBT" ? "wrapped WBT" : "USDT"} on Whitechain</p><Status value={invoice.payment} />
        {invoice.receipt && <p>Block <code>{invoice.receipt.block}</code></p>}
        {invoice.payment === "SUBMITTED" && <button disabled={busy} onClick={() => onAction("verify", {})}>Verify payment</button>}
        {invoice.payment !== "PAID" && <form className="hashForm" onSubmit={event => { event.preventDefault(); onAction("submit", { tx_hash: hash }); }}>
          <label>Payment transaction hash<input value={hash} onChange={event => setHash(event.target.value)} required /></label>
          <button disabled={busy}>Submit hash</button>
        </form>}
      </section>
      {asset === "USDT" && <><section><h3>Simulated conversion</h3><p className="caption">Simulated, no funds move</p><Status value={invoice.conversion} />
        {conversion && <p>{conversion.detail.net_usd} USD net after a {conversion.detail.fee_usd} USD simulated fee.</p>}
        {canSimulate && invoice.conversion !== "COMPLETED" &&
          <button disabled={busy} onClick={() => onAction("convert", {})}>Simulate conversion</button>}
      </section>
      <section><h3>Simulated payout</h3><p className="caption">Simulated, no funds move</p><Status value={invoice.payout} />
        {decision && <p>{decision.detail.source}: {decision.detail.reason}</p>}
        {decision?.detail.ens && <p>Finalized ENSv2 recipient matched for <code>{decision.detail.ens.name}</code> on {decision.detail.ens.network ?? (decision.detail.ens.chainId === 1 ? "Ethereum mainnet" : "Ethereum Sepolia")}.</p>}
        {decision?.detail.ccip && <details>
          <summary>CCIP approval (Chainlink Local)</summary>
          <p>Receiver route {decision.detail.ccip.beforeRoute} → {decision.detail.ccip.afterRoute}</p>
          <p>CRE run <code>{decision.detail.run}</code></p>
          <p style={{overflowWrap: "anywhere"}}>CCIP message <code>{decision.detail.ccip.messageId}</code></p>
        </details>}
        {payout && <p>{payout.detail.route === "p2p" ? "Protected P2P fallback" : payout.detail.route === "mudrex" ? "Mudrex" : payout.detail.route === "eu_offramp" ? "MiCA off-ramp" : payout.detail.route === "local_offramp" ? "Licensed local off-ramp" : "Provider simulation"}{payout.detail.amount != null ? `, ${payout.detail.amount} ${payout.detail.currency} simulated` : ""}{payout.reference && <>, reference <code>{payout.reference}</code></>}</p>}
        {canSimulate && !cashOut && invoice.conversion === "COMPLETED" && !["COMPLETED", "FAILED"].includes(invoice.payout) &&
          <div className="hashForm"><label>Scenario<select value={scenario} onChange={event => setScenario(event.target.value)}>
            {scenarios.map(([value, text]) => <option value={value} key={value}>{text}</option>)}
          </select></label><button disabled={busy} onClick={() => onAction("payout", { scenario })}>{config.localCcip ? "Run CRE + CCIP simulation" : config.crePayouts ? "Run CRE simulation" : "Simulate payout"}</button></div>}
        {payout?.detail.amount != null && <dl className="quoteBreakdown">
          <div><dt>Net payout</dt><dd>{payout.detail.amount} {payout.detail.currency}</dd></div>
          <div><dt>Payout fee</dt><dd>{payout.detail.fee ?? "—"} {payout.detail.currency}</dd></div>
          <div><dt>Fixture rate</dt><dd>{payout.detail.rate ?? "—"} {payout.detail.currency} / USD</dd></div>
          <div><dt>Pricing</dt><dd>Simulated</dd></div>
        </dl>}
        {payout?.detail.fallback_reason && <p className="note">{payout.detail.fallback_reason}</p>}
        {payout && <p className={`advisor ${invoice.payout === "ON_HOLD" ? (payout.detail.route === "p2p" ? "credit" : "hold") : ""}`}>{advisor(invoice, payout)}</p>}
        {canSimulate && invoice.payout === "ON_HOLD" && payout?.detail.route === "p2p" && payout.reference &&
          <button disabled={busy} onClick={() => onAction("simulate-p2p-credit", {})}>Simulate bank credit</button>}
      </section>
      </>}
    </div>
    {!!invoice.history.length && <section className="history"><h3>Activity</h3><ol>
      {[...invoice.history].reverse().map((entry, index) => <li key={index}>
        <div><strong>{stages[entry.stage] ?? entry.stage}: {label(entry.new)}</strong>{entry.reason && <p>{entry.reason}</p>}</div>
        <time dateTime={new Date(entry.at * 1000).toISOString()}>{date(entry.at)}</time>
      </li>)}
    </ol></section>}
  </section>;
}

function CashOut({ invoices, corridors, onOrder }) {
  const [invoiceId, setInvoiceId] = useState("");
  const [currency, setCurrency] = useState("");
  const [quote, setQuote] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const eligible = invoices.filter(invoice =>
    invoice.payment === "PAID" && (invoice.asset ?? "USDT") === "USDT" &&
    invoice.payout === "NOT_STARTED" && !invoice.needsReview);
  const invoice = eligible.find(item => item.id === invoiceId);
  const locked = invoice?.operations.find(operation => operation.stage === "cash-out")?.detail.corridor;
  const corridor = locked ?? currency;

  async function request(confirm) {
    if (!invoice || !corridor || busy) return;
    setBusy(true);
    setError("");
    try {
      const result = await api(`invoices/${invoice.id}/cash-out`, { corridor, confirm });
      if (confirm) await onOrder(result);
      else setQuote(result);
    } catch (reason) {
      setError(reason.message);
    } finally {
      setBusy(false);
    }
  }

  return <form className="invoiceForm" onSubmit={event => { event.preventDefault(); request(false); }}>
    <div className="sectionTitle"><h2>Cash out USDT to a bank</h2><p>Simulate a P2P payout for the full amount of a verified invoice. No funds move.</p></div>
    {eligible.length ? <>
      <fieldset className="fields" disabled={busy}>
        <label>Paid invoice<select required value={invoice ? invoiceId : ""} onChange={event => {
          setInvoiceId(event.target.value); setQuote(null); setError("");
        }}>
          <option value="">Choose an invoice</option>
          {eligible.map(item => <option key={item.id} value={item.id}>{item.customer || item.id} · {item.usd} USDT</option>)}
        </select></label>
        <label>Payout currency<select required disabled={!!locked} value={corridor} onChange={event => {
          setCurrency(event.target.value); setQuote(null); setError("");
        }}>
          <option value="">Choose a currency</option>
          {Object.entries(corridors || {}).map(([code, c]) => <option key={code} value={code}>{c.currency} · {code}</option>)}
        </select></label>
      </fieldset>
      {error && <p role="alert" className="alert">{error}</p>}
      {quote && <p className="note" role="status"><strong>Simulated estimated bank credit {quote.amount} {quote.currency}</strong> for {quote.inputUsdt} USDT. Includes a {quote.conversionFeeUsd} USD conversion fee and a {quote.fee} {quote.currency} payout fee.</p>}
      <div className="actions">
        <button type="submit" disabled={!invoice || !corridor || busy}>Get simulated quote</button>
        {quote && <button type="button" className="primary" disabled={!invoice || busy} onClick={() => request(true)}>Confirm simulated P2P order</button>}
        {busy && <span role="status">Checking cash-out…</span>}
      </div>
    </> : <p className="muted">Pay and verify a new USDT invoice to cash out. Invoices with an existing payout are excluded.</p>}
  </form>;
}

function WalletView({ wallets, invoices, corridors, onOrder, canCashOut, disabled, onLink, canVerify, accountsEnabled }) {
  const [balances, setBalances] = useState({});
  const [connected, setConnected] = useState([]);
  const [chain, setChain] = useState("");
  const [note, setNote] = useState("");
  useEffect(() => {
    const eth = window.ethereum;
    if (!eth) return;
    const onAccounts = a => setConnected((a || []).map(x => x.toLowerCase()));
    const onChain = c => setChain(String(c));
    eth.request({ method: "eth_accounts" }).then(onAccounts).catch(() => {});
    eth.request({ method: "eth_chainId" }).then(onChain).catch(() => {});
    eth.on?.("accountsChanged", onAccounts);
    eth.on?.("chainChanged", onChain);
    return () => { eth.removeListener?.("accountsChanged", onAccounts); eth.removeListener?.("chainChanged", onChain); };
  }, []);
  const addresses = [...new Set([...connected, ...wallets.map(w => w.address.toLowerCase())])];
  const key = addresses.join(",");
  useEffect(() => {
    addresses.forEach(a => api("balance/" + a).then(b => setBalances(x => ({ ...x, [a]: b })))
      .catch(e => setBalances(x => ({ ...x, [a]: { error: e.message } }))));
  }, [key]); // eslint-disable-line react-hooks/exhaustive-deps
  async function connect() {
    const eth = window.ethereum;
    if (!eth) return setNote("No browser wallet found. Install MetaMask or a similar wallet.");
    try {
      setConnected((await eth.request({ method: "eth_requestAccounts" })).map(x => x.toLowerCase()));
      await eth.request({ method: "wallet_switchEthereumChain", params: [{ chainId: "0x752" }] }).catch(() => setNote("Switch your wallet to Whitechain Sepolia (chain 1874)."));
    } catch (e) { setNote(e.message); }
  }
  async function disconnect() {
    // Wallets without wallet_revokePermissions keep the site connected; clear local state either way.
    await window.ethereum?.request({ method: "wallet_revokePermissions", params: [{ eth_accounts: {} }] }).catch(() => {});
    setConnected([]); setChain(""); setNote("Wallet disconnected.");
  }
  const short = a => a.slice(0, 6) + "…" + a.slice(-4);
  const purposes = a => wallets.filter(w => w.address.toLowerCase() === a).map(w => w.purpose).join(", ");
  return <>
    <header className="heading"><div><h1>Wallet</h1><p>Testnet balances for your connected and verified wallets.</p></div>
      <div className="actions">
        <button className="primary" onClick={connect}>{connected.length ? "Wallet connected" : "Connect browser wallet"}</button>
        {connected.length > 0 && (canVerify ? <button disabled={disabled} onClick={() => onLink("recipient")}>Verify ownership</button>
          : accountsEnabled ? <a className="button" href="/api/auth/sign-in">Sign in to verify</a>
          : <span className="muted">Verification needs account mode (SENFUND_ACCOUNT_MODE=1).</span>)}
        {connected.length > 0 && <button type="button" onClick={disconnect}>Disconnect</button>}
      </div></header>
    {connected[0] && <section className="invoiceForm walletHead">
      <div className="sectionTitle"><h2>Connected wallet</h2><p>{chain === "0x752" ? "Whitechain Sepolia · chain 1874" : chain ? `Wrong network (${parseInt(chain, 16)}). Switch to chain 1874.` : "Network unknown"}</p></div>
      <p className="walletAddress"><code title={connected[0]}>{connected[0]}</code>
        <button type="button" onClick={() => navigator.clipboard?.writeText(connected[0])}>Copy</button></p>
    </section>}
    {note && <p role="status" className="muted">{note}</p>}
    <section className="invoiceForm">
      <div className="sectionTitle"><h2>Balances</h2><p>Whitechain Sepolia testnet. Read only.</p></div>
      {addresses.length ? <ul className="balanceList">{addresses.map(a => { const b = balances[a]; return <li key={a}>
        <div><code title={a}>{short(a)}</code> <span className="muted">{purposes(a) || "connected, not verified"}</span></div>
        {!b ? <span className="muted">Loading…</span> : b.error ? <span className="muted">{b.error}</span> : <span className="balanceAmounts"><b>{b.native}</b> WBT <b>{b.token}</b> USDT {b.tokens?.WWBT && <><b>{b.tokens.WWBT}</b> WWBT</>}</span>}
      </li>; })}</ul> : <p className="muted">No wallet connected. Connect a browser wallet to see balances.</p>}
    </section>
    {canCashOut && <CashOut invoices={invoices} corridors={corridors} onOrder={onOrder} />}
  </>;
}

function Wallets({ wallets, disabled, onLink }) {
  return <section className="invoiceForm">
    <div className="sectionTitle"><h2>Verified wallets</h2><p>Prove wallet ownership with a message signature.</p></div>
    {wallets.length ? <ul>{wallets.map(wallet => <li key={wallet.address + wallet.chain_id + wallet.purpose}>
      <code>{wallet.address}</code> <span className="muted">{wallet.purpose}</span>
    </li>)}</ul> : <p className="muted">No verified wallets.</p>}
    <div className="actions">
      <a className="button" href="/api/auth/sign-in">Refresh sign in</a>
      <button disabled={disabled} onClick={() => onLink("signer")}>Verify signing wallet</button>
      <button disabled={disabled} onClick={() => onLink("recipient")}>Verify receiving wallet</button>
    </div>
  </section>;
}

const balanceText = amount => amount.includes(".") ? amount.replace(/0+$/, "").replace(/\.$/, "") : amount;

function statement(payments) {
  const cell = value => {
    const text = String(value ?? "");
    const safe = /^[\s]*[=+@-]|^[\t\r\n]/.test(text) ? "'" + text : text;
    return '"' + safe.replaceAll('"', '""') + '"';
  };
  const rows = [["Verified at (UTC)", "Invoice", "Client on invoice", "Paying wallet", "Receiving wallet", "Asset", "Amount", "Block", "Transaction"],
    ...payments.map(row => [
      row.verifiedAt ? new Date(row.verifiedAt * 1000).toISOString() : "", row.invoice, row.customer, row.payer,
      row.recipient, row.asset, row.amount, row.block, row.txHash,
    ])];
  const url = URL.createObjectURL(new Blob([rows.map(row => row.map(cell).join(",")).join("\r\n")], {type: "text/csv;charset=utf-8"}));
  const link = document.createElement("a");
  link.href = url;
  link.download = "senfund-payment-statement.csv";
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function MerchantOverview({ onInvoices, onCashOut }) {
  const [wallet, setWallet] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError("");
    try { setWallet(await api("treasury")); }
    catch (reason) { setError(reason.message); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { refresh(); }, [refresh]);

  return <>
    <header className="heading"><div><h1>Dashboard</h1><p>Track what arrived in your SenFund receiving wallet.</p></div>
      <div className="actions"><button disabled={loading} onClick={refresh}>{loading ? "Checking…" : "Refresh"}</button>
        <button onClick={onCashOut}>Cash out USDT</button>
        <button className="primary" onClick={onInvoices}>View invoices</button></div></header>
    {error && <p role="alert" className="alert">{error}</p>}
    {wallet && <>
      <section className="invoiceForm treasuryBalances" aria-labelledby="receiving-wallet-title">
        <div className="sectionTitle">
          <h2 id="receiving-wallet-title">{wallet.ensName || "Receiving wallet"}</h2>
          <p>Whitechain Sepolia · chain {wallet.chainId}</p>
          <code>{wallet.address}</code>
        </div>
        <div className="treasuryMetrics">
          {Object.entries({...wallet.tokens, WBT: wallet.native}).map(([asset, amount]) =>
            <div key={asset}><span className="muted">Test {asset} balance</span><strong>{balanceText(amount)} {asset}</strong>
              {wallet.received[asset] !== undefined && <small>{wallet.received[asset]} received via SenFund</small>}</div>)}
        </div>
      </section>
      <section className="invoiceForm treasuryLedger" aria-labelledby="ledger-title">
        <div className="detailTop">
          <div className="sectionTitle"><h2 id="ledger-title">Verified payments</h2>
            <p>Confirmed SenFund invoices paid to this wallet. Client names come from your invoices.</p></div>
          <button onClick={() => statement(wallet.payments)} disabled={!wallet.payments.length}>Download CSV statement</button>
        </div>
        {wallet.payments.length ? <div className="treasuryTable"><table>
          <thead><tr><th scope="col">From</th><th scope="col">Received</th><th scope="col">Verified</th><th scope="col">Proof</th></tr></thead>
          <tbody>{wallet.payments.map(row => <tr key={row.invoice}>
            <td><strong>{row.customer || "Client wallet"}</strong><br /><code title={row.payer}>{short(row.payer)}</code></td>
            <td><strong>{row.amount} {row.asset}</strong></td>
            <td>{row.verifiedAt ? date(row.verifiedAt) : `Block ${row.block}`}</td>
            <td>{wallet.explorer && <a href={`${wallet.explorer}/tx/${row.txHash}`} target="_blank" rel="noreferrer">Transaction</a>}
              {" · "}<a href={`/api/invoices/${row.invoice}/receipt`} download>Receipt</a></td>
          </tr>)}</tbody>
        </table></div> : <p className="muted">Verified invoice payments will appear here.</p>}
      </section>
    </>}
  </>;
}

export default function Workspace({ accountsEnabled }) {
  const reduceMotion = useReducedMotion();
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState("all");
  const [profile, setProfile] = useState(null);
  const [wallets, setWallets] = useState([]);
  const [signedOut, setSignedOut] = useState(false);
  const [config, setConfig] = useState(null);
  const [invoices, setInvoices] = useState([]);
  const [selected, setSelected] = useState(null);
  const [showForm, setShowForm] = useState(false);
  const [view, setView] = useState("overview");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState("");
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");
  const creation = useRef(null);

  const refresh = useCallback(async () => {
    const [nextConfig, list, account, verifiedWallets] = await Promise.all([
      api("config"), api("invoices"), accountsEnabled ? api("profile") : null,
      accountsEnabled ? api("wallets") : [],
    ]);
    setConfig(nextConfig);
    setInvoices(list);
    setProfile(account);
    setWallets(verifiedWallets);
  }, [accountsEnabled]);

  useEffect(() => {
    let active = true;
    refresh().catch(reason => {
      if (!active) return;
      if (accountsEnabled && reason.status === 401) setSignedOut(true);
      else setError(reason.message);
    })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [refresh, accountsEnabled]);

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

  useEffect(() => {
    const heading = document.getElementById("invoice-title");
    if (heading && document.activeElement?.dataset.opens) { heading.focus(); heading.scrollIntoView({ block: "start" }); }
  }, [selected?.id]);

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

  function linkWallet(purpose) {
    run("wallet", async () => {
      const wallet = window.ethereum;
      if (!wallet) throw new Error("Open this page in a browser with a supported Ethereum wallet.");
      const [address] = await wallet.request({ method: "eth_requestAccounts" });
      if (!address) throw new Error("Select a wallet account.");
      const chain = "0x" + config.chainId.toString(16);
      if (await wallet.request({ method: "eth_chainId" }) !== chain) {
        await wallet.request({ method: "wallet_switchEthereumChain", params: [{ chainId: chain }] });
      }
      if (await wallet.request({ method: "eth_chainId" }) !== chain) throw new Error("Switch to the configured settlement chain.");
      const proof = await api("wallets/challenge", { address, purpose });
      const bytes = new TextEncoder().encode(proof.message);
      const message = "0x" + Array.from(bytes, byte => byte.toString(16).padStart(2, "0")).join("");
      const signature = await wallet.request({ method: "personal_sign", params: [message, address] });
      setWallets(await api("wallets/verify", { challenge: proof.challenge, signature }));
      setStatus("Wallet ownership verified.");
    });
  }

  if (signedOut) return <main><header className="heading"><div><h1>SenFund</h1><p>Sign in to your merchant workspace.</p></div>
    <a className="button primary" href="/api/auth/sign-in">Sign in or register</a></header></main>;

  const showTreasury = !accountsEnabled || profile?.canIssue;
  const filtered = invoices.filter(invoice => {
    const matches = [invoice.id, invoice.customer, invoice.description, invoice.asset, invoice.txHash]
      .some(value => String(value ?? "").toLowerCase().includes(query.trim().toLowerCase()));
    if (!matches) return false;
    if (filter === "awaiting") return ["OPEN", "SUBMITTED"].includes(invoice.payment) && !expired(invoice);
    if (filter === "paid") return invoice.payment === "PAID";
    if (filter === "attention") return invoice.needsReview || invoice.payout === "ON_HOLD" || invoice.payout === "FAILED" || expired(invoice);
    if (filter === "complete") return invoice.payout === "COMPLETED";
    return true;
  });
  function showFiltered(value) { setFilter(value); setQuery(""); setView("invoices"); }

  return <MotionConfig reducedMotion="user"><div className="shell">
    <aside className="rail" aria-label="Workspace">
      <Logo className="brand" caption="Merchant workspace" />
      <p className="railNavLabel">Workspace</p>
      <nav>{[...(showTreasury ? [["overview", "Dashboard"]] : []), ["invoices", "Invoices"], ["wallet", "Wallet"]].map(([id, text]) =>
        <a key={id} href={"#" + id} aria-current={view === id ? "page" : undefined} onClick={event => { event.preventDefault(); setView(id); setError(""); setStatus(""); }}><NavIcon d={navIcons[id]} />{text}{view === id && <motion.span className="navMarker" layoutId="workspace-nav" transition={{ type: "spring", stiffness: 400, damping: 35 }} />}</a>)}
        <p className="railNavLabel">Resources</p>
        {config?.explorer && <a href={config.token ? `${config.explorer}/address/${config.token}` : config.explorer} target="_blank" rel="noreferrer"><NavIcon d={navIcons.explorer} />Block explorer</a>}
        <a href="/#how"><NavIcon d={navIcons.how} />How settlement works</a>
        {profile && !wallets.length && view === "invoices" && <p className="railHint">Verify a wallet before you issue invoices.</p>}</nav>
      <div className="railFooter"><p>Settlement network</p><strong><span className={config ? "dot live" : "dot"} />{config ? "Whitechain Sepolia" : "Connecting…"}</strong><span className="muted">Test assets · simulated payouts</span></div>
    </aside>
    <main id="invoices">
      <div className="topline"><span>Merchant workspace</span><span className="toplineRight"><span className="environment">{config?.env === "testnet" ? "Testnet" : config?.env ?? (loading ? "Connecting" : "Offline")}</span>
        {profile && <details className="profileMenu"><summary aria-label="Profile menu">{(profile.displayName || profile.email || "?")[0].toUpperCase()}</summary>
          <div className="profilePanel"><p><strong>{profile.displayName || "Merchant"}</strong><span>{profile.email}</span></p>
            {[["account", "Account and wallets"], ["wallet", "Wallet"], ["invoices", "Invoices"]].map(([id, text]) =>
              <button key={id} type="button" onClick={event => { event.currentTarget.closest("details").open = false; setView(id); setError(""); setStatus(""); }}>{text}</button>)}
            <button type="button" disabled={!!busy} onClick={() => run("sign-out", async () => { await api("auth/sign-out", {}); location.reload(); })}>Sign out</button>
          </div></details>}</span></div>
      <motion.div key={view} className="workspaceView" initial={{ opacity: 0, y: reduceMotion ? 0 : 10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: reduceMotion ? 0 : 0.24 }}>
      {(view === "overview" || view === "wallet") && error && <p className="alert" role="alert">{error}</p>}
      {(view === "overview" || view === "wallet") && status && <p className="feedback" role="status">{status}</p>}
      {view === "overview" && showTreasury && !loading && <InvoiceSummary invoices={invoices} onSelect={showFiltered} />}
      {view === "overview" && showTreasury ? <MerchantOverview onInvoices={() => setView("invoices")} onCashOut={() => setView("wallet")} /> : view === "wallet" ? <WalletView
        wallets={wallets} invoices={invoices} corridors={config?.corridors} canCashOut={showTreasury}
        disabled={!!busy} onLink={linkWallet} canVerify={!!profile} accountsEnabled={accountsEnabled}
        onOrder={async invoice => {
          setSelected(invoice);
          setError("");
          setStatus(invoice.payout === "NOT_STARTED" ? "Cash-out is waiting for payout approval." : "Simulated P2P order updated.");
          setView("invoices");
          await refresh();
        }} /> : view === "invoices" || view === "overview" ? <>
      <header className="heading">
        <div><h1>Invoices</h1><p>Issue invoices and track settlement and simulated payouts.</p></div>
        <button className="primary" disabled={!config || !!busy || (accountsEnabled && !profile?.canIssue)} onClick={() => setShowForm(!showForm)}>{showForm ? "Close form" : "New invoice"}</button>
      </header>
      {!loading && config && <InvoiceSummary invoices={invoices} onSelect={showFiltered} />}
      <p className="notice">Whitechain Sepolia · payments settle to the signed recipient. Conversion and bank payouts are simulated.</p>
      {error && <p role="alert" className="alert">{error}</p>}
      <div className="feedback" role="status">{status}</div>
      {config && !loading && invoices.length === 0 && !showForm && <section className="onboarding" aria-labelledby="onboarding-title">
        <h2 id="onboarding-title">Get started</h2>
        <ol>
          <li>USDT invoices support simulated conversion and payout. WBT invoices settle in wrapped WBT.</li>
          <li>Pick a payout corridor (simulated): India, Europe, UK, Mexico, Kenya, UAE and more. Each has a protected fallback.</li>
          <li>Create your first invoice and share its payment link.</li>
        </ol>
        <button className="primary" disabled={!!busy || (accountsEnabled && !profile?.canIssue)} onClick={() => setShowForm(true)}>Create first invoice</button>
      </section>}
      <AnimatePresence initial={false}>
        {showForm && <motion.div key="invoice-form" initial={{ opacity: 0, height: reduceMotion ? "auto" : 0 }} animate={{ opacity: 1, height: "auto" }} exit={{ opacity: 0, height: reduceMotion ? "auto" : 0 }} transition={{ duration: 0.22 }} style={{ overflow: "hidden" }}>
          <InvoiceForm busy={!!busy} onCreate={create} corridors={config?.corridors} assets={config?.paymentAssets} />
        </motion.div>}
      </AnimatePresence>
      <div className={selected ? "board open" : "board"}>
      <section className="register" aria-labelledby="register-title">
        <div className="registerTop"><div><h2 id="register-title">Invoice register</h2>{config && <p>{invoices.length} {invoices.length === 1 ? "invoice" : "invoices"}</p>}</div><button disabled={!!busy || loading} onClick={reload}>{busy === "refresh" ? "Refreshing…" : "Refresh"}</button></div>
        <div className="registerTools">
          <label className="searchField"><span>Search invoices</span><input type="search" placeholder="Client, invoice, description or transaction" value={query} onChange={event => setQuery(event.target.value)} /></label>
          <label><span>Status</span><select value={filter} onChange={event => setFilter(event.target.value)}>
            <option value="all">All invoices</option><option value="awaiting">Awaiting payment</option><option value="paid">Settled onchain</option><option value="attention">Needs attention</option><option value="complete">Simulated payout complete</option>
          </select></label>
          {(query || filter !== "all") && <button className="plain" onClick={() => { setQuery(""); setFilter("all"); }}>Clear filters</button>}
        </div>
        {config && !loading && <p className="resultCount" aria-live="polite">{filtered.length} of {invoices.length} invoices</p>}
        {loading ? <div className="loadingRows" role="status"><span>Loading your invoice register…</span><i /><i /><i /></div> :
          !config ? <p className="empty">Connect the local settlement service to view invoices.</p> :
          invoices.length === 0 ? <p className="empty">No invoices yet. Create an invoice to get a payment link.</p> :
          filtered.length === 0 ? <div className="empty"><h3>No matching invoices</h3><p>Try another client name or status.</p><button onClick={() => { setQuery(""); setFilter("all"); }}>Show all invoices</button></div> :
          <div className="tableScroll"><table>
            <thead><tr><th scope="col">Invoice</th><th scope="col">Amount</th><th scope="col">Settlement</th><th scope="col">Payout simulation</th><th scope="col">Details</th></tr></thead>
            <tbody>{filtered.map(invoice => <tr key={invoice.id} className={selected?.id === invoice.id ? "selected" : undefined}>
              <th scope="row"><strong>{invoice.customer || invoice.id}</strong><span className="invoiceDescription">{invoice.description}</span><code>{invoice.id}</code><span className="invoiceDate">{date(invoice.createdAt)}</span></th>
              <td className="amount" data-label="Amount">{invoice.usd} <span>{invoice.asset ?? "USDT"}</span></td>
              <td data-label="Settlement">{expired(invoice) ? <span className="state bad">Expired</span> : <Status value={invoice.payment} />}</td><td data-label="Payout simulation">{invoice.asset === "WBT" ? "Wallet settlement" : <Status value={invoice.payout} />}</td>
              <td data-label="Actions"><button className="plain" data-opens="1" disabled={!!busy} onClick={() => run("open", () => open(invoice.id))} aria-label={`Open invoice ${invoice.id}`}>Open details</button></td>
            </tr>)}</tbody>
          </table></div>}
      </section>
      <AnimatePresence mode="wait" initial={false}>{selected && <motion.div key={selected.id} className="detailPane" initial={{ opacity: 0, x: reduceMotion ? 0 : 12 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0 }} transition={{ duration: 0.18 }}><InvoiceDetail invoice={selected} config={config} busy={!!busy}
        onAction={update} onClose={() => setSelected(null)} onCopy={link => run("copy", async () => {
          await navigator.clipboard.writeText(link);
          setStatus("Payment link copied.");
        })} /></motion.div>}</AnimatePresence>
      </div>
      </> : <>
      <header className="heading"><div><h1>Account</h1><p>Profile, sign in and wallet ownership.</p></div></header>
      {error && <p role="alert" className="alert">{error}</p>}
      <div className="feedback" role="status">{status}</div>
      {profile && <form className="invoiceForm" onSubmit={event => {
        event.preventDefault();
        const body = Object.fromEntries(new FormData(event.currentTarget));
        run("profile", async () => {
          setProfile(await api("profile", body));
          setStatus("Profile saved.");
        });
      }}>
        <div className="sectionTitle"><h2>Profile</h2><p>{profile.email}</p></div>
        <div className="fields"><label>Display name<input name="displayName" defaultValue={profile.displayName ?? ""} maxLength={100} required /></label></div>
        <div className="actions"><button disabled={!!busy}>Save profile</button>
          <button type="button" disabled={!!busy} onClick={() => run("sign-out", async () => {
            await api("auth/sign-out", {});
            location.reload();
          })}>Sign out</button>
          <button type="button" disabled={!!busy} onClick={() => run("sign-out", async () => {
            await api("auth/sign-out", { allSessions: true });
            location.reload();
          })}>Sign out on all devices</button></div>
      </form>}
      {profile && <Wallets wallets={wallets} disabled={!!busy} onLink={linkWallet} />}
      </>}
      </motion.div>
    </main>
  </div></MotionConfig>;
}
