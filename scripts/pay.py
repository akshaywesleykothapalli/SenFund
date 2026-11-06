"""Pay a SenFund invoice from the command line (same approve+settle as the checkout).
Usage: scripts/pay.py <invoice id>   (needs PAYER_PRIVATE_KEY in .env, or payerKey in deployments/local.json)"""
import json, os, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from eth_account import Account
from backend import chain, devchain, ens
from backend.config import ROOT, load, web3_for
from backend.service import SenFund

cfg = load()
w3 = web3_for(cfg)
key = os.environ.get("PAYER_PRIVATE_KEY")
if not key and cfg.env == "local":
    key = json.loads((ROOT / "deployments" / "local.json").read_text()).get("payerKey")
if not key:
    raise RuntimeError("configure a funded testnet payer key")
req = SenFund(cfg, w3=w3).checkout_request(sys.argv[1])
if w3.eth.chain_id != req["chainId"] or req["token"].lower() != cfg.token.lower() or req["contract"].lower() != cfg.settlement.lower():
    raise RuntimeError("RPC chain or invoice configuration does not match")
recipient = ens.resolve_recipient(cfg) if cfg.env == "testnet" else cfg.recipient
if req["recipient"].lower() != recipient.lower():
    raise RuntimeError("merchant payment address changed")
payer = Account.from_key(key).address
contract = w3.eth.contract(address=cfg.settlement, abi=chain.ABI)
_, valid, state = contract.functions.checkRequest(req["invoiceId"], req["merchant"], req["recipient"], req["token"],
                                                  int(req["amount"]), req["expiry"], req["signature"]).call({"from": payer})
if not valid or state or w3.eth.get_block("latest")["timestamp"] > req["expiry"]:
    raise RuntimeError("invalid signature or invoice is no longer payable")
rc = devchain.pay(w3, req, payer, key)
print("settle tx:", chain._h(rc["transactionHash"]), "status", rc["status"])
