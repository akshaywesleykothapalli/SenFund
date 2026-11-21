"""SenFund merchant app: dashboard (web/) + JSON API + background verifier. stdlib http.server only."""
import base64
import json
import hmac
import secrets
import re
from decimal import Decimal
from functools import partial
from pathlib import Path
from tempfile import TemporaryDirectory
import threading
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse, urlsplit

from . import cre_payout, drafter, ens

from .accounts import Accounts
from .local_accounts import LocalAccounts
from .adapters import CORRIDORS
from .config import ROOT, load, setting, web3_for
from .state import InvalidTransition
from .service import InvoiceCreationConflict, SenFund, draft_note

LOCK = threading.Lock()  # service calls are short; one at a time keeps state transitions simple


ADDRESS = re.compile(r"^0x[0-9a-fA-F]{40}$")


def checkout_origin():
    url = setting("SENFUND_CHECKOUT_URL", "http://localhost:8702/")
    parts = urlsplit(url)
    if (not parts.hostname or parts.username or parts.password or parts.query or parts.fragment
            or (parts.scheme != "https" and not (parts.scheme == "http" and parts.hostname in {"127.0.0.1", "localhost"}))):
        raise ValueError("Configure an HTTPS checkout URL or a local loopback URL.")
    return url.rstrip("/") + "/"


def balance(cfg, address):
    """Read-only testnet balances for one address: native gas coin and the settlement token."""
    if not ADDRESS.match(address or ""):
        raise ValueError("Enter a valid 0x wallet address.")
    w3 = web3_for(cfg)
    addr = w3.to_checksum_address(address)
    native = w3.eth.get_balance(addr)
    data = "0x70a08231" + addr[2:].lower().rjust(64, "0")
    tokens = {}
    for name, (token, decimals) in cfg.payment_assets.items():
        raw = int.from_bytes(w3.eth.call({"to": w3.to_checksum_address(token), "data": data}), "big")
        tokens["WWBT" if name == "WBT" else name] = format(Decimal(raw).scaleb(-decimals), "f")
    return {"address": addr, "chainId": cfg.chain_id, "native": format(Decimal(native).scaleb(-18), "f"),
            "token": tokens["USDT"], "tokens": tokens}


def treasury(app, owner, legacy_only):
    address = ens.resolve_recipient(app.cfg) if app.cfg.env == "testnet" else app.cfg.recipient
    wallet = balance(app.cfg, address)
    totals = {asset: 0 for asset in wallet["tokens"]}
    payments = []
    for invoice in app.list(owner, legacy_only=legacy_only):
        receipt = invoice["receipt"]
        recipient = invoice["request"]["recipient"]
        if invoice["payment"] != "PAID" or not receipt or invoice["needs_review"] or recipient.lower() != address.lower():
            continue
        asset = "WWBT" if invoice["asset"] == "WBT" else "USDT"
        decimals = app.cfg.payment_assets[invoice["asset"]][1]
        units = int(receipt["amount"])
        totals[asset] += units
        verified = next((row["at"] for row in reversed(invoice["history"])
                         if row["stage"] == "payment" and row["new"] == "PAID"), None)
        payments.append({"invoice": invoice["id"], "customer": invoice["data"].get("customer") or "",
                         "payer": receipt["payer"], "recipient": recipient, "asset": asset,
                         "amount": format(Decimal(units).scaleb(-decimals).normalize(), "f"),
                         "txHash": receipt["tx_hash"], "block": receipt["block_number"], "verifiedAt": verified})
    payments.sort(key=lambda payment: (payment["block"], payment["verifiedAt"] or 0), reverse=True)
    received = {asset: format(Decimal(units).scaleb(-app.cfg.payment_assets["WBT" if asset == "WWBT" else asset][1]).normalize(), "f")
                for asset, units in totals.items()}
    return {**wallet, "ensName": app.cfg.ens_name, "explorer": app.cfg.explorer, "received": received, "payments": payments}


def checkout_link(app, inv):
    raw = json.dumps(app.checkout_request(inv), separators=(",", ":")).encode()
    return checkout_origin() + "#req=" + base64.urlsafe_b64encode(raw).decode().rstrip("=")


def make_handler(app, accounts=None, *, payout_runner=cre_payout.run, local_ccip=False, evidence_key=""):
    class H(SimpleHTTPRequestHandler):
        def __init__(self, *a, **k):
            super().__init__(*a, directory=str(ROOT / "web"), **k)

        def log_message(self, *a):
            pass

        def _json(self, code, body):
            data = json.dumps(body, default=str).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _route(self, method):
            parts = urlparse(self.path).path.strip("/").split("/")
            if parts[0] != "api":
                if accounts:
                    return self._json(404, {"error": "Use the SenFund web workspace."})
                return super().do_GET() if method == "GET" else self._json(404, {"error": "not found"})
            internal = (bool(evidence_key) and method == "GET" and len(parts) == 4 and parts[1] == "cre"
                        and parts[2] in {"receipt", "provider"}
                        and hmac.compare_digest(self.headers.get("X-SenFund-Evidence", "").encode(), evidence_key.encode()))
            if accounts and not internal and not accounts.trusted_bridge(self.headers.get("X-SenFund-Bridge", "")):
                return self._json(401, {"error": "Unauthorized."})
            body = {}
            if method == "POST":
                try:
                    n = int(self.headers.get("Content-Length") or 0)
                    if n < 0:
                        raise ValueError("negative body length")
                    if n > 65536:
                        return self._json(413, {"error": "too large"})
                    body = json.loads(self.rfile.read(n) or b"{}")
                except (ValueError, UnicodeError):
                    return self._json(400, {"error": "Expected a JSON object."})
                if not isinstance(body, dict):
                    return self._json(400, {"error": "Expected a JSON object."})
            try:
                actor = None
                merchant_admin = False
                if accounts and not internal:
                    path = parts[1:]
                    if path == ["session", "sign-in"] and method == "POST":
                        return self._json(201, {"token": accounts.sign_in(body)})
                    if isinstance(accounts, LocalAccounts) and path == ["session", "sign-up"] and method == "POST":
                        return self._json(201, {"token": accounts.authenticate(body, register=True)})
                    token = self.headers.get("X-SenFund-Session", "")
                    actor = accounts.actor(token)
                    if actor is None:
                        return self._json(401, {"error": "Sign in to access your workspace."})
                    merchant_admin = isinstance(accounts, LocalAccounts) and accounts.can_issue(actor)
                    if path == ["wallets"] and method == "GET":
                        return self._json(200, accounts.wallets(actor))
                    if path == ["wallets", "challenge"] and method == "POST":
                        origin = setting("SENFUND_APP_ORIGIN", "http://127.0.0.1:3000")
                        return self._json(201, accounts.wallet_challenge(actor, token, body, origin, app.cfg.chain_id))
                    if path == ["wallets", "verify"] and method == "POST":
                        return self._json(200, accounts.verify_wallet(actor, token, body))
                    if path == ["profile"]:
                        profile = (accounts.profile(actor) if method == "GET"
                                   else accounts.update_prefs(actor, body.get("role"), body.get("corridor"))
                                   if "corridor" in body
                                   else accounts.update_profile(actor, body.get("displayName")))
                        return self._json(200, profile)
                    if method == "POST" and path == ["session", "sign-out"]:
                        accounts.sign_out(token, actor, body.get("allSessions") is True)
                        return self._json(200, {"signedOut": True})
                    if not path or path[0] not in {"invoices", "config", "cre", "draft-invoice", "draft-note", "balance", "treasury"}:
                        return self._json(404, {"error": "not found"})
                    if path[0] == "invoices" and len(path) >= 2 and not merchant_admin:
                        accounts.require_owner(path[1], actor["id"])
                    if path[0] == "cre":
                        accounts.require_owner(path[2] if len(path) >= 3 else "", actor["id"])
                    if path == ["invoices"] and method == "POST" and not accounts.can_issue(actor):
                        return self._json(403, {"error": "This account is not enrolled to sign invoices."})
                if not accounts and len(parts) >= 3 and parts[1] in {"invoices", "cre"}:
                    invoice = parts[2] if parts[1] == "invoices" else parts[3] if len(parts) >= 4 else ""
                    if app.db.one("select 1 from invoice_owners where invoice=?", invoice):
                        return self._json(404, {"error": "unknown invoice"})
                if parts[1:] == ["draft-invoice"]:
                    if method == "GET":
                        return self._json(200, {"enabled": drafter.enabled()})
                    return self._json(200, drafter.draft_invoice(body.get("text")))
                if parts[1:] == ["draft-note"] and method == "POST":
                    return self._json(200, {"note": draft_note(str(body.get("payer", "")), str(body.get("amount", "")), str(body.get("description", "")))})
                if method == "POST" and len(parts) == 4 and parts[1] == "invoices" and parts[3] == "cash-out":
                    if accounts and not accounts.can_issue(actor):
                        return self._json(403, {"error": "Only the merchant operator can request cash-out."})
                    invoice, corridor = parts[2], body.get("corridor")
                    confirmed = body.get("confirm")
                    if type(confirmed) is not bool:
                        raise ValueError("Choose whether to preview or confirm this cash-out.")
                    with LOCK:
                        if not confirmed:
                            return self._json(200, app.quote_cash_out(invoice, corridor))
                        if not app.prepare_cash_out(invoice, corridor):
                            return self._json(200, app.get(invoice))
                        if not app.cfg.cre_payouts:
                            return self._json(200, app.run_payout(invoice, "mudrex_unavailable"))
                    return self._json(200, payout_runner(app, LOCK, invoice, "mudrex_unavailable"))
                if app.cfg.cre_payouts and method == "POST" and len(parts) == 4 and parts[1] == "invoices" and parts[3] == "payout":
                    result = payout_runner(app, LOCK, parts[2], body.get("scenario", "success"))
                    return self._json(200, result)
                if method == "GET" and parts[1:] == ["treasury"]:
                    if accounts and not accounts.can_issue(actor):
                        return self._json(403, {"error": "Merchant wallet access is restricted to the operator."})
                    owner = None if merchant_admin or not actor else actor["id"]
                    return self._json(200, treasury(app, owner, legacy_only=actor is None))
                if method == "GET" and len(parts) == 3 and parts[1] == "balance":  # network read; keep outside LOCK
                    try:
                        return self._json(200, balance(app.cfg, parts[2]))
                    except ValueError:
                        raise
                    except Exception:
                        return self._json(502, {"error": "Could not reach the Whitechain testnet RPC."})
                with LOCK:
                    return self._dispatch(method, parts[1:], body, actor, merchant_admin)
            except InvoiceCreationConflict as error:
                return self._json(409, {"error": str(error)})
            except KeyError:
                return self._json(404, {"error": "unknown invoice"})  # KeyError from service = missing row
            except (ValueError, RuntimeError) as e:
                return self._json(400, {"error": str(e)})
            except InvalidTransition as e:
                return self._json(409, {"error": str(e)})
            except Exception:  # never leak internals to the client
                return self._json(500, {"error": "Something went wrong."})

        def _dispatch(self, method, p, body, actor, merchant_admin):
            if p == ["config"]:
                c = app.cfg
                return self._json(200, {"env": c.env, "chainId": c.chain_id, "explorer": c.explorer, "settlement": c.settlement,
                                        "token": c.token, "merchant": app.merchant, "recipient": c.recipient,
                                        "confirmations": c.confirmations, "ensName": c.ens_name, "crePayouts": c.cre_payouts, "localCcip": local_ccip,
                                        "livePayouts": False, "mainnet": False, "paymentAssets": list(c.payment_assets),
                                        "corridors": {k: {"currency": v["currency"], "rate": str(v["rate"]), "fee": str(v["fee"]), "note": v["note"]}
                                                      for k, v in CORRIDORS.items()}})
            if app.cfg.cre_payouts and method == "GET" and len(p) == 3 and p[0] == "cre":
                if p[1] == "receipt":
                    return self._json(200, cre_payout.receipt_evidence(app, p[2]))
                if p[1] == "provider":
                    scenario = parse_qs(urlparse(self.path).query).get("scenario", ["success"])[0]
                    return self._json(200, cre_payout.provider_evidence(app, p[2], scenario))
            if p == ["invoices"] and method == "GET":
                return self._json(200, app.list(actor["id"] if actor and not merchant_admin else None, legacy_only=actor is None))
            if p == ["invoices"] and method == "POST":
                description = body.get("description", "Invoice")
                customer = body.get("customer", "")
                if not isinstance(description, str) or not isinstance(customer, str):
                    raise ValueError("Invoice description and customer must be text.")
                inv = app.create_invoice(body.get("usd", ""), description[:200], customer[:100],
                                         idempotency_key=self.headers.get("Idempotency-Key"),
                                         owner=actor["id"] if actor else None,
                                         corridor=body.get("corridor", "IN"), asset=body.get("asset", "USDT"))
                return self._json(201, {**inv, "checkout": checkout_link(app, inv["id"])})
            if p == ["callbacks", "remittance"] and method == "POST":
                return self._json(200, {"result": app.provider_callback(body["event_id"], body["order_id"], body["status"])})
            if len(p) >= 2 and p[0] == "invoices":
                inv, action = p[1], (p[2] if len(p) > 2 else "")
                if method == "GET" and action == "":
                    return self._json(200, {**app.get(inv), "checkout": checkout_link(app, inv)})
                if method == "GET" and action == "checkout-request":
                    return self._json(200, app.checkout_request(inv))
                if method == "GET" and action == "evidence":
                    return self._json(200, app.evidence_pack(inv))
                if method == "GET" and action == "receipt":
                    data = app.receipt_html(inv).encode()
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Content-Disposition", f'inline; filename="senfund-receipt-{inv}.html"')
                    self.end_headers()
                    return self.wfile.write(data)
                if method == "POST" and action == "submit":
                    return self._json(200, app.submit_tx(inv, body.get("tx_hash", ""), source="api"))
                if method == "POST" and action == "verify":
                    return self._json(200, app.verify(inv))
                if method == "POST" and action == "convert":
                    return self._json(200, app.run_conversion(inv))
                if method == "POST" and action == "payout" and not app.cfg.cre_payouts:
                    return self._json(200, app.run_payout(inv, body.get("scenario", "success")))
                if method == "POST" and action == "simulate-p2p-credit":
                    return self._json(200, app.confirm_p2p_credit(inv))
            if p == ["reconcile"] and method == "POST":
                start = int(body["from_block"]) if "from_block" in body else None
                return self._json(200, {"recovered": app.reconcile(start)})
            return self._json(404, {"error": "not found"})

        do_GET = lambda self: self._route("GET")
        do_POST = lambda self: self._route("POST")
    return H


def verifier_loop(app, every=5):
    """Recovers payments made while the app was down, confirms pending ones, and detects reorgs."""
    while True:
        try:
            with LOCK:
                app.recheck()
                app.reconcile(prioritize_recent=True)
                for r in app.db.q("select id from invoices where payment='SUBMITTED'"):
                    app.verify(r["id"])
        except Exception as e:
            print("verifier:", e)
        time.sleep(every)


def make_server(app, accounts=None, *, port=8700, local_ccip=False):
    address = ("127.0.0.1", port)
    cfg = app.cfg
    private_cre = isinstance(accounts, LocalAccounts) and cfg.cre_payouts
    if not local_ccip and not private_cre:
        return ThreadingHTTPServer(address, make_handler(app, accounts))
    if (cfg.env != "testnet" or not cfg.cre_payouts or (accounts is not None and not private_cre)
            or not (cfg.ens_name and cfg.ens_resolver and cfg.ens_rpc)):
        raise ValueError("Local CRE needs testnet mode, enabled CRE and ENSv2 settings in the local operator workspace.")

    authorize = None
    if local_ccip:
        from .ccip_local import LocalPayoutRelay
        authorize = LocalPayoutRelay().authorize
    evidence_key = secrets.token_urlsafe(32) if private_cre else ""

    def run_payout(app, lock, invoice, scenario):
        with TemporaryDirectory(prefix="senfund-browser-cre-") as tmp:
            config = Path(tmp) / "config.json"
            config.write_text(json.dumps({"evidenceOrigin": f"http://127.0.0.1:{server.server_port}", "evidenceKey": evidence_key}))
            simulator = partial(cre_payout.simulate, config=config)
            return cre_payout.run(app, lock, invoice, scenario, simulator=simulator, authorize=authorize)

    server = ThreadingHTTPServer(address, make_handler(app, accounts, payout_runner=run_payout, local_ccip=local_ccip, evidence_key=evidence_key))
    return server


def main():
    cfg = load()
    app = SenFund(cfg)
    accounts = None
    if setting("SENFUND_LOCAL_AUTH") == "1":
        accounts = LocalAccounts(app.db, setting("SENFUND_API_BRIDGE_SECRET", ""),
                                 setting("SENFUND_LOCAL_ADMIN_PASSWORD_HASH", ""))
    elif setting("SENFUND_ACCOUNT_MODE") == "1":
        if cfg.cre_payouts:
            raise ValueError("Disable the local CRE runner before enabling account mode.")
        accounts = Accounts(app.db, setting("SENFUND_OIDC_ISSUER", ""),
                            setting("SENFUND_API_BRIDGE_SECRET", ""), setting("SENFUND_OPERATOR_SUBJECT", ""))
    port = int(setting("SENFUND_PORT", "8700"))
    print(f"SenFund ({cfg.env}, chain {cfg.chain_id}) dashboard: http://localhost:{port}/  checkout: {checkout_origin()}")
    ThreadingHTTPServer.request_queue_size = 128  # default backlog 5 drops bursts
    with make_server(app, accounts, port=port, local_ccip=setting("SENFUND_CCIP_LOCAL") == "1") as server:
        threading.Thread(target=verifier_loop, args=(app,), daemon=True).start()
        server.serve_forever()


if __name__ == "__main__":
    main()
