"""Check public demo prerequisites or export a verified Whitechain payment receipt."""
import argparse
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
from contextlib import closing
from decimal import Decimal
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from eth_account import Account
from web3 import Web3
from web3.exceptions import Web3Exception

from backend import chain, ens
from backend.config import ROOT, WHITECHAIN_SEPOLIA, load, setting, web3_for
from scripts.ens_record import nonzero_address

TOKEN = WHITECHAIN_SEPOLIA["usdt"]
CHAIN_ID = WHITECHAIN_SEPOLIA["chain_id"]
EXPLORER = WHITECHAIN_SEPOLIA["explorer"]
DECIMALS = WHITECHAIN_SEPOLIA["usdt_decimals"]
TOKEN_ABI = [
    {"type": "function", "name": "decimals", "stateMutability": "view", "inputs": [],
     "outputs": [{"type": "uint8"}]},
    {"type": "function", "name": "balanceOf", "stateMutability": "view", "inputs": [{"type": "address"}],
     "outputs": [{"type": "uint256"}]},
]


def verify_network(cfg, w3):
    if cfg.env != "testnet" or cfg.chain_id != CHAIN_ID or (cfg.token.lower(), cfg.token_decimals) != (TOKEN.lower(), DECIMALS):
        raise ValueError("configure the official Whitechain Sepolia token and testnet environment")
    if w3.eth.chain_id != CHAIN_ID:
        raise ValueError("the RPC did not return Whitechain Sepolia chain ID 1874")


def explorer_verified(address):
    request = Request(f"{EXPLORER}/api/v2/addresses/{address}", headers={"User-Agent": "SenFund demo preflight"})
    try:
        with urlopen(request, timeout=8) as response:
            data = json.load(response)
    except (URLError, OSError, ValueError):
        return False
    return (isinstance(data, dict) and data.get("is_verified") is True
            and str(data.get("hash", "")).lower() == address.lower())


def verify_contract(cfg, w3):
    address = nonzero_address(cfg.settlement)
    contract = w3.eth.contract(address=address, abi=chain.ABI)
    domain = contract.functions.eip712Domain().call()
    if (domain[1], domain[2], domain[3], domain[4].lower()) != (cfg.domain_name, "1", CHAIN_ID, address.lower()):
        raise ValueError("settlement domain does not match the configured SenFund deployment")
    if not explorer_verified(address):
        raise ValueError("Whitechain explorer did not confirm settlement source verification")
    return address


def check(cfg, w3, payer=None, deployer=None, amount=Decimal("25")):
    results = []

    def item(label, status, detail):
        results.append({"check": label, "status": status, "detail": detail})

    try:
        verify_network(cfg, w3)
        item("Whitechain Sepolia RPC", "pass", "Chain ID 1874")
    except Exception:
        item("Whitechain Sepolia RPC", "blocked", "Wrong network, token configuration or RPC unavailable")
        return results

    token = w3.eth.contract(address=TOKEN, abi=TOKEN_ABI)
    try:
        decimals = token.functions.decimals().call()
        token_ok = decimals == cfg.token_decimals == DECIMALS
        item("Official test USDT", "pass" if token_ok else "blocked", f"Token {TOKEN}, decimals {decimals}")
    except Exception:
        token_ok = False
        item("Official test USDT", "blocked", "Could not read token metadata")

    for label, supplied, key in (("Payer", payer, "PAYER_PRIVATE_KEY"), ("Deployer", deployer, "DEPLOYER_PRIVATE_KEY")):
        if label == "Deployer" and cfg.settlement and not supplied and not os.environ.get(key):
            item(label, "pass", "Existing deployment will be checked below")
            continue
        try:
            address = nonzero_address(supplied) if supplied else Account.from_key(os.environ[key]).address
        except (KeyError, ValueError):
            item(label, "blocked", f"Supply a public --{label.lower()} address or configure the local test wallet")
            continue
        try:
            gas = Decimal(w3.eth.get_balance(address)).scaleb(-18)
            detail = f"{address} has {gas:f} test WBT"
            enough = gas > 0
            if label == "Payer" and token_ok:
                units = Decimal(token.functions.balanceOf(address).call()).scaleb(-DECIMALS)
                detail += f" and {units:f} test USDT for a {amount:f} USDT demo"
                enough = enough and units >= amount
            item(label, "pass" if enough else "blocked", detail)
        except Exception:
            item(label, "blocked", "Could not read the wallet balances")

    try:
        merchant = Account.from_key(cfg.merchant_key).address
        item("Merchant signer", "pass", merchant)
    except ValueError:
        item("Merchant signer", "blocked", "Configure MERCHANT_PRIVATE_KEY locally with a test wallet")

    try:
        recipient = ens.resolve_recipient(cfg)
        item("ENSv2 recipient", "pass", recipient)
    except Exception:
        item("ENSv2 recipient", "blocked", "Configure the enrolled subname, dedicated resolver and Ethereum Sepolia RPC")

    try:
        settlement = verify_contract(cfg, w3)
        item("Whitechain settlement contract", "pass", f"{EXPLORER}/address/{settlement}")
    except Exception:
        item("Whitechain settlement contract", "blocked", "Deploy the SenFund contract and verify its source")

    cli = shutil.which(setting("SENFUND_CRE_CLI", "cre"))
    if cli:
        try:
            env = {key: os.environ[key] for key in ("HOME", "PATH", "USER", "TMPDIR", "XDG_CONFIG_HOME")
                   if key in os.environ}
            result = subprocess.run([cli, "whoami"], capture_output=True, timeout=10, check=False, env=env)
            item("Chainlink CRE", "pass" if result.returncode == 0 else "blocked",
                 "CLI account available" if result.returncode == 0 else "Run cre login locally")
        except (OSError, subprocess.TimeoutExpired):
            item("Chainlink CRE", "blocked", "Unable to confirm the CLI login")
    else:
        item("Chainlink CRE", "blocked", "Install the official CLI and run cre login locally")
    return results


def stored_payment(path, invoice):
    uri = Path(path).resolve().as_uri() + "?mode=ro"
    with closing(sqlite3.connect(uri, uri=True)) as db:
        db.row_factory = sqlite3.Row
        row = db.execute(
            """select i.request, r.tx_hash, r.block_hash, r.log_index
               from invoices i join receipts r on r.invoice = i.id
               where i.id = ? and i.payment = 'PAID' and i.needs_review = 0 and r.status = 'active'""",
            (invoice,),
        ).fetchone()
    if not row:
        raise ValueError("submit and confirm the payment in SenFund before exporting evidence")
    return json.loads(row["request"]), dict(row)


def build_evidence(cfg, w3, invoice):
    verify_network(cfg, w3)
    request, saved = stored_payment(cfg.db_path, invoice)
    confirmed = chain.verify_receipt(w3, cfg, request, saved["tx_hash"])
    if (confirmed["block_hash"], confirmed["log_index"]) != (saved["block_hash"], saved["log_index"]):
        raise ValueError("the saved receipt no longer matches the canonical settlement")
    settlement = verify_contract(cfg, w3)
    tx = confirmed["tx_hash"]
    receipt = w3.eth.get_transaction_receipt(tx)
    if chain._h(receipt["blockHash"]) != confirmed["block_hash"]:
        raise ValueError("the settlement block changed during export")
    transfer_topic = Web3.keccak(text="Transfer(address,address,uint256)")
    payer = bytes.fromhex(confirmed["payer"][2:]).rjust(32, b"\0")
    recipient = bytes.fromhex(request["recipient"][2:]).rjust(32, b"\0")
    transfers = [
        log["logIndex"] for log in receipt["logs"]
        if log["address"].lower() == TOKEN.lower()
        and list(log["topics"]) == [transfer_topic, payer, recipient]
        and len(log["data"]) == 32 and int.from_bytes(log["data"]) == int(confirmed["amount"])
        and log["logIndex"] < confirmed["log_index"]
    ]
    if len(transfers) != 1:
        raise ValueError("expected one matching official USDT Transfer before InvoiceSettled")
    return {
        "environment": "Whitechain Sepolia testnet", "chainId": CHAIN_ID, "invoice": request["invoiceId"],
        "digest": request["digest"], "contract": settlement, "verifiedContract": f"{EXPLORER}/address/{settlement}?tab=contract",
        "transaction": tx, "explorerTransaction": f"{EXPLORER}/tx/{tx}",
        "blockHash": confirmed["block_hash"], "blockNumber": confirmed["block_number"],
        "logIndex": confirmed["log_index"], "tokenTransferLogIndex": transfers[0], "confirmations": confirmed["confirmations"],
        "payer": confirmed["payer"], "recipient": request["recipient"], "token": TOKEN,
        "amountBaseUnits": confirmed["amount"],
        "amountTestUsdt": format(Decimal(f"{confirmed['amount']}e-{DECIMALS}"), "f"),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    doctor = commands.add_parser("check", help="Read-only readiness report")
    doctor.add_argument("--payer")
    doctor.add_argument("--deployer")
    doctor.add_argument("--amount", type=Decimal, default=Decimal("25"))
    export = commands.add_parser("evidence", help="Print public, verified Whitechain receipt JSON")
    export.add_argument("invoice")
    args = parser.parse_args()
    try:
        cfg = load()
        w3 = web3_for(cfg)
        if args.command == "check":
            if not args.amount.is_finite() or args.amount <= 0:
                parser.error("amount must be positive and finite")
            report = check(cfg, w3, args.payer, args.deployer, args.amount)
            print(json.dumps(report, indent=2))
            return int(any(row["status"] != "pass" for row in report))
        if not re.fullmatch(r"inv_[a-f0-9]{12}", args.invoice):
            parser.error("expected a SenFund dashboard invoice ID")
        print(json.dumps(build_evidence(cfg, w3, args.invoice), indent=2))
        return 0
    except (ValueError, RuntimeError, chain.VerificationError, sqlite3.Error) as error:
        print(f"Demo check failed: {error}", file=sys.stderr)
        return 1
    except (Web3Exception, OSError):
        print("Demo check failed: the chain or local evidence is unavailable", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
