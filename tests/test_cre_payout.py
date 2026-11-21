import json
from threading import Lock

import pytest

from backend import cre_payout, devchain
from backend.service import SenFund
from backend.state import InvalidTransition


@pytest.fixture
def invoice(env, monkeypatch):
    app = SenFund(env.cfg.with_(cre_payouts=True, ens_name="merchant.example.eth",
                               ens_resolver=env.settle.address, ens_rpc="https://example.invalid"),
                  w3=env.w3, db=env.app.db)
    r = app.create_invoice("25", "Private text")
    rc = devchain.pay(env.w3, r["request"], env.payer)
    env.mine(2)
    app.submit_tx(r["id"], rc["transactionHash"].hex())
    app.run_conversion(r["id"])
    monkeypatch.setattr(cre_payout.ens, "resolve_recipient", lambda cfg: cfg.recipient)
    return app, r["id"]


def decision(route):
    def simulate(payload, rpc):
        return {**payload, "route": route, "reason": "test decision", "policy": cre_payout.POLICY,
                "checks": dict.fromkeys(cre_payout.REQUIRED_CHECKS, True),
                "ensChainId": cre_payout.ens.network(payload["ensNetwork"]).chain_id}
    return simulate


@pytest.mark.parametrize(("scenario", "route", "state"), [
    ("success", "USE_MUDREX", "COMPLETED"),
    ("mudrex_unavailable", "USE_P2P", "ON_HOLD"),
    ("mudrex_unavailable", "HOLD", "NOT_STARTED"),
])
def test_cre_controls_dispatch(invoice, monkeypatch, scenario, route, state):
    app, inv = invoice
    monkeypatch.setattr(cre_payout, "simulate", decision(route))
    result = cre_payout.run(app, Lock(), inv, scenario)
    assert result["payout"] == state
    audit = next(op for op in result["operations"] if op["stage"] == "cre")
    assert audit["status"] == route
    assert json.loads(audit["detail"])["source"] == "Chainlink CRE CLI"
    assert len(app.db.q("select * from mock_provider_orders")) == (route != "HOLD")


def test_existing_uncertain_attempt_cannot_fallback(invoice, monkeypatch):
    app, inv = invoice
    app.run_payout(inv, "timeout")
    monkeypatch.setattr(cre_payout, "simulate", decision("USE_P2P"))
    with pytest.raises(InvalidTransition, match="existing attempt"):
        cre_payout.run(app, Lock(), inv, "mudrex_unavailable")
    assert not app.db.q("select * from mock_provider_orders")
    assert app.get(inv)["payout"] == "ON_HOLD"


def test_cre_ignores_replayed_result(invoice, monkeypatch):
    app, inv = invoice
    monkeypatch.setattr(cre_payout, "simulate", lambda payload, rpc: {
        **decision("USE_MUDREX")(payload, rpc), "run": "prior-run",
    })
    with pytest.raises(InvalidTransition, match="does not match"):
        cre_payout.run(app, Lock(), inv, "success")
    assert not app.db.q("select * from mock_provider_orders")


def test_cre_holds_when_ens_rotates(invoice, monkeypatch):
    app, inv = invoice
    monkeypatch.setattr(cre_payout, "simulate", decision("USE_MUDREX"))
    monkeypatch.setattr(cre_payout.ens, "resolve_recipient", lambda cfg: app.merchant)
    result = cre_payout.run(app, Lock(), inv, "success")
    assert result["payout"] == "NOT_STARTED"
    assert not app.db.q("select * from mock_provider_orders")


def test_cre_reconciles_lost_primary_response_without_fallback(invoice, monkeypatch):
    app, inv = invoice
    app.run_payout(inv, "timeout_created")
    assert app.get(inv)["payout"] == "ON_HOLD"
    monkeypatch.setattr(cre_payout, "simulate", decision("USE_MUDREX"))
    result = cre_payout.run(app, Lock(), inv, "mudrex_unavailable")
    assert result["payout"] == "COMPLETED"
    orders = app.db.q("select order_id from mock_provider_orders")
    assert len(orders) == 1
    assert orders[0]["order_id"].startswith("SIM-MUDREX-")


def test_dashboard_payout_runs_cre_and_exposes_only_evidence(invoice, monkeypatch):
    from http.server import ThreadingHTTPServer
    from threading import Thread
    from urllib.request import Request, urlopen

    from backend.server import make_handler

    app, inv = invoice
    with ThreadingHTTPServer(("127.0.0.1", 0), make_handler(app)) as server:
        base = f"http://127.0.0.1:{server.server_address[1]}/api"

        def simulate(payload, rpc):
            with urlopen(f"{base}/cre/receipt/{inv}", timeout=3) as response:
                evidence = json.load(response)
            assert evidence == payload["receipt"]
            assert "Private text" not in json.dumps(evidence)
            with urlopen(f"{base}/cre/provider/{inv}?scenario=mudrex_unavailable", timeout=3) as response:
                assert json.load(response)["available"] is False
            return decision("USE_P2P")(payload, rpc)

        monkeypatch.setattr(cre_payout, "simulate", simulate)
        server_thread = Thread(target=server.serve_forever, daemon=True)
        server_thread.start()
        try:
            request = Request(f"{base}/invoices/{inv}/payout",
                              data=b'{"scenario":"mudrex_unavailable"}',
                              headers={"Content-Type": "application/json"})
            with urlopen(request, timeout=8) as response:
                r = json.load(response)
            assert r["payout"] == "ON_HOLD"
            assert any(op["stage"] == "cre" and op["status"] == "USE_P2P" for op in r["operations"])
        finally:
            server.shutdown()
            server_thread.join()


def test_missing_cre_policy_check_blocks_dispatch(invoice, monkeypatch):
    app, inv = invoice

    def incomplete(payload, rpc):
        output = decision("USE_MUDREX")(payload, rpc)
        output["checks"]["providerSnapshot"] = False
        return output

    monkeypatch.setattr(cre_payout, "simulate", incomplete)
    with pytest.raises(InvalidTransition, match="evidence checks"):
        cre_payout.run(app, Lock(), inv, "success")
    assert not app.db.q("select * from mock_provider_orders")


def test_ccip_failure_leaves_payout_unstarted(invoice, monkeypatch):
    app, inv = invoice
    monkeypatch.setattr(cre_payout, "simulate", decision("USE_MUDREX"))

    def reject(receipt, nonce, route):
        raise InvalidTransition("CCIP rejected the approval")

    result = cre_payout.run(app, Lock(), inv, "success", authorize=reject)
    audit = next(op for op in result["operations"] if op["stage"] == "cre")
    assert audit["status"] == "HOLD"
    assert result["payout"] == "NOT_STARTED"
    assert not app.db.q("select * from mock_provider_orders")


def test_cre_rejects_decision_from_wrong_ens_network(invoice, monkeypatch):
    app, inv = invoice

    def wrong_network(payload, rpc):
        return {**decision("USE_MUDREX")(payload, rpc), "ensChainId": 1}

    monkeypatch.setattr(cre_payout, "simulate", wrong_network)
    with pytest.raises(InvalidTransition, match="ENS network"):
        cre_payout.run(app, Lock(), inv, "success")
    assert not app.db.q("select * from mock_provider_orders")
