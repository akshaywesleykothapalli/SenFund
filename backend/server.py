"""SenFund merchant app: dashboard (web/) + JSON API + background verifier. stdlib http.server only."""
import base64
import json
import threading
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from . import cre_payout

from .config import ROOT, load, setting
from .service import InvoiceCreationConflict, SenFund

CHECKOUT_URL = setting("SENFUND_CHECKOUT_URL", "http://localhost:8702/")
LOCK = threading.Lock()  # service calls are short; one at a time keeps state transitions simple


def checkout_link(app, inv):
    raw = json.dumps(app.checkout_request(inv), separators=(",", ":")).encode()
    return CHECKOUT_URL + "#req=" + base64.urlsafe_b64encode(raw).decode().rstrip("=")


def make_handler(app):
    class H(SimpleHTTPRequestHandler):
        def __init__(self, *a, **k):
            super().__init__(*a, directory=str(ROOT / "web"), **k)

        def log_message(self, *a):
            pass

        def _json(self, code, body):
            data = json.dumps(body, default=str).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _route(self, method):
            parts = urlparse(self.path).path.strip("/").split("/")
            if parts[0] != "api":
                return super().do_GET() if method == "GET" else self._json(404, {"error": "not found"})
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
                if app.cfg.cre_payouts and method == "POST" and len(parts) == 4 and parts[1] == "invoices" and parts[3] == "payout":
                    result = cre_payout.run(app, LOCK, parts[2], body.get("scenario", "success"))
                    return self._json(200, result)
                with LOCK:
                    return self._dispatch(method, parts[1:], body)
            except InvoiceCreationConflict as error:
                return self._json(409, {"error": str(error)})
            except KeyError:
                return self._json(404, {"error": "unknown invoice"})  # KeyError from service = missing row
            except (ValueError, RuntimeError) as e:
                return self._json(400, {"error": str(e)})
            except Exception as e:  # e.g. InvalidTransition
                return self._json(409, {"error": f"{type(e).__name__}: {e}"})

        def _dispatch(self, method, p, body):
            if p == ["config"]:
                c = app.cfg
                return self._json(200, {"env": c.env, "chainId": c.chain_id, "explorer": c.explorer, "settlement": c.settlement,
                                        "token": c.token, "merchant": app.merchant, "recipient": c.recipient,
                                        "confirmations": c.confirmations, "ensName": c.ens_name, "crePayouts": c.cre_payouts, "livePayouts": False, "mainnet": False})
            if app.cfg.cre_payouts and method == "GET" and len(p) == 3 and p[0] == "cre":
                if p[1] == "receipt":
                    return self._json(200, cre_payout.receipt_evidence(app, p[2]))
                if p[1] == "provider":
                    scenario = parse_qs(urlparse(self.path).query).get("scenario", ["success"])[0]
                    return self._json(200, cre_payout.provider_evidence(app, p[2], scenario))
            if p == ["invoices"] and method == "GET":
                return self._json(200, app.list())
            if p == ["invoices"] and method == "POST":
                description = body.get("description", "Invoice")
                customer = body.get("customer", "")
                if not isinstance(description, str) or not isinstance(customer, str):
                    raise ValueError("Invoice description and customer must be text.")
                inv = app.create_invoice(body.get("usd", ""), description[:200], customer[:100],
                                         idempotency_key=self.headers.get("Idempotency-Key"))
                return self._json(201, {**inv, "checkout": checkout_link(app, inv["id"])})
            if p == ["callbacks", "remittance"] and method == "POST":
                return self._json(200, {"result": app.provider_callback(body["event_id"], body["order_id"], body["status"])})
            if len(p) >= 2 and p[0] == "invoices":
                inv, action = p[1], (p[2] if len(p) > 2 else "")
                if method == "GET" and action == "":
                    return self._json(200, {**app.get(inv), "checkout": checkout_link(app, inv)})
                if method == "GET" and action == "checkout-request":
                    return self._json(200, app.checkout_request(inv))
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
    threading.Thread(target=verifier_loop, args=(app,), daemon=True).start()
    port = int(setting("SENFUND_PORT", "8700"))
    print(f"SenFund ({cfg.env}, chain {cfg.chain_id}) dashboard: http://localhost:{port}/  checkout: {CHECKOUT_URL}")
    ThreadingHTTPServer(("127.0.0.1", port), make_handler(app)).serve_forever()


if __name__ == "__main__":
    main()
