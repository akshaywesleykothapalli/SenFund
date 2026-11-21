const $ = s => document.querySelector(s);
const api = async (path, body) => {
  const r = await fetch("/api" + path, body ? {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body)} : {});
  const j = await r.json();
  if (!r.ok) throw new Error(j.error || r.status);
  return j;
};
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
let cfg;

async function refresh() {
  const list = await api("/invoices");
  $("#rows").innerHTML = list.map(i => `<tr><td><code>${esc(i.id)}</code></td><td>${esc(i.usd)} ${esc(i.asset || "USDT")}</td><td>${esc(i.payment)}</td>
    <td><span class="sim">SIM</span> ${esc(i.conversion)}</td><td><span class="sim">SIM</span> ${esc(i.payout)}${i.needs_review ? " ⚠ review" : ""}</td>
    <td><button data-id="${esc(i.id)}">Open</button></td></tr>`).join("");
}

async function show(id) {
  const i = await api("/invoices/" + id);
  const d = $("#detail"); d.hidden = false;
  const tx = i.tx_hash ? (cfg.explorer ? `<a href="${esc(cfg.explorer)}/tx/${esc(i.tx_hash)}" target="_blank" rel="noopener">${esc(i.tx_hash)}</a>` : esc(i.tx_hash)) : "—";
  const payout = i.operations.find(o => o.stage === "payout");
  const quote = payout ? JSON.parse(payout.detail) : {};
  const cre = i.operations.find(o => o.stage === "cre");
  const decision = cre ? JSON.parse(cre.detail) : {};
  const route = {mudrex: "Mudrex", p2p: "P2P fallback"}[quote.route] || "Mock remittance";
  const awaitingCredit = quote.route === "p2p" && payout.external_id && i.payout === "ON_HOLD" &&
    i.payment === "PAID" && !i.needs_review;
  d.innerHTML = `<h2>Invoice ${esc(i.id)}</h2>
    <p>${esc(i.usd)} ${esc(i.asset || "USDT")} · payment <b>${esc(i.payment)}</b> · tx ${tx}</p>
    <p>Checkout link (works with this app stopped): <a href="${esc(i.checkout)}" target="_blank" rel="noopener">open checkout</a></p>
    <p><button data-a="verify">Verify onchain</button>
       ${i.asset === "WBT" ? "Settles in wrapped WBT." : `<button data-a="convert">Run simulated USD conversion</button>
       <label>Payout scenario
         <select id="scn">
           <option value="success">Mudrex succeeds</option>
           <option value="mudrex_unavailable">Mudrex unavailable → P2P fallback</option>
           <option value="timeout">Mudrex times out</option>
           <option value="timeout_created">Mudrex accepts order, response lost</option>
           <option value="fail">Mudrex reports failure</option>
         </select>
       </label>
       <button data-a="payout">${cfg.localCcip ? "Run CRE + CCIP simulation" : cfg.crePayouts ? "Run Chainlink CRE payout simulation" : "Run simulated INR payout"}</button>`}
       <a href="/api/invoices/${esc(i.id)}/receipt" target="_blank">Receipt</a></p>
    ${cre ? `<p><b>${esc(decision.source)}</b> · ${esc(cre.status)} · ${esc(decision.reason)}</p>` : ""}
    ${decision.ens ? `<p>Finalized ENSv2 recipient matched for <code>${esc(decision.ens.name)}</code> on ${esc(decision.ens.network ?? (decision.ens.chainId === 1 ? "Ethereum mainnet" : "Ethereum Sepolia"))}.</p>` : ""}
    ${decision.ccip ? `<p>CCIP approval (Chainlink Local) · receiver route ${esc(decision.ccip.beforeRoute)} → ${esc(decision.ccip.afterRoute)} · message <code>${esc(decision.ccip.messageId)}</code></p>` : ""}
    ${payout ? `<p>Simulated payout via <b>${esc(route)}</b> · ${esc(i.payout)}. ${esc(quote.fallback_reason)}</p>` : ""}
    ${awaitingCredit ? '<p>Awaiting simulated INR credit. <button data-a="simulate-p2p-credit">Simulate bank credit</button></p>' : ""}
    <p><label>Paid elsewhere? Submit tx hash <input id="txh" size="66"></label> <button data-a="submit">Submit</button></p>
    <pre>${esc(JSON.stringify(i, null, 2))}</pre>`;
  d.onclick = async e => {
    const a = e.target.dataset.a; if (!a) return;
    try {
      const body = a === "payout" ? {scenario: $("#scn").value} : a === "submit" ? {tx_hash: $("#txh").value} : {};
      await api(`/invoices/${id}/${a}`, body);
      $("#msg").textContent = a + " ok";
    } catch (err) { $("#msg").textContent = a + ": " + err.message; }
    show(id); refresh();
  };
}

$("#create").elements.asset.onchange = () => { $("#create").elements.usd.value = ""; };
$("#create").onsubmit = async e => {
  e.preventDefault();
  try { const i = await api("/invoices", Object.fromEntries(new FormData(e.target))); $("#msg").textContent = "Signed invoice " + i.id; refresh(); show(i.id); }
  catch (err) { $("#msg").textContent = err.message; }
};
$("#rows").onclick = e => e.target.dataset.id && show(e.target.dataset.id);

(async () => {
  cfg = await api("/config");
  $("#asset-choice").hidden = !cfg.paymentAssets?.includes("WBT");
  $("#net").textContent = `${cfg.env === "testnet" ? "Whitechain Sepolia testnet" : "Local dev chain"} · chain ${cfg.chainId}`;
  refresh(); setInterval(refresh, 5000);
})();
