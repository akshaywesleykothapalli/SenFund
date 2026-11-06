"""EIP-712 PaymentRequest signing and onchain receipt verification."""
import json
from eth_account import Account
from eth_account.messages import encode_typed_data
from web3 import Web3

from .config import ROOT

ABI = json.loads((ROOT / "contracts" / "out" / "SenFundSettlement.json").read_text())["abi"]
SETTLED_TOPIC = Web3.keccak(text="InvoiceSettled(bytes32,bytes32,address,address,address,address,uint256)").hex()
TYPES = {
    "EIP712Domain": [
        {"name": "name", "type": "string"}, {"name": "version", "type": "string"},
        {"name": "chainId", "type": "uint256"}, {"name": "verifyingContract", "type": "address"},
    ],
    "PaymentRequest": [
        {"name": "invoiceId", "type": "bytes32"}, {"name": "merchant", "type": "address"},
        {"name": "recipient", "type": "address"}, {"name": "token", "type": "address"},
        {"name": "amount", "type": "uint256"}, {"name": "expiry", "type": "uint256"},
    ],
}


def _h(x):
    x = x.hex() if isinstance(x, (bytes, bytearray)) else str(x)
    return (x if x.startswith("0x") else "0x" + x).lower()


def typed(req: dict) -> dict:
    return {
        "types": TYPES, "primaryType": "PaymentRequest",
        "domain": {"name": req.get("domainName", "SenFun"), "version": "1", "chainId": req["chainId"], "verifyingContract": req["contract"]},
        "message": {k: (int(req[k]) if k in ("amount", "expiry") else req[k]) for k in ("invoiceId", "merchant", "recipient", "token", "amount", "expiry")},
    }


def sign_request(req: dict, key: str) -> dict:
    signed = Account.sign_message(encode_typed_data(full_message=typed(req)), key)
    return {**req, "digest": _h(signed.message_hash), "signature": _h(signed.signature)}


def recover(req: dict) -> str:
    return Account.recover_message(encode_typed_data(full_message=typed(req)), signature=req["signature"])


class VerificationError(Exception):
    def __init__(self, code, msg=""):
        super().__init__(f"{code}: {msg}")
        self.code = code


def verify_receipt(w3, cfg, inv_req: dict, tx_hash: str) -> dict:
    """Return the matching InvoiceSettled log after every PRD check, else raise VerificationError.
    Raises code 'pending' when the tx is not mined or not yet confirmed (caller keeps it SUBMITTED)."""
    if w3.eth.chain_id != cfg.chain_id:
        raise VerificationError("wrong_network", f"rpc chain {w3.eth.chain_id} != {cfg.chain_id}")
    try:
        rc = w3.eth.get_transaction_receipt(tx_hash)
    except Exception:
        raise VerificationError("pending", "receipt not found yet")
    if rc["status"] != 1:
        raise VerificationError("reverted", "transaction failed onchain")
    tx = w3.eth.get_transaction(tx_hash)
    match = None
    for lg in rc["logs"]:
        if not lg["topics"] or _h(lg["topics"][0]) != _h(SETTLED_TOPIC):
            continue
        if lg["address"].lower() != cfg.settlement.lower():
            continue  # look-alike event from an untrusted contract
        if _h(lg["topics"][1]) != inv_req["invoiceId"].lower():
            continue
        match = lg
        break
    if match is None:
        raise VerificationError("no_settlement_event", "no InvoiceSettled from the trusted contract for this invoice")
    ev = w3.eth.contract(address=cfg.settlement, abi=ABI).events.InvoiceSettled().process_log(match)["args"]
    checks = {
        "digest": _h(ev["digest"]) == inv_req["digest"].lower(),
        "payer": ev["payer"].lower() == tx["from"].lower(),
        "merchant": ev["merchant"].lower() == inv_req["merchant"].lower(),
        "recipient": ev["recipient"].lower() == inv_req["recipient"].lower(),
        "token": ev["token"].lower() == inv_req["token"].lower() == cfg.token.lower(),
        "amount": int(ev["amount"]) == int(inv_req["amount"]),
    }
    bad = [k for k, ok in checks.items() if not ok]
    if bad:
        raise VerificationError("mismatch", ",".join(bad))
    canon = w3.eth.get_block(rc["blockNumber"])
    if _h(canon["hash"]) != _h(rc["blockHash"]):
        raise VerificationError("pending", "block not canonical")
    confs = w3.eth.block_number - rc["blockNumber"] + 1
    if confs < cfg.confirmations:
        raise VerificationError("pending", f"{confs}/{cfg.confirmations} confirmations")
    return {"tx_hash": _h(tx_hash), "log_index": match["logIndex"], "block_number": rc["blockNumber"],
            "block_hash": _h(rc["blockHash"]), "payer": ev["payer"], "amount": str(ev["amount"]), "confirmations": confs}
