import json
from dataclasses import replace

import pytest
from web3 import Web3

from backend import devchain
from scripts import demo, ens_record


def test_ens_setup_targets_only_whitechain_record(env):
    name = "merchant.example.eth"
    recipient = env.cfg.recipient
    delegate = env.payer
    update = ens_record.build_transaction(name, env.settle.address, recipient)
    grant = ens_record.build_transaction(name, env.settle.address, recipient, delegate)
    assert update["chainId"] == grant["chainId"] == 11155111
    assert update["to"] == grant["to"] == env.settle.address
    assert update["value"] == grant["value"] == "0x0"
    update_data = Web3.to_bytes(hexstr=update["data"])
    raw = Web3.to_bytes(hexstr=grant["data"])
    assert raw[:4] == Web3.keccak(text="grantSetterRoles(bytes,address)")[:4]
    setter, target = env.w3.codec.decode(["bytes", "address"], raw[4:])
    assert setter == update_data and target.lower() == delegate.lower()
    assert setter[:4] == Web3.keccak(text="setAddress(bytes,uint256,bytes)")[:4]
    wire, coin_type, value = env.w3.codec.decode(["bytes", "uint256", "bytes"], setter[4:])
    assert wire == b"\x08merchant\x07example\x03eth\0" and coin_type == 0x80000752
    assert Web3.to_checksum_address(value) == recipient


def test_evidence_checks_paid_canonical_transfer_and_contract_verification(env, monkeypatch):
    invoice = env.app.create_invoice("25", "Private description")
    inv = invoice["id"]
    with pytest.raises(ValueError, match="before exporting"):
        demo.stored_payment(env.cfg.db_path, inv)
    rc = devchain.pay(env.w3, invoice["request"], env.payer)
    env.mine(2)
    assert env.app.submit_tx(inv, rc["transactionHash"].hex())["status"] == "paid"
    with pytest.raises(ValueError, match="official Whitechain"):
        demo.build_evidence(env.cfg, env.w3, inv)

    # Exercise the full exporter on the fixture chain after swapping its expected network constants.
    monkeypatch.setattr(demo, "CHAIN_ID", env.cfg.chain_id)
    monkeypatch.setattr(demo, "TOKEN", env.cfg.token)
    cfg = replace(env.cfg, env="testnet")
    monkeypatch.setattr(demo, "explorer_verified", lambda address: False)
    with pytest.raises(ValueError, match="source verification"):
        demo.build_evidence(cfg, env.w3, inv)

    monkeypatch.setattr(demo, "explorer_verified", lambda address: address == env.settle.address)
    evidence = demo.build_evidence(cfg, env.w3, inv)
    assert evidence["amountTestUsdt"] == "25.000000"
    assert evidence["tokenTransferLogIndex"] < evidence["logIndex"]
    assert "Private description" not in json.dumps(evidence)
    env.app.db.x("update receipts set block_hash=? where invoice=?", "0x" + "00" * 32, inv)
    with pytest.raises(ValueError, match="canonical settlement"):
        demo.build_evidence(cfg, env.w3, inv)
