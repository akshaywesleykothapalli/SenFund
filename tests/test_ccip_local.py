import pytest
from eth_tester.exceptions import TransactionFailed
from web3 import Web3

from backend.ccip_local import LocalPayoutRelay, SOURCE_SELECTOR
from backend.state import InvalidTransition


@pytest.fixture
def relay():
    return LocalPayoutRelay()


@pytest.fixture
def receipt(relay):
    return {
        "digest": "0x" + "11" * 32,
        "txHash": "0x" + "22" * 32,
        "blockHash": "0x" + "33" * 32,
        "recipient": relay.w3.eth.accounts[1],
        "logIndex": 2,
    }


def test_delivery_mutates_receiver_once_and_cannot_change_route(relay, receipt):
    first = relay.authorize(receipt, "aa" * 16, "USE_MUDREX")
    assert (first["beforeRoute"], first["afterRoute"]) == (0, 1)
    assert first["transactionHash"]
    retry = relay.authorize(receipt, "bb" * 16, "USE_MUDREX")
    assert retry["reused"] and retry["messageId"] == first["messageId"]
    with pytest.raises(InvalidTransition, match="does not match"):
        relay.authorize(receipt, "cc" * 16, "USE_P2P")
    duplicate = relay.envelope(receipt, "dd" * 16, "USE_MUDREX")
    send = relay.sender.functions.sendDecision(relay.receiver.address, *duplicate)
    tx = send.transact({"from": relay.operator.address, "gas": 1_000_000})
    assert relay.w3.eth.get_transaction_receipt(tx).status == 0


def test_sender_rejects_non_operator(relay, receipt):
    envelope = relay.envelope(receipt, "aa" * 16, "USE_MUDREX")
    send = relay.sender.functions.sendDecision(relay.receiver.address, *envelope)
    with pytest.raises(TransactionFailed):
        send.transact({"from": relay.w3.eth.accounts[0]})
    assert relay.receiver.functions.approvals(receipt["digest"]).call()[3] == 0


@pytest.mark.parametrize("failure", ["expired", "tampered", "wrong-chain", "wrong-sender", "direct-call"])
def test_receiver_rejects_invalid_delivery(relay, receipt, failure):
    latest = relay.w3.eth.get_block("latest").timestamp
    expires = latest - 1 if failure == "expired" else latest + 60
    decision, signature = relay.envelope(receipt, "aa" * 16, "USE_MUDREX", expires_at=expires)
    if failure == "tampered":
        decision = (*decision[:-1], 2)
    sender = relay.w3.eth.accounts[0] if failure == "wrong-sender" else relay.sender.address
    selector = SOURCE_SELECTOR + 1 if failure == "wrong-chain" else SOURCE_SELECTOR
    if failure in {"expired", "tampered"}:
        send = relay.sender.functions.sendDecision(relay.receiver.address, decision, signature)
        tx = send.transact({"from": relay.operator.address, "gas": 1_000_000})
        assert relay.w3.eth.get_transaction_receipt(tx).status == 0
    else:
        codec = relay.w3.codec
        data = codec.encode(["(bytes32,bytes32,bytes32,address,bytes16,uint64,uint32,uint8)", "bytes"],
                            [decision, signature])
        message = (Web3.keccak(text=failure), selector, codec.encode(["address"], [sender]), data, [])
        if failure == "direct-call":
            with pytest.raises(TransactionFailed):
                relay.receiver.functions.ccipReceive(message).transact({"from": relay.w3.eth.accounts[0]})
        else:
            # The official local router exposes this test hook to inject the inbound message fields.
            execute = relay.router.functions.routeMessage(message, 5_000, 300_000, relay.receiver.address)
            success, _, _ = execute.call({"from": relay.w3.eth.accounts[0], "gas": 1_000_000})
            assert not success
    assert relay.receiver.functions.approvals(receipt["digest"]).call()[3] == 0
