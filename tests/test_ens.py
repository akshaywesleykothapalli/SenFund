from types import SimpleNamespace

import pytest
from web3 import Web3

from backend import chain, ens
from backend.service import SenFund


@pytest.mark.parametrize("present", [True, False])
def test_ens_requires_explicit_address(env, present):
    cfg = env.cfg.with_(ens_rpc="https://example.invalid", ens_name="merchant.example.eth", ens_resolver=env.settle.address)
    calls = []

    def call(tx, block_identifier):
        assert tx["to"] == ens.UNIVERSAL_RESOLVER
        assert block_identifier == 31
        name, query = env.w3.codec.decode(["bytes", "bytes"], tx["data"][4:])
        assert name == b"\x08merchant\x07example\x03eth\0"
        assert int.from_bytes(query[-32:]) == 0x80000752
        calls.append(query[:4].hex())
        value = env.w3.codec.encode(["bool"], [present]) if len(calls) == 1 else env.w3.codec.encode(
            ["bytes"], [bytes.fromhex(env.cfg.recipient[2:])]
        )
        return env.w3.codec.encode(["bytes", "address"], [value, cfg.ens_resolver])

    w3 = SimpleNamespace(codec=env.w3.codec, eth=SimpleNamespace(chain_id=11155111, block_number=31, call=call))
    if present:
        assert ens.resolve_recipient(cfg, w3) == env.cfg.recipient
        assert calls == ["32f111d7", "f1cb7e06"]
    else:
        with pytest.raises(ValueError, match="no explicit"):
            ens.resolve_recipient(cfg, w3)
        assert calls == ["32f111d7"]


def test_testnet_invoice_signs_ens_address_and_keeps_description_private(env, monkeypatch):
    resolved = env.w3.eth.accounts[1]
    monkeypatch.setattr(ens, "resolve_recipient", lambda cfg: resolved)
    app = SenFund(env.cfg.with_(env="testnet"), w3=env.w3, db=env.app.db)
    invoice = app.create_invoice("25", "Private description")
    checkout = app.checkout_request(invoice["id"])
    assert checkout["recipient"] == resolved
    assert checkout["domainName"] == "SenFund"
    assert chain.recover(checkout) == app.merchant
    assert "description" not in checkout


def test_legacy_request_without_domain_still_recovers_merchant(env):
    invoice = env.app.create_invoice("25", "legacy compatibility")
    original = invoice["request"]
    original.pop("domainName")
    legacy = chain.sign_request(original, env.cfg.merchant_key)
    assert chain.typed(legacy)["domain"]["name"] == "SenFun"
    assert chain.recover(legacy) == env.app.merchant
