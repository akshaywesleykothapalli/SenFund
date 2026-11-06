// SenFund static checkout: no backend, no build step. Request arrives in the URL fragment (#req=base64url JSON).
const SETTLE_SELECTOR = "0x3414c14f";  // settle(bytes32,address,address,address,uint256,uint256,bytes)
const CHECK_SELECTOR = "0xd6591e18";
const APPROVE_SELECTOR = "0x095ea7b3"; // approve(address,uint256)
const SETTLED_TOPIC = "0x85698fa15ef6458f171e64e809e549b751ab3db8a7c7e78b51744c5983a8b8d5";
const CHAINS = {
  1874: { chainId: "0x752", chainName: "Whitechain Sepolia", rpcUrls: ["https://rpc.testnet.whitechain.io"],
          nativeCurrency: { name: "WBT", symbol: "WBT", decimals: 18 }, blockExplorerUrls: ["https://explorer.testnet.whitechain.io"] },
};
const $ = (id) => document.getElementById(id);
const log = (msg, cls) => { const li = document.createElement("li"); li.textContent = msg; if (cls) li.className = cls; $("log").append(li); return li; };
const word = (hex) => hex.replace(/^0x/i, "").toLowerCase().padStart(64, "0");
const uint = (n) => word(BigInt(n).toString(16));

function parseReq() {
  const m = location.hash.match(/req=([A-Za-z0-9_-]+)/);
  if (!m) throw new Error("No payment request in link.");
  const b64 = m[1].replace(/-/g, "+").replace(/_/g, "/");
  const r = JSON.parse(atob(b64 + "=".repeat((4 - (b64.length % 4)) % 4)));
  for (const k of ["chainId", "contract", "invoiceId", "merchant", "recipient", "token", "amount", "expiry", "signature"])
    if (r[k] === undefined) throw new Error("Payment request missing " + k);
  return r;
}

function encodeRequest(r, selector) {
  const sig = r.signature.replace(/^0x/i, "");
  const padded = sig.padEnd(Math.ceil(sig.length / 64) * 64, "0");
  return selector + word(r.invoiceId) + word(r.merchant) + word(r.recipient) + word(r.token) +
    uint(r.amount) + uint(r.expiry) + uint(7 * 32) + uint(sig.length / 2) + padded;
}

const address = v => typeof v === "string" && /^0x[0-9a-f]{40}$/i.test(v);
const same = (a, b) => address(a) && address(b) && a.toLowerCase() === b.toLowerCase();

function checkTrustedRequest(r, trust) {
  if (r.chainId !== trust.chainId || !same(r.contract, trust.contract) ||
      !same(r.token, trust.token) || !same(r.merchant, trust.merchant) ||
      !address(r.recipient) || !/^0x[0-9a-f]{64}$/i.test(r.invoiceId) ||
      !/^0x[0-9a-f]{130}$/i.test(r.signature) || !/^[0-9]+$/.test(r.amount) ||
      BigInt(r.amount) <= 0n || BigInt(r.amount) >= (1n << 256n) ||
      !Number.isSafeInteger(r.expiry) || Date.now() / 1000 > r.expiry) {
    throw new Error("Invoice does not match the trusted checkout configuration or has expired.");
  }
}

function abiBytes(hex) {
  return uint(hex.length / 2) + hex.padEnd(Math.ceil(hex.length / 64) * 64, "0");
}

function readWord(hex, offset) {
  const value = hex.slice(offset * 2, offset * 2 + 64);
  if (!/^[0-9a-f]{64}$/i.test(value)) throw new Error("Invalid RPC response.");
  return BigInt("0x" + value);
}

function readBytes(hex, offset) {
  const start = Number(readWord(hex, offset));
  const length = Number(readWord(hex, start));
  if (!Number.isSafeInteger(length) || (start + 32 + length) * 2 > hex.length) throw new Error("Invalid RPC bytes.");
  return hex.slice((start + 32) * 2, (start + 32 + length) * 2);
}

async function resolveEns(ens) {
  const labels = ens.name.split(".");
  const name = labels.map(label => label.length.toString(16).padStart(2, "0") +
    [...label].map(c => c.charCodeAt(0).toString(16)).join("")).join("") + "00";
  async function rpc(method, params = []) {
    const response = await fetch(ens.rpc, {
      method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({jsonrpc: "2.0", id: 1, method, params}),
      signal: AbortSignal.timeout(10000),
    });
    if (!response.ok) throw new Error("ENS RPC unavailable.");
    const reply = await response.json();
    if (reply.error || typeof reply.result !== "string") throw new Error("ENS resolution failed.");
    return reply.result;
  }

  if (Number(await rpc("eth_chainId")) !== ens.chainId) throw new Error("Wrong ENS RPC chain.");
  const block = await rpc("eth_blockNumber");
  async function resolve(selector) {
    const nameArg = abiBytes(name);
    const profile = selector + uint(0) + uint(ens.coinType);
    const data = "0x9061b923" + uint(64) + uint(64 + nameArg.length / 2) + nameArg + abiBytes(profile);
    const result = (await rpc("eth_call", [{to: ens.universalResolver, data}, block])).slice(2);
    if (!same("0x" + result.slice(88, 128), ens.resolver)) throw new Error("Merchant ENS resolver changed.");
    return readBytes(result, 0);
  }
  if (readWord(await resolve("32f111d7"), 0) !== 1n) throw new Error("Merchant has no explicit Whitechain address.");
  return "0x" + readBytes(await resolve("f1cb7e06"), 0);
}

async function checkRecipient(r, trust) {
  const recipient = trust.ens ? await resolveEns(trust.ens) : trust.recipient;
  if (!same(r.recipient, recipient) || /^0x0{40}$/i.test(recipient)) {
    throw new Error("Merchant payment address changed. Request a new invoice.");
  }
}

async function preflight(eth, from, r, trust) {
  checkTrustedRequest(r, trust);
  if (Number(await eth.request({method: "eth_chainId"})) !== trust.chainId) throw new Error("Wallet is on the wrong network.");
  const data = encodeRequest(r, CHECK_SELECTOR);
  const result = (await eth.request({method: "eth_call", params: [{from, to: trust.contract, data}, "latest"]})).slice(2);
  if (readWord(result, 32) !== 1n || readWord(result, 64) !== 0n) {
    throw new Error("Invalid signature or invoice is no longer open.");
  }
  await checkRecipient(r, trust);
  return "0x" + result.slice(0, 64).toLowerCase();
}

async function waitReceipt(eth, hash) {
  for (;;) {
    const rc = await eth.request({ method: "eth_getTransactionReceipt", params: [hash] });
    if (rc) return rc;
    await new Promise((s) => setTimeout(s, 2000));
  }
}

async function pay(r, trust) {
  checkTrustedRequest(r, trust);
  const eth = window.ethereum;
  if (!eth) throw new Error("No browser wallet found. Install a wallet and add Whitechain Sepolia.");
  const [from] = await eth.request({ method: "eth_requestAccounts" });
  const want = "0x" + Number(r.chainId).toString(16);
  if ((await eth.request({ method: "eth_chainId" })) !== want) {
    log("Switching wallet to chain " + r.chainId + "…");
    try { await eth.request({ method: "wallet_switchEthereumChain", params: [{ chainId: want }] }); }
    catch (e) { if (CHAINS[r.chainId]) await eth.request({ method: "wallet_addEthereumChain", params: [CHAINS[r.chainId]] }); else throw e; }
    if ((await eth.request({ method: "eth_chainId" })) !== want) throw new Error("Wallet is on the wrong network.");
  }
  await preflight(eth, from, r, trust);
  log("Approve the exact amount of test USDT…");
  const a = await eth.request({ method: "eth_sendTransaction", params: [{ from, to: trust.token, data: APPROVE_SELECTOR + word(trust.contract) + uint(r.amount) }] });
  if ((await waitReceipt(eth, a)).status !== "0x1") throw new Error("Approval failed.");
  const digest = await preflight(eth, from, r, trust);
  log("Approved. Now confirm the settlement…");
  const s = await eth.request({ method: "eth_sendTransaction", params: [{ from, to: trust.contract, data: encodeRequest(r, SETTLE_SELECTOR) }] });
  log("Submitted: " + s);
  const rc = await waitReceipt(eth, s);
  const ev = rc.status === "0x1" && rc.logs.find((l) => l.address.toLowerCase() === r.contract.toLowerCase() &&
    l.topics[0] === SETTLED_TOPIC && l.topics[1]?.toLowerCase() === "0x" + word(r.invoiceId) &&
    l.topics[2]?.toLowerCase() === digest && l.topics[3]?.toLowerCase() === "0x" + word(from));
  if (!ev) throw new Error("Settlement reverted or no settlement event. Invoice may be paid, cancelled or expired.");
  const confirmation = log("Paid onchain in block " + parseInt(rc.blockNumber, 16) + ". The merchant will verify this receipt.", "ok");
  const ex = CHAINS[r.chainId]?.blockExplorerUrls[0];
  if (ex) { const a2 = document.createElement("a"); a2.href = ex + "/tx/" + s; a2.textContent = "View on explorer"; a2.target = "_blank"; a2.rel = "noopener"; confirmation.append(a2); }
}

async function init() {
  const r = parseReq();
  const response = await fetch("./trust.json", {cache: "no-store"});
  if (!response.ok) throw new Error("Checkout trust configuration is missing.");
  const trust = await response.json();
  checkTrustedRequest(r, trust);
  const units = BigInt(r.amount);
  const scale = 10n ** BigInt(trust.tokenDecimals);
  const fraction = (units % scale).toString().padStart(trust.tokenDecimals, "0").replace(/0+$/, "");
  const amount = (units / scale).toString() + (fraction ? "." + fraction : "");
  $("details").textContent = "";
  const dl = document.createElement("dl");
  for (const [k, v] of [["Merchant", trust.ens?.name ?? trust.merchant], ["Amount", amount + " USDT (test)"],
      ["Chain", (CHAINS[trust.chainId]?.chainName ?? "Local dev") + " (" + trust.chainId + ")"],
      ["Pays to", r.recipient], ["Expires", new Date(r.expiry * 1000).toLocaleString()]]) {
    const dt = document.createElement("dt"); dt.textContent = k; const dd = document.createElement("dd"); dd.textContent = v; dl.append(dt, dd);
  }
  $("details").append(dl);
  await checkRecipient(r, trust);
  $("pay").disabled = false;
  $("pay").onclick = () => {
    $("pay").disabled = true;
    pay(r, trust).catch(e => { log(e.message || String(e), "err"); $("pay").disabled = false; });
  };
}

init().catch(e => log(e.message || String(e), "err"));
