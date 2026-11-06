"""PRD acceptance: happy path, tampered invoices, wrong network/token, duplicates, payout retries, recovery."""
import json
import pytest
from web3 import Web3

from backend import chain, devchain
from backend.adapters import LiveRemittance
from backend.config import guard
from backend.service import SenFund
from backend.state import InvalidTransition


def paid(e, usd="25"):
    inv = e.app.create_invoice(usd, "Test order")
    rc = devchain.pay(e.w3, inv["request"], e.payer)
    e.mine(2)
    return inv, rc


def test_core_flow(env):
    inv, rc = paid(env)
    assert inv["amount_units"] == "25000000"
    assert chain.recover(inv["request"]) == env.app.merchant
    assert env.app.submit_tx(inv["id"], rc["transactionHash"].hex())["status"] == "paid"
    assert env.usdt.functions.balanceOf(env.cfg.recipient).call() == 25_000_000
    r = env.app.run_conversion(inv["id"])
    assert json.loads(r["operations"][0]["detail"])["net_usd"] == "24.50"
    r = env.app.run_payout(inv["id"])
    assert r["payout"] == "COMPLETED"
    payout_op = next(o for o in r["operations"] if o["stage"] == "payout")
    assert json.loads(payout_op["detail"])["route"] == "mudrex"
    assert payout_op["external_id"].startswith("SIM-MUDREX-")
    html = env.app.receipt_html(inv["id"])
    assert "Simulated payout completed" in html and "1920.00 INR" in html and "Verified onchain" in html
    assert "XXXX0000" not in html  # beneficiary data never exported
    for bad in ("Claude", "Ponytail", "Anthropic"):
        assert bad not in html


def test_pending_until_confirmed(env):
    inv = env.app.create_invoice("25", "x")
    rc = devchain.pay(env.w3, inv["request"], env.payer)
    assert env.app.submit_tx(inv["id"], rc["transactionHash"].hex())["status"] == "pending"
    env.mine(2)
    assert env.app.verify(inv["id"])["status"] == "paid"


@pytest.mark.parametrize("field,value", [
    ("amount", "1000000"),
    ("recipient", "0x000000000000000000000000000000000000dEaD"),
    ("expiry", "9999999999"),
])
def test_tampered_request_reverts(env, field, value):
    inv = env.app.create_invoice("25", "x")
    req = {**inv["request"], field: value}
    with pytest.raises(Exception):
        devchain.pay(env.w3, req, env.payer)
    assert env.usdt.functions.balanceOf(env.cfg.recipient).call() == 0


def test_tampered_signature_and_contract_check(env):
    inv = env.app.create_invoice("25", "x")
    req = inv["request"]
    sig = bytes.fromhex(req["signature"][2:])
    bad = {**req, "signature": "0x" + (sig[:10] + bytes([sig[10] ^ 1]) + sig[11:]).hex()}
    d, ok, state = env.settle.functions.checkRequest(req["invoiceId"], req["merchant"], req["recipient"], req["token"],
                                                    int(req["amount"]), int(req["expiry"]), bad["signature"]).call()
    assert not ok
    with pytest.raises(Exception):
        devchain.pay(env.w3, bad, env.payer)


def test_expired_request_reverts(env):
    inv = env.app.create_invoice("25", "x", ttl=1)
    env.w3.testing.timeTravel(int(inv["request"]["expiry"]) + 10)
    with pytest.raises(Exception):
        devchain.pay(env.w3, inv["request"], env.payer)


def test_wrong_token(env):
    """Settlement with a different token: signature check fails onchain; and a request
    re-signed for another token is rejected by the backend's token check."""
    fake = devchain.deploy(env.w3, "MockUSDT", env.payer)
    devchain.send(env.w3, fake.functions.mint(env.payer, 10**9), env.payer)
    inv = env.app.create_invoice("25", "x")
    with pytest.raises(Exception):
        devchain.pay(env.w3, {**inv["request"], "token": fake.address}, env.payer)
    # merchant-signed for wrong token (misconfiguration) still fails verification
    other = SenFund(env.cfg.with_(token=fake.address), w3=env.w3, db=env.app.db)
    inv2 = other.create_invoice("25", "x")
    rc = devchain.pay(env.w3, inv2["request"], env.payer)
    env.mine(2)
    res = env.app.submit_tx(inv2["id"], rc["transactionHash"].hex())
    assert res["status"] == "rejected" and "token" in res["detail"]


def test_fee_on_transfer_token_reverts(env):
    fee = devchain.deploy(env.w3, "FeeOnTransferToken", env.payer)
    devchain.send(env.w3, fee.functions.mint(env.payer, 10**9), env.payer)
    app = SenFund(env.cfg.with_(token=fee.address), w3=env.w3, db=env.app.db)
    inv = app.create_invoice("25", "x")
    with pytest.raises(Exception):
        devchain.pay(env.w3, inv["request"], env.payer, token_abi_name="FeeOnTransferToken")


def test_wrong_network(env):
    inv, rc = paid(env)
    wrong = SenFund(env.cfg.with_(chain_id=1), w3=env.w3, db=env.app.db)
    res = wrong.submit_tx(inv["id"], rc["transactionHash"].hex())
    assert res["status"] == "rejected" and res["reason"] == "wrong_network"
    # testnet config refuses anything but chain 1874 and non-test envs
    with pytest.raises(RuntimeError):
        guard("production")


def test_forged_event_and_unrelated_tx(env):
    inv = env.app.create_invoice("25", "x")
    req = inv["request"]
    forger = devchain.deploy(env.w3, "ForgedEmitter", env.payer)
    rc = devchain.send(env.w3, forger.functions.forge(req["invoiceId"], req["digest"], req["merchant"], req["recipient"],
                                                      req["token"], int(req["amount"])), env.payer)
    env.mine(2)
    res = env.app.submit_tx(inv["id"], rc["transactionHash"].hex())
    assert res["status"] == "rejected" and res["reason"] == "no_settlement_event"
    # a real settlement of a different invoice can't be claimed for this one
    other, rc2 = paid(env)
    res = env.app.submit_tx(inv["id"], rc2["transactionHash"].hex())
    assert res["reason"] == "no_settlement_event"


def test_duplicate_settlement(env):
    inv, rc = paid(env)
    env.app.submit_tx(inv["id"], rc["transactionHash"].hex())
    with pytest.raises(Exception):  # onchain: InvoiceNotOpen
        devchain.pay(env.w3, inv["request"], env.payer)
    assert env.usdt.functions.balanceOf(env.cfg.recipient).call() == 25_000_000
    assert env.app.submit_tx(inv["id"], rc["transactionHash"].hex())["status"] == "already_paid"
    assert len(env.app.db.q("select * from receipts")) == 1


def test_cancelled_invoice_cannot_be_paid(env):
    inv = env.app.create_invoice("25", "x")
    merchant = env.app.merchant
    env.w3.eth.send_transaction({"from": env.payer, "to": merchant, "value": 10**18})
    devchain.send(env.w3, env.settle.functions.cancel(inv["request"]["invoiceId"]), merchant, env.cfg.merchant_key)
    with pytest.raises(Exception):
        devchain.pay(env.w3, inv["request"], env.payer)


@pytest.mark.parametrize("scenario", ["timeout", "timeout_created"])
def test_uncertain_payout_retry_never_duplicates(env, scenario):
    inv, rc = paid(env)
    env.app.submit_tx(inv["id"], rc["transactionHash"].hex())
    env.app.run_conversion(inv["id"])
    r = env.app.run_payout(inv["id"], scenario=scenario)
    assert r["payout"] == "ON_HOLD"
    r = env.app.run_payout(inv["id"], scenario="success")  # retry
    r = env.app.run_payout(inv["id"], scenario="success")  # and again
    assert r["payout"] == "COMPLETED"
    assert len(env.app.db.q("select * from mock_provider_orders")) == 1


@pytest.mark.parametrize("scenario, expected, order_count", [
    ("timeout", "ON_HOLD", 0),
    ("timeout_created", "COMPLETED", 1),
    ("fail", "FAILED", 1),
])
def test_existing_primary_attempt_does_not_fall_back(env, scenario, expected, order_count):
    inv, rc = paid(env)
    invoice_id = inv["id"]
    env.app.submit_tx(invoice_id, rc["transactionHash"].hex())
    env.app.run_conversion(invoice_id)
    env.app.run_payout(invoice_id, scenario=scenario)
    r = env.app.run_payout(invoice_id, scenario="mudrex_unavailable")
    assert r["payout"] == expected
    op = next(o for o in r["operations"] if o["stage"] == "payout")
    assert json.loads(op["detail"])["route"] == "mudrex"
    assert len(env.app.db.q("select * from mock_provider_orders")) == order_count


def test_p2p_fallback_survives_restart_and_requires_credit(env):
    inv, rc = paid(env)
    invoice_id = inv["id"]
    env.app.submit_tx(invoice_id, rc["transactionHash"].hex())
    env.app.run_conversion(invoice_id)
    r = env.app.run_payout(invoice_id, scenario="mudrex_unavailable")
    assert r["payout"] == "ON_HOLD"
    op = next(o for o in r["operations"] if o["stage"] == "payout")
    assert op["external_id"].startswith("SIM-P2P-")
    assert json.loads(op["detail"])["route"] == "p2p"
    env.app.db.close()

    restarted = SenFund(env.cfg, w3=env.w3)
    assert restarted.run_payout(invoice_id, scenario="success")["payout"] == "ON_HOLD"
    assert restarted.provider_callback("evt-p2p", op["external_id"], "COMPLETED") == "wrong_route"
    assert restarted.get(invoice_id)["payout"] == "ON_HOLD"
    assert restarted.confirm_p2p_credit(invoice_id)["payout"] == "COMPLETED"
    assert restarted.confirm_p2p_credit(invoice_id)["payout"] == "COMPLETED"
    assert len(restarted.db.q("select * from mock_provider_orders")) == 1
    assert "Mudrex unavailable before any order was submitted" in restarted.receipt_html(invoice_id)
    restarted.db.close()


def test_payout_callbacks_dedupe_and_stale(env):
    inv, rc = paid(env)
    env.app.submit_tx(inv["id"], rc["transactionHash"].hex())
    env.app.run_conversion(inv["id"])
    r = env.app.run_payout(inv["id"], scenario="hold")
    assert r["payout"] == "ON_HOLD"
    oid = r["operations"][-1]["external_id"]
    assert env.app.provider_callback("evt1", oid, "COMPLETED") == "applied"
    assert env.app.provider_callback("evt1", oid, "COMPLETED") == "duplicate"
    assert env.app.provider_callback("evt2", oid, "ON_HOLD").startswith("ignored_stale")
    assert env.app.get(inv["id"])["payout"] == "COMPLETED"


def test_payout_requires_verified_payment(env):
    inv = env.app.create_invoice("25", "x")
    with pytest.raises(InvalidTransition):
        env.app.run_conversion(inv["id"])
    with pytest.raises(RuntimeError):
        LiveRemittance()


def test_recovery_with_app_stopped(env, tmp_path):
    """Invoice created, server 'stopped' (no submit), customer pays via static checkout.
    A fresh process (new DB handle, same file) recovers the payment via log reconciliation."""
    inv = env.app.create_invoice("25", "x")
    env.app.db.close()
    rc = devchain.pay(env.w3, inv["request"], env.payer)
    env.mine(2)
    restarted = SenFund(env.cfg, w3=env.w3)
    found = restarted.reconcile()
    assert found == [{"invoice": inv["id"], "status": "paid"}]
    assert restarted.get(inv["id"])["receipt"]["tx_hash"] == chain._h(rc["transactionHash"])
    assert restarted.reconcile() == []  # idempotent


def test_reorg_orphans_receipt(env):
    snap = env.w3.testing.snapshot()
    inv, rc = paid(env)
    env.app.submit_tx(inv["id"], rc["transactionHash"].hex())
    env.app.run_conversion(inv["id"])
    env.w3.testing.revert(snap)
    env.mine(5)  # replacement chain without the payment
    assert env.app.recheck() == [inv["id"]]
    r = env.app.get(inv["id"])
    assert r["payment"] == "SUBMITTED" and r["needs_review"] == 1 and r["receipt"] is None
    assert env.app.verify(inv["id"])["status"] in ("pending", "rejected")


def test_checkout_constants_match_abi():
    js = open(chain.ROOT / "checkout" / "app.js").read()
    assert chain._h(chain.SETTLED_TOPIC) in js
    sel = Web3.keccak(text="settle(bytes32,address,address,address,uint256,uint256,bytes)")[:4].hex()
    assert sel.removeprefix("0x") in js


def test_recheck_rpc_failure_preserves_paid_invoice(env, monkeypatch):
    inv, rc = paid(env)
    env.app.submit_tx(inv["id"], rc["transactionHash"].hex())

    def unavailable(_number):
        raise TimeoutError("RPC timed out")

    monkeypatch.setattr(env.w3.eth, "get_block", unavailable)
    assert env.app.recheck() == []
    current = env.app.get(inv["id"])
    assert current["payment"] == "PAID" and current["needs_review"] == 0
    assert current["receipt"]["tx_hash"] == chain._h(rc["transactionHash"])


def test_reorg_update_rolls_back_on_failure(env, monkeypatch):
    snap = env.w3.testing.snapshot()
    inv, rc = paid(env)
    env.app.submit_tx(inv["id"], rc["transactionHash"].hex())
    env.w3.testing.revert(snap)
    env.mine(5)
    original = env.app.db.x

    def fail_flag(sql, *args):
        if sql.startswith("update invoices set needs_review"):
            raise RuntimeError("write failed")
        return original(sql, *args)

    with monkeypatch.context() as patch:
        patch.setattr(env.app.db, "x", fail_flag)
        with pytest.raises(RuntimeError, match="write failed"):
            env.app.recheck()
    current = env.app.get(inv["id"])
    assert current["payment"] == "PAID" and current["needs_review"] == 0
    assert current["receipt"]["tx_hash"] == chain._h(rc["transactionHash"])
    assert all(row["source"] != "reorg" for row in current["history"])
    assert env.app.recheck() == [inv["id"]]


def test_unrelated_hash_cannot_replace_pending_payment(env):
    inv = env.app.create_invoice("25", "x")
    rc = devchain.pay(env.w3, inv["request"], env.payer)
    tx_hash = chain._h(rc["transactionHash"])
    assert env.app.submit_tx(inv["id"], tx_hash)["status"] == "pending"
    assert env.app.submit_tx(inv["id"], "0x" + "aa" * 32)["status"] == "pending"
    unrelated = env.w3.eth.send_transaction({"from": env.payer, "to": env.cfg.recipient, "value": 1})
    assert env.app.submit_tx(inv["id"], chain._h(unrelated))["status"] == "rejected"
    assert env.app.get(inv["id"])["tx_hash"] == tx_hash
    env.mine()
    assert env.app.verify(inv["id"])["status"] == "paid"


def test_reconcile_resumes_bounded_scan_after_restart(env, monkeypatch):
    import backend.service as service

    inv = env.app.create_invoice("25", "x")
    rc = devchain.pay(env.w3, inv["request"], env.payer)
    env.mine(2)
    payment_block = rc["blockNumber"]
    cfg = env.cfg.with_(from_block=payment_block - 2)
    first = SenFund(cfg, w3=env.w3, db=env.app.db)
    monkeypatch.setattr(service, "RECONCILE_BLOCKS", 2)
    original = env.w3.eth.get_logs
    ranges = []

    def record(query):
        ranges.append((query["fromBlock"], query["toBlock"]))
        return original(query)

    monkeypatch.setattr(env.w3.eth, "get_logs", record)
    assert first.reconcile() == []
    first.db.close()
    restarted = SenFund(cfg, w3=env.w3)
    assert restarted.reconcile() == [{"invoice": inv["id"], "status": "paid"}]
    assert restarted.reconcile() == []
    assert ranges == [(payment_block - 2, payment_block - 1), (payment_block, payment_block + 1)]
    restarted.db.close()


def test_recent_reconciliation_recovers_payment_without_skipping_history(env, monkeypatch):
    import backend.service as service

    inv = env.app.create_invoice("25", "Recent checkout")
    receipt = devchain.pay(env.w3, inv["request"], env.payer)
    env.mine(2)
    payment_block = receipt["blockNumber"]
    app = SenFund(env.cfg.with_(from_block=payment_block - 3), w3=env.w3, db=env.app.db)
    monkeypatch.setattr(service, "RECONCILE_BLOCKS", 2)

    assert app.reconcile(prioritize_recent=True) == [{"invoice": inv["id"], "status": "paid"}]
    cursor = app.db.one("select block_number from reconciliation_cursor")
    assert cursor["block_number"] == payment_block - 2
    assert app.reconcile(prioritize_recent=True) == []
