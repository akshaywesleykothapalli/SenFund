const service = "http://127.0.0.1:8700";
const invoiceId = "inv_[a-f0-9]{12}";
const readRoute = new RegExp(`^(config|invoices(?:/${invoiceId}(?:/receipt)?)?)$`);
const writeRoute = new RegExp(`^invoices(?:/${invoiceId}/(submit|verify|convert|payout|simulate-p2p-credit))?$`);
const scenarios = new Set(["success", "mudrex_unavailable", "timeout", "timeout_created", "fail"]);

function json(data, status = 200) {
  return Response.json(data, { status, headers: { "Cache-Control": "no-store" } });
}

function invoiceView(invoice) {
  return {
    id: invoice.id,
    usd: invoice.usd,
    customer: invoice.data?.customer,
    description: invoice.data?.description,
    payment: invoice.payment,
    conversion: invoice.conversion,
    payout: invoice.payout,
    needsReview: Boolean(invoice.needs_review),
    createdAt: invoice.created_at,
    expiresAt: invoice.request?.expiry,
    recipient: invoice.request?.recipient,
    txHash: invoice.tx_hash,
    checkout: invoice.checkout,
    receipt: invoice.receipt && {
      block: invoice.receipt.block_number,
      payer: invoice.receipt.payer,
      txHash: invoice.receipt.tx_hash,
    },
    history: invoice.history,
    operations: invoice.operations.map(({ stage, status, external_id, detail }) => ({
      stage, status, reference: external_id, detail: JSON.parse(detail),
    })),
  };
}

function validateWrite(path, body) {
  if (!body || typeof body !== "object" || Array.isArray(body)) throw new Error("Enter valid invoice details.");
  if (path === "invoices") {
    const { usd, customer, description } = body;
    if (typeof usd !== "string" || !/^\d{1,22}(\.\d{1,2})?$/.test(usd) || !/[1-9]/.test(usd)) {
      throw new Error("Enter a positive USD amount with up to two decimal places.");
    }
    if (typeof customer !== "string" || !customer.trim() || customer.trim().length > 100) {
      throw new Error("Enter the client name using up to 100 characters.");
    }
    if (typeof description !== "string" || !description.trim() || description.trim().length > 200) {
      throw new Error("Enter the service description using up to 200 characters.");
    }
    return { usd, customer: customer.trim(), description: description.trim() };
  }
  if (path.endsWith("/submit")) {
    if (typeof body.tx_hash !== "string" || !/^0x[\da-f]{64}$/i.test(body.tx_hash.trim())) {
      throw new Error("Enter the complete Whitechain payment transaction hash.");
    }
    return { tx_hash: body.tx_hash.trim() };
  }
  if (path.endsWith("/payout")) {
    if (!scenarios.has(body.scenario)) throw new Error("Select a payout simulation scenario.");
    return { scenario: body.scenario };
  }
  return {};
}

async function handle(request, context) {
  const { path: segments } = await context.params;
  const path = segments.join("/");
  const write = request.method === "POST";
  if (!(write ? writeRoute : readRoute).test(path)) return json({ error: "Page not found." }, 404);
  let body;
  const key = path === "invoices" && write ? request.headers.get("idempotency-key") : null;
  if (key !== null && !/^[A-Za-z0-9._-]{1,128}$/.test(key)) return json({ error: "Invalid Idempotency-Key header." }, 400);
  if (write) {
    const host = request.headers.get("host") ?? "";
    const origin = request.headers.get("origin");
    if (!/^(localhost|127\.0\.0\.1)(:\d+)?$/.test(host) || origin !== `http://${host}`) {
      return json({ error: "Open the local SenFund dashboard to make changes." }, 403);
    }
    if (Number(request.headers.get("content-length")) > 8192) {
      return json({ error: "The request is too large." }, 413);
    }
    try {
      const text = await request.text();
      if (text.length > 8192) return json({ error: "The request is too large." }, 413);
      body = JSON.stringify(validateWrite(path, JSON.parse(text)));
    } catch (error) {
      return json({ error: error instanceof SyntaxError ? "The request must be valid JSON." : error.message }, 400);
    }
  }
  try {
    const upstream = await fetch(`${service}/api/${path}`, {
      method: request.method,
      headers: write ? { "Content-Type": "application/json", ...(key ? { "Idempotency-Key": key } : {}) } : undefined,
      body,
      cache: "no-store",
      redirect: "error",
      signal: AbortSignal.timeout(path.endsWith("/payout") ? 135_000 : 30_000),
    });
    if (upstream.ok && path.endsWith("/receipt")) {
      return new Response(upstream.body, {
        headers: {
          "Content-Type": "text/html; charset=utf-8",
          "Content-Disposition": upstream.headers.get("content-disposition") ?? "attachment",
          "Cache-Control": "no-store",
        },
      });
    }
    const payload = await upstream.json();
    if (!upstream.ok) return json({ error: payload.error || "The settlement service rejected this request." }, upstream.status);
    if (path === "config") return json(payload);
    if (Array.isArray(payload)) return json(payload.map(invoiceView));
    if (payload.invoice) {
      return json({ ...payload, invoice: invoiceView(payload.invoice) }, upstream.status);
    }
    return json(invoiceView(payload), upstream.status);
  } catch {
    return json({ error: "The local settlement service is unavailable. Check that it is running and try again." }, 503);
  }
}

export const GET = handle;
export const POST = handle;
