import * as oidc from "openid-client";
import { NextResponse } from "next/server";
import { accountCookie, accountMode, accountOrigin, authJson, bridgeHeaders, localAuthMode, service, sessionName } from "../../../account-server";

const flowName = () => accountOrigin().protocol === "https:" ? "__Host-senfund-oidc" : "senfund-oidc";
const callbackUrl = () => new URL("/api/auth/callback", accountOrigin());

async function provider() {
  const issuer = new URL(process.env.SENFUND_OIDC_ISSUER);
  if (issuer.protocol !== "https:" || !process.env.SENFUND_OIDC_CLIENT_ID || !process.env.SENFUND_OIDC_CLIENT_SECRET) {
    throw new Error("OIDC is not configured.");
  }
  return oidc.discovery(issuer, process.env.SENFUND_OIDC_CLIENT_ID, process.env.SENFUND_OIDC_CLIENT_SECRET,
    undefined, { execute: [oidc.enableNonRepudiationChecks] });
}

function redirect(url) {
  return NextResponse.redirect(url, { headers: { "Cache-Control": "no-store", "Referrer-Policy": "no-referrer" } });
}

export async function GET(request, { params }) {
  if (!accountMode()) return authJson({ error: "Account mode is disabled." }, 404);
  const { action } = await params;
  if (localAuthMode()) {
    if (action === "sign-in") return redirect(new URL("/login", accountOrigin()));
    return authJson({ error: "Page not found." }, 404);
  }
  if (action !== "sign-in" && action !== "callback") return authJson({ error: "Page not found." }, 404);

  try {
    const config = await provider();
    if (action === "sign-in") {
      const flow = { verifier: oidc.randomPKCECodeVerifier(), state: oidc.randomState(), nonce: oidc.randomNonce() };
      const response = redirect(oidc.buildAuthorizationUrl(config, {
        redirect_uri: callbackUrl().href,
        scope: "openid email",
        max_age: "300",
        code_challenge_method: "S256",
        code_challenge: await oidc.calculatePKCECodeChallenge(flow.verifier),
        state: flow.state,
        nonce: flow.nonce,
      }));
      response.cookies.set(flowName(), JSON.stringify(flow), accountCookie(600));
      return response;
    }

    const rawFlow = request.cookies.get(flowName())?.value;
    if (!rawFlow) return authJson({ error: "Sign-in expired. Start again from the workspace." }, 400);
    const flow = JSON.parse(rawFlow);
    const callback = callbackUrl();
    callback.search = new URL(request.url).search;
    const tokens = await oidc.authorizationCodeGrant(config, callback, {
      pkceCodeVerifier: flow.verifier, expectedState: flow.state, expectedNonce: flow.nonce, maxAge: 300,
    });
    const identity = tokens.claims();
    if (!identity?.sub) throw new Error("Missing identity subject.");
    const profile = identity.email_verified === true && identity.email
      ? identity : await oidc.fetchUserInfo(config, tokens.access_token, identity.sub);
    const upstream = await fetch(service + "/api/session/sign-in", {
      method: "POST",
      headers: { ...bridgeHeaders(request), "Content-Type": "application/json" },
      body: JSON.stringify({ iss: identity.iss, sub: identity.sub, email: profile.email, email_verified: profile.email_verified, auth_time: identity.auth_time }),
      cache: "no-store",
      signal: AbortSignal.timeout(5000),
    });
    if (!upstream.ok) throw new Error("Identity rejected.");
    const { token } = await upstream.json();
    const response = redirect(new URL("/workspace", accountOrigin()));
    response.cookies.set(flowName(), "", accountCookie(0));
    response.cookies.set(sessionName(), token, accountCookie(8 * 3600));
    return response;
  } catch {
    const response = authJson({ error: "Sign-in could not be completed. Confirm your email with the identity provider and start again." }, 401);
    try { response.cookies.set(flowName(), "", accountCookie(0)); } catch {}
    return response;
  }
}

export async function POST(request, { params }) {
  const { action } = await params;
  const passwordAction = localAuthMode() && ["sign-in", "sign-up"].includes(action);
  if (!accountMode() || (action !== "sign-out" && !passwordAction)) return authJson({ error: "Page not found." }, 404);
  try {
    if (request.headers.get("origin") !== accountOrigin().origin) {
      return authJson({ error: "Open the local SenFund workspace." }, 403);
    }
    if (Number(request.headers.get("content-length")) > 2048) return authJson({ error: "Request too large." }, 413);
    const raw = await request.text();
    if (raw.length > 2048) return authJson({ error: "Request too large." }, 413);
    let body;
    try { body = JSON.parse(raw); }
    catch { return authJson({ error: "Enter valid account details." }, 400); }
    const fields = passwordAction ? { email: body?.email, password: body?.password } : { allSessions: body?.allSessions === true };
    const upstream = await fetch(service + "/api/session/" + action, {
      method: "POST",
      headers: { ...bridgeHeaders(request), "Content-Type": "application/json" },
      body: JSON.stringify(fields),
      cache: "no-store",
      signal: AbortSignal.timeout(5000),
    });
    if (passwordAction) {
      const data = await upstream.json();
      if (!upstream.ok) return authJson({ error: data.error || "Unable to sign in." }, upstream.status);
      const response = authJson({ signedIn: true }, 200);
      response.cookies.set(sessionName(), data.token, accountCookie(8 * 3600));
      return response;
    }
    if (!upstream.ok && upstream.status !== 401) throw new Error("Session could not be revoked.");
    const response = authJson({ signedOut: true }, 200);
    response.cookies.set(sessionName(), "", accountCookie(0));
    return response;
  } catch {
    return authJson({ error: "The local account service is unavailable. Try again." }, 503);
  }
}
