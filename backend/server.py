"""SenFund merchant app: dashboard (web/) + JSON API + background verifier. stdlib http.server only."""
import base64
import json
import re
from decimal import Decimal
import threading
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from . import cre_payout, drafter

from .accounts import Accounts
from .adapters import CORRIDORS
from .config import ROOT, load, setting, web3_for
from .state import InvalidTransition
from .service import InvoiceCreationConflict, SenFund, draft_note

CHECKOUT_URL = setting("SENFUND_CHECKOUT_URL", "http://localhost:8702/")
LOCK = threading.Lock()  # service calls are short; one at a time keeps state transitions simple


ADDRESS = re.compile(r"^0x[0-9a-fA-F]{40}$")


def balance(cfg, address):
    """Read-only testnet balances for one address: native gas coin and the settlement token."""
    if not ADDRESS.match(address or ""):
        raise ValueError("Enter a valid 0x wallet address.")
    w3 = web3_for(cfg)
    addr = w3.to_checksum_address(address)
    native = w3.eth.get_balance(addr)
    data = "0x70a08231" + addr[2:].lower().rjust(64, "0")
    raw = int(w3.eth.call({"to": w3.to_checksum_address(cfg.token), "data": data}).hex() or "0", 16)
    return {"address": addr, "chainId": cfg.chain_id,
            "native": str(Decimal(native) / Decimal(10**18)),
            "token": str(Decimal(raw) / (Decimal(10) ** cfg.token_decimals))}


def checkout_link(app, inv):
    raw = json.dumps(app.checkout_request(inv), separators=(",", ":")).encode()
    return CHECKOUT_URL + "#req=" + base64.urlsafe_b64encode(raw).decode().rstrip("=")


def make_handler(app, accounts=None):
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
            if accounts and not accounts.trusted_bridge(self.headers.get("X-SenFund-Bridge", "")):
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
                if accounts:
                    path = parts[1:]
                    if path == ["session", "sign-in"] and method == "POST":
                        return self._json(201, {"token": accounts.sign_in(body)})
                    token = self.headers.get("X-SenFund-Session", "")
                    actor = accounts.actor(token)
                    if actor is None:
                        return self._json(401, {"error": "Sign in to access your workspace."})
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
                    if not path or path[0] not in {"invoices", "config", "cre", "draft-invoice", "draft-note", "balance"}:
                        return self._json(404, {"error": "not found"})
                    if path[0] == "invoices" and len(path) >= 2:
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
                if app.cfg.cre_payouts and method == "POST" and len(parts) == 4 and parts[1] == "invoices" and parts[3] == "payout":
                    result = cre_payout.run(app, LOCK, parts[2], body.get("scenario", "success"))
                    return self._json(200, result)
                if method == "GET" and len(parts) == 3 and parts[1] == "balance":  # network read; keep outside LOCK
                    try:
                        return self._json(200, balance(app.cfg, parts[2]))
                    except ValueError:
                        raise
                    except Exception:
                        return self._json(502, {"error": "Could not reach the Whitechain testnet RPC."})
                with LOCK:
                    return self._dispatch(method, parts[1:], body, actor)
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

        def _dispatch(self, method, p, body, actor):
            if p == ["config"]:
                c = app.cfg
                return self._json(200, {"env": c.env, "chainId": c.chain_id, "explorer": c.explorer, "settlement": c.settlement,
                                        "token": c.token, "merchant": app.merchant, "recipient": c.recipient,
                                        "confirmations": c.confirmations, "ensName": c.ens_name, "crePayouts": c.cre_payouts, "livePayouts": False, "mainnet": False,
                                        "corridors": {k: {"currency": v["currency"], "rate": str(v["rate"]), "fee": str(v["fee"]), "note": v["note"]}
                                                      for k, v in CORRIDORS.items()}})
            if app.cfg.cre_payouts and method == "GET" and len(p) == 3 and p[0] == "cre":
                if p[1] == "receipt":
                    return self._json(200, cre_payout.receipt_evidence(app, p[2]))
                if p[1] == "provider":
                    scenario = parse_qs(urlparse(self.path).query).get("scenario", ["success"])[0]
                    return self._json(200, cre_payout.provider_evidence(app, p[2], scenario))
            if p == ["invoices"] and method == "GET":
                return self._json(200, app.list(actor["id"] if actor else None, legacy_only=actor is None))
            if p == ["invoices"] and method == "POST":
                description = body.get("description", "Invoice")
                customer = body.get("customer", "")
                if not isinstance(description, str) or not isinstance(customer, str):
                    raise ValueError("Invoice description and customer must be text.")
                inv = app.create_invoice(body.get("usd", ""), description[:200], customer[:100],
                                         idempotency_key=self.headers.get("Idempotency-Key"),
                                         owner=actor["id"] if actor else None,
                                         corridor=body.get("corridor", "IN"))
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


def main():
    cfg = load()
    app = SenFund(cfg)
    accounts = None
    if setting("SENFUND_ACCOUNT_MODE") == "1":
        if cfg.cre_payouts:
            raise ValueError("Disable the local CRE runner before enabling account mode.")
        accounts = Accounts(app.db, setting("SENFUND_OIDC_ISSUER", ""),
                            setting("SENFUND_API_BRIDGE_SECRET", ""), setting("SENFUND_OPERATOR_SUBJECT", ""))
    threading.Thread(target=verifier_loop, args=(app,), daemon=True).start()
    port = int(setting("SENFUND_PORT", "8700"))
    print(f"SenFund ({cfg.env}, chain {cfg.chain_id}) dashboard: http://localhost:{port}/  checkout: {CHECKOUT_URL}")
    ThreadingHTTPServer.request_queue_size = 128  # default backlog 5 drops bursts
    ThreadingHTTPServer(("127.0.0.1", port), make_handler(app, accounts)).serve_forever()


if __name__ == "__main__":
    main()
