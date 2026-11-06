"""Deploy and pay helpers shared by tests, the local dev chain and the testnet scripts."""
import json
from web3 import Web3
from .config import ROOT


def artifact(name):
    a = json.loads((ROOT / "contracts" / "out" / f"{name}.json").read_text())
    return a["abi"], a["bytecode"]


def send(w3, fn, sender, key=None):
    """Send a contract call from an unlocked account (eth-tester) or sign with key (real RPC)."""
    if key is None:
        return w3.eth.wait_for_transaction_receipt(fn.transact({"from": sender}))
    tx = fn.build_transaction({"from": sender, "nonce": w3.eth.get_transaction_count(sender), "chainId": w3.eth.chain_id})
    signed = w3.eth.account.sign_transaction(tx, key)
    return w3.eth.wait_for_transaction_receipt(w3.eth.send_raw_transaction(signed.raw_transaction), timeout=180)


def deploy(w3, name, sender, key=None, *args):
    abi, bc = artifact(name)
    rc = send(w3, w3.eth.contract(abi=abi, bytecode=bc).constructor(*args), sender, key)
    return w3.eth.contract(address=rc["contractAddress"], abi=abi)


def pay(w3, req, payer, key=None, token_abi_name="MockUSDT"):
    """approve + settle exactly as the static checkout does. Returns the settle receipt."""
    token = w3.eth.contract(address=Web3.to_checksum_address(req["token"]), abi=artifact(token_abi_name)[0])
    settle = w3.eth.contract(address=Web3.to_checksum_address(req["contract"]), abi=artifact("SenFundSettlement")[0])
    send(w3, token.functions.approve(settle.address, int(req["amount"])), payer, key)
    return send(w3, settle.functions.settle(req["invoiceId"], req["merchant"], req["recipient"], req["token"],
                                             int(req["amount"]), int(req["expiry"]), req["signature"]), payer, key)
