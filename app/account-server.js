import { NextResponse } from "next/server";

export const service = "http://127.0.0.1:8700";
export const accountMode = () => process.env.SENFUND_ACCOUNT_MODE === "1";
export function accountOrigin() {
  const url = new URL(process.env.SENFUND_APP_ORIGIN);
  if (url.origin !== process.env.SENFUND_APP_ORIGIN ||
      (url.protocol !== "https:" && !(url.protocol === "http:" && ["127.0.0.1", "localhost"].includes(url.hostname)))) {
    throw new Error("Invalid SenFund account origin.");
  }
  return url;
}

export function sessionName() {
  return accountOrigin().protocol === "https:" ? "__Host-senfund-session" : "senfund-session";
}

export function bridgeHeaders(request) {
  const secret = process.env.SENFUND_API_BRIDGE_SECRET;
  if (!secret || secret.length < 32) throw new Error("SenFund API bridge is unavailable.");
  const token = request.cookies.get(sessionName())?.value;
  return { "X-SenFund-Bridge": secret, ...(token ? { "X-SenFund-Session": token } : {}) };
}

export function accountCookie(maxAge) {
  return { httpOnly: true, sameSite: "lax", secure: accountOrigin().protocol === "https:", path: "/", maxAge };
}

export function authJson(data, status) {
  return NextResponse.json(data, { status, headers: { "Cache-Control": "no-store" } });
}
