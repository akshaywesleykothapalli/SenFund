import json, threading, urllib.error, urllib.request
from http.server import ThreadingHTTPServer
from backend import devchain
from backend.server import make_handler


def test_api_flow(env):
    srv = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(env.app))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}/api"
    def call(p, body=None):
        r = urllib.request.Request(base + p, data=json.dumps(body).encode() if body is not None else None,
                                   headers={"Content-Type": "application/json"})
        try:
            return json.loads(urllib.request.urlopen(r).read())
        except urllib.error.HTTPError as e:
            raise AssertionError(f"{p}: {e.code} {e.read()}")
    inv = call("/invoices", {"usd": "25.00", "description": "t"})
    assert "#req=" in inv["checkout"]
    rc = devchain.pay(env.w3, call(f"/invoices/{inv['id']}/checkout-request"), env.payer)
    call(f"/invoices/{inv['id']}/submit", {"tx_hash": rc["transactionHash"].hex()})
    env.mine(3)
    assert call(f"/invoices/{inv["id"]}/verify", {})["status"] == "paid"
    path = f"/invoices/{inv['id']}"
    assert call(path + "/convert", {})["conversion"] == "COMPLETED"
    assert call(path + "/payout", {"scenario": "mudrex_unavailable"})["payout"] == "ON_HOLD"
    assert call(path + "/simulate-p2p-credit", {})["payout"] == "COMPLETED"
    assert call("/config")["livePayouts"] is False
    srv.shutdown()


def test_invoice_creation_retry_survives_restart(env):
    from contextlib import closing
    from backend.service import SenFund

    body = {"usd": "3", "description": "Service", "customer": "Client"}

    def serve_once(app, data):
        with ThreadingHTTPServer(("127.0.0.1", 0), make_handler(app)) as server:
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                url = f"http://127.0.0.1:{server.server_address[1]}/api/invoices"
                request = urllib.request.Request(url, data=data, headers={
                    "Content-Type": "application/json",
                    "Idempotency-Key": "invoice-retry-test",
                })
                try:
                    response = urllib.request.urlopen(request, timeout=5)
                except urllib.error.HTTPError as error:
                    response = error
                with response:
                    return response.status, json.load(response)
            finally:
                server.shutdown()
                thread.join()

    status, original = serve_once(env.app, json.dumps(body).encode())
    assert status == 201
    restarted = SenFund(env.cfg, w3=env.w3)
    with closing(restarted.db):
        status, replay = serve_once(restarted, json.dumps({**body, "usd": "3.00"}).encode())
        assert status == 201
        assert replay["id"] == original["id"]
        assert replay["checkout"] == original["checkout"]
        assert serve_once(restarted, json.dumps({**body, "usd": "4"}).encode())[0] == 409
        assert serve_once(restarted, b"[1]")[0] == 400
        assert serve_once(restarted, b"{")[0] == 400
        assert serve_once(restarted, json.dumps({**body, "usd": "NaN"}).encode())[0] == 400
        assert len(restarted.list()) == 1
