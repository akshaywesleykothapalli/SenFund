"use client";

import { useEffect, useState } from "react";
import Logo from "../logo";
import { AnimatePresence, MotionConfig, motion, useReducedMotion } from "framer-motion";

export default function Login() {
  const reduce = useReducedMotion();
  const [fieldErrors, setFieldErrors] = useState({});
  const [visible, setVisible] = useState(false);
  const [register, setRegister] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    setRegister(new URLSearchParams(window.location.search).get("mode") === "signup");
  }, []);

  async function submit(event) {
    event.preventDefault();
    const body = Object.fromEntries(new FormData(event.currentTarget));
    const fields = event.currentTarget.elements;
    const errors = {};
    if (!body.email?.trim()) errors.email = "Enter your email address.";
    else if (fields.namedItem("email").validity.typeMismatch) errors.email = "Enter a valid email address.";
    if (!body.password || body.password.length < 8 || body.password.length > 128) errors.password = "Use a password of 8 to 128 characters.";
    if (register && body.password !== body.confirmPassword) errors.confirmPassword = "The passwords do not match.";
    setFieldErrors(errors);
    setError("");
    if (Object.keys(errors).length) {
      fields.namedItem(Object.keys(errors)[0]).focus();
      return;
    }
    body.email = body.email.trim();
    delete body.confirmPassword;
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

  function switchMode(next) {
    setRegister(next);
    setFieldErrors({});
    setError("");
    setVisible(false);
    window.history.replaceState(null, "", next ? "/login?mode=signup" : "/login");
  }

  return <MotionConfig reducedMotion="user">
    <div className="authPage">
      <header className="authHeader"><Logo /><a href="/#payment-proof">Explore payment proof ↗</a></header>
      <main className="authLayout">
        <motion.aside className="authArtwork" initial={{ opacity: 0, y: reduce ? 0 : 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: .5 }}>
          <img src="/images/senfund-account.webp" alt="An illustrated invoice ribbon connects a freelancer’s desk to a distant city through an architectural arch." width="1000" height="1250" fetchPriority="high" />
        </motion.aside>
        <motion.section layout="size" transition={{ layout: { duration: reduce ? 0 : .3, ease: [.22, 1, .36, 1] } }} className="authCard" aria-labelledby="auth-title">
          <div className="authMode" aria-label="Account action"><button type="button" aria-pressed={!register} disabled={busy} onClick={() => switchMode(false)}>{!register && <motion.span className="authTabPill" layoutId="auth-tab" transition={{type:"spring",stiffness:380,damping:34}} />}<span>Log in</span></button><button type="button" aria-pressed={register} disabled={busy} onClick={() => switchMode(true)}>{register && <motion.span className="authTabPill" layoutId="auth-tab" transition={{type:"spring",stiffness:380,damping:34}} />}<span>Create account</span></button></div>
          <motion.div layout="position">
            <p className="eyebrow">{register ? "Start with SenFund" : "Your merchant workspace"}</p>
            <h2 id="auth-title">{register ? "Make room for your next invoice." : "Welcome back."}</h2>
            <p className="authSubtitle">{register ? "Create a local account to organize invoices and link your wallets." : "Log in to follow your invoices, payments and wallet records."}</p>
            <form onSubmit={submit} noValidate onInput={event => {
              const name = event.target.name;
              if (fieldErrors[name]) setFieldErrors(current => ({ ...current, [name]: "" }));
            }}>
              <fieldset disabled={busy} className="authFields">
                <label>Email address<input id="auth-email" type="email" name="email" autoComplete="email" autoCapitalize="none" spellCheck={false} placeholder="you@example.com" maxLength={254} required aria-invalid={!!fieldErrors.email} aria-describedby={fieldErrors.email ? "email-error" : undefined} />{fieldErrors.email && <small className="fieldError" id="email-error">{fieldErrors.email}</small>}</label>
                <label>Password<span className="passwordField"><input type={visible ? "text" : "password"} name="password" aria-invalid={!!fieldErrors.password} aria-describedby={fieldErrors.password ? "password-error" : register ? "password-help" : undefined} autoComplete={register ? "new-password" : "current-password"} minLength={8} maxLength={128} placeholder={register ? "Choose a password" : "Enter your password"} required /><button type="button" aria-label={visible ? "Hide password" : "Show password"} aria-pressed={visible} onClick={() => setVisible(!visible)}>{visible ? "Hide" : "Show"}</button></span>{fieldErrors.password ? <small className="fieldError" id="password-error">{fieldErrors.password}</small> : register && <small id="password-help">Use 8 to 128 characters.</small>}</label>
                <AnimatePresence initial={false}>{register && <motion.div key="confirm" initial={{height: reduce ? "auto" : 0, opacity:0}} animate={{height:"auto",opacity:1}} exit={{height:reduce ? "auto" : 0,opacity:0}} transition={{duration:reduce ? 0 : .25,ease:[.22,1,.36,1]}} style={{overflow:"hidden"}}>
                  <label>Confirm password<input type={visible ? "text" : "password"} name="confirmPassword" aria-invalid={!!fieldErrors.confirmPassword} aria-describedby={fieldErrors.confirmPassword ? "confirm-error" : undefined} autoComplete="new-password" minLength={8} maxLength={128} placeholder="Enter it once more" required />{fieldErrors.confirmPassword && <small className="fieldError" id="confirm-error">{fieldErrors.confirmPassword}</small>}</label>
                </motion.div>}</AnimatePresence>
              </fieldset>
              {error && <p role="alert" className="alert">{error}</p>}
              <motion.button whileTap={{ scale: .99 }} className="primary authSubmit" disabled={busy}>{busy ? "Please wait…" : register ? "Create account" : "Log in"} <span aria-hidden="true">↗</span></motion.button>
            </form>
          </motion.div>
          <p className="authSwitch">{register ? "Already have an account?" : "New to SenFund?"} <button type="button" disabled={busy} onClick={() => switchMode(!register)}>{register ? "Log in" : "Create an account"}</button></p>
          <p className="authLocalNote">Local demo account. Stored by this SenFund instance. Wallet ownership is verified separately with a message signature.</p>
        </motion.section>
      </main>
      <footer className="authFooter"><span>Whitechain Sepolia · Test assets only</span><a href="/">← Back to SenFund</a></footer>
    </div>
  </MotionConfig>;
}
