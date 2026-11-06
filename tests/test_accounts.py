import json
import threading
import time
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from eth_account import Account
from eth_account.messages import encode_defunct

from backend.accounts import Accounts
from backend.server import make_handler


ISSUER = "https://identity.example.test"
BRIDGE = "fixture-bridge-secret-" * 3


def test_authenticated_workspace_isolates_invoices_and_wallet_proofs(env):
    accounts = Accounts(env.app.db, ISSUER, BRIDGE, "merchant-subject")
    legacy = env.app.create_invoice("5", "Existing private invoice")
    with ThreadingHTTPServer(("127.0.0.1", 0), make_handler(env.app, accounts)) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_address[1]}/api/"

        def call(path, body=None, token="", bridge=BRIDGE):
            headers = {"X-SenFund-Bridge": bridge, "X-SenFund-Session": token, "Content-Type": "application/json"}
            data = json.dumps(body).encode() if body is not None else None
            try:
                response = urlopen(Request(base + path, data=data, headers=headers), timeout=5)
            except HTTPError as error:
                response = error
            with response:
                return response.status, json.load(response)

        def sign_in(subject, verified=True):
            return call("session/sign-in", {"iss": ISSUER, "sub": subject, "email": "fixture@example.test",
                                             "email_verified": verified, "auth_time": int(time.time())})

        try:
            assert call("invoices", bridge="")[0] == 401
            assert call("invoices")[0] == 401
            assert sign_in("unverified", False)[0] == 400
            first = sign_in("merchant-subject")[1]["token"]
            second = sign_in("other-subject")[1]["token"]
            assert call("invoices", token=first) == (200, [])
            assert call(f"invoices/{legacy['id']}", token=first)[0] == 404
            owner = call("profile", token=first)[1]["id"]
            assert owner != call("profile", token=second)[1]["id"]
            accounts.assign_legacy_invoice(legacy["id"], owner)
            assert call(f"invoices/{legacy['id']}", token=first)[0] == 200
            assert call("profile", {"displayName": "Merchant"}, first)[1]["displayName"] == "Merchant"

            body = {"usd": "3", "description": "Private invoice", "customer": "Client", "owner": "spoofed"}
            assert call("invoices", body, second)[0] == 403
            status, invoice = call("invoices", body, first)
            assert status == 201
            path = f"invoices/{invoice['id']}"
            assert call("invoices", token=second) == (200, [])
            for suffix in ("", "/checkout-request", "/receipt", "/evidence"):
                assert call(path + suffix, token=second)[0] == 404
            for action in ("submit", "verify", "convert", "payout", "simulate-p2p-credit"):
                assert call(path + "/" + action, {}, second)[0] == 404
            for kind in ("receipt", "provider"):
                assert call(f"cre/{kind}/{invoice['id']}", token=second)[0] == 404

            wallet = Account.create()
            proof = call("wallets/challenge", {"address": wallet.address, "purpose": "signer"}, first)[1]
            signature = Account.sign_message(encode_defunct(text=proof["message"]), wallet.key).signature
            payload = {"challenge": proof["challenge"], "signature": "0x" + signature.hex()}
            assert call("wallets/verify", payload, second)[0] == 400
            assert call("wallets/verify", payload, first)[1][0]["address"] == wallet.address
            assert call("wallets/verify", payload, first)[0] == 400
            assert call("wallets", token=second) == (200, [])

            another_session = sign_in("merchant-subject")[1]["token"]
            assert call("session/sign-out", {"allSessions": True}, first)[0] == 200
            assert call(path, token=first)[0] == 401
            assert call(path, token=another_session)[0] == 401
        finally:
            server.shutdown()
            thread.join()
