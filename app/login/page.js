"use client";

import { useEffect, useState } from "react";

export default function Login() {
  const [register, setRegister] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    setRegister(new URLSearchParams(window.location.search).get("mode") === "signup");
  }, []);

  async function submit(event) {
    event.preventDefault();
    const body = Object.fromEntries(new FormData(event.currentTarget));
    setBusy(true);
    setError("");
    try {
      const response = await fetch("/api/auth/" + (register ? "sign-up" : "sign-in"), {
        method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body),
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error);
      window.location.assign("/workspace");
    } catch (reason) {
      setError(reason.message || "Unable to sign in.");
      setBusy(false);
    }
  }

  return <main className="localLogin">
    <a className="wordmark" href="/">SenFund</a>
    <form className="invoiceForm" onSubmit={submit}>
      <div className="sectionTitle">
        <h1>{register ? "Create an account" : "Log in"}</h1>
        <p>{register ? "Save your profile and wallet links on this Mac." : "Open your local SenFund workspace."}</p>
      </div>
      <fieldset className="fields">
        <label className="wide">Email<input type="email" name="email" autoComplete="email" maxLength={254} required /></label>
        <label className="wide">Password<input type="password" name="password" autoComplete={register ? "new-password" : "current-password"} minLength={8} maxLength={128} required /></label>
      </fieldset>
      {error && <p role="alert" className="alert">{error}</p>}
      <div className="formFooter">
        <button type="button" disabled={busy} onClick={() => { setRegister(!register); setError(""); }}>{register ? "Already have an account?" : "Create an account"}</button>
        <button className="primary" disabled={busy}>{busy ? "Please wait…" : register ? "Sign up" : "Log in"}</button>
      </div>
    </form>
  </main>;
}
