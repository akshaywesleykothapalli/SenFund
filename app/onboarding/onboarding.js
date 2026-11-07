"use client";

import { useEffect, useState } from "react";

async function api(path, body) {
  const response = await fetch("/api/" + path, { cache: "no-store",
    ...(body ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) } : {}) });
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || "SenFund could not complete the request.");
  return result;
}

export default function Onboarding() {
  const [step, setStep] = useState(1);
  const [role, setRole] = useState("payee");
  const [corridor, setCorridor] = useState("IN");
  const [config, setConfig] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => { api("config").then(setConfig).catch(e => setError(e.message)); }, []);

  async function act(fn) {
    setBusy(true); setError("");
    try { await fn(); } catch (e) { setError(e.message); } finally { setBusy(false); }
  }

  const save = () => act(async () => { await api("profile", { role, corridor }); setStep(3); });

  // The user signs in their own wallet; nothing is signed automatically.
  const sign = () => act(async () => {
    const wallet = window.ethereum;
    if (!wallet) throw new Error("Open this page in a browser with a supported Ethereum wallet.");
    const [address] = await wallet.request({ method: "eth_requestAccounts" });
    const chain = "0x" + config.chainId.toString(16);
    if (await wallet.request({ method: "eth_chainId" }) !== chain)
      await wallet.request({ method: "wallet_switchEthereumChain", params: [{ chainId: chain }] });
    const proof = await api("wallets/challenge", { address, purpose: role === "payee" ? "signer" : "recipient" });
    const hex = "0x" + Array.from(new TextEncoder().encode(proof.message), b => b.toString(16).padStart(2, "0")).join("");
    const signature = await wallet.request({ method: "personal_sign", params: [hex, address] });
    await api("wallets/verify", { challenge: proof.challenge, signature });
    setStep(4);
  });

  return <main>
    <header className="heading"><div><h1>Set up SenFund</h1><p>Step {step} of 4</p></div></header>
    {error && <p className="error" role="alert">{error}</p>}
    {step === 1 && <fieldset><legend>Are you paid or paying?</legend>
      {[["payee", "I get paid (merchant)"], ["payer", "I pay invoices"]].map(([v, t]) =>
        <label key={v}><input type="radio" name="role" checked={role === v} onChange={() => setRole(v)} /> {t}</label>)}
      <button className="button primary" onClick={() => setStep(2)}>Next</button></fieldset>}
    {step === 2 && <fieldset><legend>Payout corridor</legend>
      {Object.entries(config?.corridors || { IN: { currency: "INR" }, EU: { currency: "EUR" } }).map(([v, c]) => [v, `${v} (${c.currency})`]).map(([v, t]) =>
        <label key={v}><input type="radio" name="corridor" checked={corridor === v} onChange={() => setCorridor(v)} /> {t}</label>)}
      <button className="button primary" disabled={busy} onClick={save}>Save</button></fieldset>}
    {step === 3 && <fieldset><legend>Verify your wallet</legend>
      <p>Your wallet asks you to sign a message. It costs no gas.</p>
      <button className="button primary" disabled={busy || !config} onClick={sign}>Connect and sign</button></fieldset>}
    {step === 4 && <section><h2>You are set up</h2>
      {config?.ensName && <p>Pay this merchant at <strong>{config.ensName}</strong>.</p>}
      <a className="button primary" href="/">Done</a></section>}
  </main>;
}
