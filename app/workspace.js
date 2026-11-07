"use client";

import { useCallback, useEffect, useRef, useState } from "react";

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
  if (invoice.payout === "ON_HOLD" && payout.detail.route === "p2p") return `Your payout of ${amt} is going via Protected P2P fallback. Your USDT stays locked until your bank confirms the credit (simulated).`;
  if (invoice.payout === "ON_HOLD") return `Your payout of ${amt} is on hold. The provider may have accepted the order, so we are checking before doing anything else.`;
  return "";
}

function nextStep(invoice, payout) {
  if (invoice.needsReview) return "Next: settlement review. Payout is paused.";
  if (invoice.payment !== "PAID") return expired(invoice) ? "Checkout link expired. Create a new invoice." : invoice.payment === "SUBMITTED" ? "Next: verify the submitted payment." : "Waiting for the client to pay in test USDT.";
  if (invoice.conversion !== "COMPLETED") return "Paid. Next: run the simulated conversion.";
  if (invoice.payout === "COMPLETED") return "Complete. Receipt and evidence pack are ready.";
  if (invoice.payout === "FAILED") return "Simulated payout failed. See the payout section.";
  if (invoice.payout === "ON_HOLD") return payout?.detail.route === "p2p" ? "Pending bank credit (simulated). Next: simulate bank credit." : "Provider hold. Checking order status before any retry.";
  return "Converted. Next: run the simulated payout.";
}

function InvoiceForm({ busy, onCreate, corridors }) {
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
    {drafting && <fieldset className="fields">
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
      <label>Amount (USDT)<span className="affix"><input name="usd" inputMode="decimal" placeholder="250.00" pattern="[0-9]+([.][0-9]{1,2})?" required /><b>USDT</b></span><small>Client pays in test USDT.</small></label>
      <label>Payout corridor<select name="corridor" defaultValue="IN">
        {Object.entries(corridors || { IN: { currency: "INR" } }).map(([code, c]) => <option key={code} value={code}>{code} · {c.currency} (simulated)</option>)}
      </select><small>Local currency you receive. No real money moves.</small></label>
    </fieldset>
    {note && <p className="note">{note}</p>}
    <div className="formFooter"><p>Client pays in USDT. SenFund routes the payout.</p><button type="button" onClick={draft}>Draft note</button><button className="primary" disabled={busy}>{busy ? "Signing…" : "Sign invoice"}</button></div>
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
      <div><p className="reference">{invoice.id}</p><h2 id="invoice-title" tabIndex={-1}>{invoice.description}</h2><p className="muted">{invoice.customer}</p></div>
      <button className="plain" onClick={onClose}>Close details</button>
    </div>
    <p className={`nextStep ${invoice.payout === "ON_HOLD" && payout?.detail.route !== "p2p" ? "hold" : ""}`} role="status">{nextStep(invoice, payout)}</p>
    <dl className="facts">
      <div><dt>Amount</dt><dd className="amount">${invoice.usd} USDT</dd></div>
      <div><dt>Settlement</dt><dd>{expired(invoice) ? <span className="state bad">Expired</span> : <Status value={invoice.payment} />}</dd></div>
      {invoice.expiresAt && <div><dt>Checkout expires</dt><dd>{date(invoice.expiresAt)}</dd></div>}
      <div><dt>Created</dt><dd>{date(invoice.createdAt)}</dd></div>
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
      <section><h3>Onchain settlement</h3><p className="caption">Test USDT on Whitechain</p><Status value={invoice.payment} />
        {invoice.receipt && <p>Block <code>{invoice.receipt.block}</code></p>}
        {invoice.payment === "SUBMITTED" && <button disabled={busy} onClick={() => onAction("verify", {})}>Verify payment</button>}
        {invoice.payment !== "PAID" && <form className="hashForm" onSubmit={event => { event.preventDefault(); onAction("submit", { tx_hash: hash }); }}>
          <label>Payment transaction hash<input value={hash} onChange={event => setHash(event.target.value)} required /></label>
          <button disabled={busy}>Submit hash</button>
        </form>}
      </section>
      <section><h3>Simulated conversion</h3><p className="caption">Simulated, no funds move</p><Status value={invoice.conversion} />
        {conversion && <p>{conversion.detail.net_usd} USD net after a {conversion.detail.fee_usd} USD simulated fee.</p>}
        {canSimulate && invoice.conversion !== "COMPLETED" &&
          <button disabled={busy} onClick={() => onAction("convert", {})}>Simulate conversion</button>}
      </section>
      <section><h3>Simulated payout</h3><p className="caption">Simulated, no funds move</p><Status value={invoice.payout} />
        {decision && <p>{decision.detail.source}: {decision.detail.reason}</p>}
        {payout && <p>{payout.detail.route === "p2p" ? "Protected P2P fallback" : payout.detail.route === "mudrex" ? "Mudrex" : payout.detail.route === "eu_offramp" ? "MiCA off-ramp" : payout.detail.route === "local_offramp" ? "Licensed local off-ramp" : "Provider simulation"}{payout.detail.amount != null ? `, ${payout.detail.amount} ${payout.detail.currency} simulated` : ""}{payout.reference && <>, reference <code>{payout.reference}</code></>}</p>}
        {canSimulate && invoice.conversion === "COMPLETED" && !["COMPLETED", "FAILED"].includes(invoice.payout) &&
          <div className="hashForm"><label>Scenario<select value={scenario} onChange={event => setScenario(event.target.value)}>
            {scenarios.map(([value, text]) => <option value={value} key={value}>{text}</option>)}
          </select></label><button disabled={busy} onClick={() => onAction("payout", { scenario })}>{config.crePayouts ? "Run CRE simulation" : "Simulate payout"}</button></div>}
        {payout && <p className={`advisor ${invoice.payout === "ON_HOLD" ? (payout.detail.route === "p2p" ? "credit" : "hold") : ""}`}>{advisor(invoice, payout)}</p>}
        {canSimulate && invoice.payout === "ON_HOLD" && payout?.detail.route === "p2p" && payout.reference &&
          <button disabled={busy} onClick={() => onAction("simulate-p2p-credit", {})}>Simulate bank credit</button>}
      </section>
    </div>
    {!!invoice.history.length && <section className="history"><h3>Activity</h3><ol>
      {[...invoice.history].reverse().map((entry, index) => <li key={index}>
        <div><strong>{stages[entry.stage] ?? entry.stage}: {label(entry.new)}</strong>{entry.reason && <p>{entry.reason}</p>}</div>
        <time dateTime={new Date(entry.at * 1000).toISOString()}>{date(entry.at)}</time>
      </li>)}
    </ol></section>}
  </section>;
}

function WalletView({ wallets, corridors, disabled, onLink, canVerify, accountsEnabled }) {
  const [balances, setBalances] = useState({});
  const [quote, setQuote] = useState("");
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
  const list = Object.entries(corridors || {});
  function withdraw(event) {
    event.preventDefault();
    const f = new FormData(event.currentTarget), c = corridors?.[f.get("corridor")];
    const amount = Number(f.get("amount"));
    if (!c || !(amount > 0)) return setQuote("Enter an amount and pick a corridor.");
    const out = amount * Number(c.rate) - Number(c.fee);
    setQuote(out > 0 ? `You would receive about ${out.toFixed(2)} ${c.currency}. Simulated — no money moves.` : "Amount is below the corridor fee.");
  }
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
        {!b ? <span className="muted">Loading…</span> : b.error ? <span className="muted">{b.error}</span> : <span className="balanceAmounts"><b>{b.native}</b> WHITE <b>{b.token}</b> USDT</span>}
      </li>; })}</ul> : <p className="muted">No wallet connected. Connect a browser wallet to see balances.</p>}
    </section>
    <form className="invoiceForm" onSubmit={withdraw}>
      <div className="sectionTitle"><h2>Withdraw to bank</h2><p>Simulated — no money moves. Nothing is signed.</p></div>
      <fieldset className="fields">
        <label>Amount (USDT)<span className="affix"><input name="amount" inputMode="decimal" placeholder="100.00" required /><b>USDT</b></span></label>
        <label>Corridor<select name="corridor" disabled={!list.length}>{!list.length && <option>Loading corridors…</option>}{list.map(([code, c]) => <option key={code} value={code}>{code} · {c.currency} (simulated)</option>)}</select></label>
      </fieldset>
      <div className="actions"><button type="submit">Get simulated quote</button></div>
      <p role="status">{quote}</p>
    </form>
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

export default function Workspace({ accountsEnabled }) {
  const [profile, setProfile] = useState(null);
  const [wallets, setWallets] = useState([]);
  const [signedOut, setSignedOut] = useState(false);
  const [config, setConfig] = useState(null);
  const [invoices, setInvoices] = useState([]);
  const [selected, setSelected] = useState(null);
  const [showForm, setShowForm] = useState(false);
  const [view, setView] = useState("invoices");
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

  return <div className="shell">
    <aside className="rail" aria-label="Workspace">
      <a className="brand" href="/">SenFund<span>Merchant workspace</span></a>
      <p className="railNavLabel">Workspace</p>
      <nav>{[["invoices", "Invoices"], ["wallet", "Wallet"]].map(([id, text]) =>
        <a key={id} href={"#" + id} aria-current={view === id ? "page" : undefined} onClick={event => { event.preventDefault(); setView(id); setError(""); setStatus(""); }}><NavIcon d={navIcons[id]} />{text}</a>)}
        <p className="railNavLabel">Resources</p>
        {config?.explorer && <a href={config.token ? `${config.explorer}/address/${config.token}` : config.explorer} target="_blank" rel="noreferrer"><NavIcon d={navIcons.explorer} />Block explorer</a>}
        <a href="/#how"><NavIcon d={navIcons.how} />How settlement works</a>
        {profile && !wallets.length && view === "invoices" && <p className="railHint">Verify a wallet before you issue invoices.</p>}</nav>
    </aside>
    <main id="invoices">
      <div className="topline"><span>Merchant workspace</span><span className="toplineRight"><span className="environment">{config?.env === "testnet" ? "Testnet" : config?.env ?? (loading ? "Connecting" : "Offline")}</span>
        {profile && <details className="profileMenu"><summary aria-label="Profile menu">{(profile.displayName || profile.email || "?")[0].toUpperCase()}</summary>
          <div className="profilePanel"><p><strong>{profile.displayName || "Merchant"}</strong><span>{profile.email}</span></p>
            {[["account", "Account and wallets"], ["wallet", "Wallet"], ["invoices", "Invoices"]].map(([id, text]) =>
              <button key={id} type="button" onClick={event => { event.currentTarget.closest("details").open = false; setView(id); setError(""); setStatus(""); }}>{text}</button>)}
            <button type="button" disabled={!!busy} onClick={() => run("sign-out", async () => { await api("auth/sign-out", {}); location.reload(); })}>Sign out</button>
          </div></details>}</span></div>
      {view === "wallet" ? <WalletView wallets={wallets} corridors={config?.corridors} disabled={!!busy} onLink={linkWallet} canVerify={!!profile} accountsEnabled={accountsEnabled} /> : view === "invoices" ? <>
      <header className="heading">
        <div><h1>Invoices</h1><p>Issue USDT invoices and track payment, conversion and payout.</p></div>
        <button className="primary" disabled={!config || !!busy || (accountsEnabled && !profile?.canIssue)} onClick={() => setShowForm(!showForm)}>{showForm ? "Close form" : "New invoice"}</button>
      </header>
      <p className="notice">Clients pay in test USDT. Conversion and payout are simulations.</p>
      {error && <p role="alert" className="alert">{error}</p>}
      <div className="feedback" role="status">{status}</div>
      {config && !loading && invoices.length === 0 && !showForm && <section className="onboarding" aria-labelledby="onboarding-title">
        <h2 id="onboarding-title">Get started</h2>
        <ol>
          <li>Payments settle in test USDT. Conversion and payout are simulated, so no real money moves.</li>
          <li>Pick a payout corridor (simulated): India, Europe, UK, Mexico, Kenya, UAE and more. Each has a protected fallback.</li>
          <li>Create your first invoice and share its payment link.</li>
        </ol>
        <button className="primary" disabled={!!busy || (accountsEnabled && !profile?.canIssue)} onClick={() => setShowForm(true)}>Create first invoice</button>
      </section>}
      {showForm && <InvoiceForm busy={!!busy} onCreate={create} corridors={config?.corridors} />}
      <div className={selected ? "board open" : "board"}>
      <section className="register" aria-labelledby="register-title">
        <div className="registerTop"><div><h2 id="register-title">Invoice register</h2>{config && <p>{invoices.length} {invoices.length === 1 ? "invoice" : "invoices"}</p>}</div><button disabled={!!busy || loading} onClick={reload}>{busy === "refresh" ? "Refreshing…" : "Refresh"}</button></div>
        {loading ? <p className="empty">Loading invoices…</p> :
          !config ? <p className="empty">Connect the local settlement service to view invoices.</p> :
          invoices.length === 0 ? <p className="empty">No invoices yet. Create an invoice to get a payment link.</p> :
          <div className="tableScroll"><table>
            <thead><tr><th scope="col">Invoice</th><th scope="col">Amount</th><th scope="col">Settlement</th><th scope="col">Payout simulation</th><th scope="col">Details</th></tr></thead>
            <tbody>{invoices.map(invoice => <tr key={invoice.id} className={selected?.id === invoice.id ? "selected" : undefined}>
              <th scope="row"><strong>{invoice.customer || invoice.id}</strong><code>{invoice.id}</code></th>
              <td className="amount" data-label="Amount">${invoice.usd} <span>USDT</span></td>
              <td data-label="Settlement">{expired(invoice) ? <span className="state bad">Expired</span> : <Status value={invoice.payment} />}</td><td data-label="Payout simulation"><Status value={invoice.payout} /></td>
              <td><button className="plain" data-opens="1" disabled={!!busy} onClick={() => run("open", () => open(invoice.id))} aria-label={`Open invoice ${invoice.id}`}>Open details</button></td>
            </tr>)}</tbody>
          </table></div>}
      </section>
      {selected && <InvoiceDetail key={selected.id} invoice={selected} config={config} busy={!!busy}
        onAction={update} onClose={() => setSelected(null)} onCopy={link => run("copy", async () => {
          await navigator.clipboard.writeText(link);
          setStatus("Payment link copied.");
        })} />}
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
    </main>
  </div>;
}
