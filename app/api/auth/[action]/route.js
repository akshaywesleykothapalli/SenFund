import * as oidc from "openid-client";
import { NextResponse } from "next/server";
import { accountCookie, accountMode, accountOrigin, authJson, bridgeHeaders, service, sessionName } from "../../../account-server";

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
  if (!accountMode() || (await params).action !== "sign-out") return authJson({ error: "Page not found." }, 404);
  try {
    if (request.headers.get("origin") !== accountOrigin().origin) {
      return authJson({ error: "Open the SenFund workspace to sign out." }, 403);
    }
    const body = await request.json();
    const upstream = await fetch(service + "/api/session/sign-out", {
      method: "POST",
      headers: { ...bridgeHeaders(request), "Content-Type": "application/json" },
      body: JSON.stringify({ allSessions: body?.allSessions === true }),
      cache: "no-store",
      signal: AbortSignal.timeout(5000),
    });
    if (!upstream.ok && upstream.status !== 401) throw new Error("Session could not be revoked.");
    const response = authJson({ signedOut: true }, 200);
    response.cookies.set(sessionName(), "", accountCookie(0));
    return response;
  } catch {
    return authJson({ error: "Unable to sign out. Try again." }, 503);
  }
}
