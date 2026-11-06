"""Generate public checkout trust configuration from the operator's local setup."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from eth_account import Account
from web3 import Web3
from backend.config import ROOT, WHITECHAIN_SEPOLIA, load
from backend.ens import SEPOLIA, UNIVERSAL_RESOLVER, WHITECHAIN_COIN_TYPE, dns_name


def main():
    cfg = load()
    if not cfg.settlement or not cfg.merchant_key:
        raise ValueError("deploy settlement and configure the merchant signing key first")
    trust = {
        "chainId": cfg.chain_id, "contract": cfg.settlement, "token": cfg.token,
        "tokenDecimals": cfg.token_decimals, "merchant": Account.from_key(cfg.merchant_key).address,
    }
    if cfg.env == "testnet":
        dns_name(cfg.ens_name)
        if cfg.token.lower() != WHITECHAIN_SEPOLIA["usdt"].lower() or cfg.token_decimals != 6:
            raise ValueError("checkout requires official Whitechain test USDT")
        if not Web3.is_address(cfg.ens_resolver) or not cfg.ens_rpc.startswith("https://"):
            raise ValueError("configure the enrolled ENS resolver and a public HTTPS RPC without credentials")
        trust["ens"] = {"name": cfg.ens_name, "chainId": SEPOLIA, "rpc": cfg.ens_rpc,
                        "universalResolver": UNIVERSAL_RESOLVER, "resolver": cfg.ens_resolver,
                        "coinType": WHITECHAIN_COIN_TYPE}
    else:
        trust["recipient"] = Web3.to_checksum_address(cfg.recipient)
    target = ROOT / "checkout" / "trust.json"
    target.write_text(json.dumps(trust, indent=2) + "\n")
    print(f"Wrote public trust configuration to {target}")


if __name__ == "__main__":
    main()
