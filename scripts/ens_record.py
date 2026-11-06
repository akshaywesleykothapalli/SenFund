"""Prepare unsigned Ethereum Sepolia ENSv2 record transactions for the owner's wallet."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from web3 import Web3

from backend.ens import SEPOLIA, WHITECHAIN_COIN_TYPE, dns_name


def nonzero_address(value):
    if not Web3.is_address(value) or int(value, 16) == 0:
        raise ValueError("expected a nonzero EVM address")
    return Web3.to_checksum_address(value)


def calldata(signature, types, values):
    return Web3.keccak(text=signature)[:4] + Web3().codec.encode(types, values)


def build_transaction(name, resolver, recipient, delegate=None):
    wire_name = dns_name(name)
    if len(name.split(".")) < 3:
        raise ValueError("use an enrolled merchant subname")
    recipient = nonzero_address(recipient)
    resolver = nonzero_address(resolver)
    data = calldata("setAddress(bytes,uint256,bytes)", ["bytes", "uint256", "bytes"],
                    [wire_name, WHITECHAIN_COIN_TYPE, bytes.fromhex(recipient[2:])])
    if delegate:
        data = calldata("grantSetterRoles(bytes,address)", ["bytes", "address"], [data, nonzero_address(delegate)])
    return {"chainId": SEPOLIA, "to": resolver, "value": "0x0", "data": Web3.to_hex(data)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--name", required=True)
    parser.add_argument("--resolver", required=True)
    parser.add_argument("--recipient", required=True, help="Whitechain recipient wallet")
    parser.add_argument("--delegate", help="Prepare the owner role grant instead of a record update")
    args = parser.parse_args()
    try:
        tx = build_transaction(args.name, args.resolver, args.recipient, args.delegate)
    except ValueError as error:
        parser.error(str(error))
    print(json.dumps(tx, indent=2))


if __name__ == "__main__":
    main()
