"""Resolve an enrolled merchant's explicit Whitechain address on ENSv2."""
import re
from dataclasses import dataclass

from web3 import Web3
from web3.exceptions import ContractLogicError

WHITECHAIN_COIN_TYPE = 0x80000000 | 1874
RESOLVER_NOT_FOUND = "0x" + Web3.keccak(text="ResolverNotFound(bytes)")[:4].hex()


@dataclass(frozen=True)
class Network:
    chain_id: int
    label: str
    universal_resolver: str
    cre_target: str


# Pin the ENSv2 entry points so mainnet does not silently use an ENSv1 resolver.
NETWORKS = {
    "sepolia": Network(11155111, "Ethereum Sepolia",
                       Web3.to_checksum_address("0x24e1d8e068620b647ca097f961a61055f4f42d72"), "staging-settings"),
    "mainnet": Network(1, "Ethereum mainnet",
                       Web3.to_checksum_address("0x06fdd07f007adac667177b46ab2eb9a75132cfd5"), "ens-mainnet-settings"),
}


def network(name):
    if name not in NETWORKS:
        raise ValueError("SENFUND_ENS_NETWORK must be sepolia or mainnet")
    return NETWORKS[name]


def dns_name(name):
    # The demo enrolls lowercase ASCII .eth names only.
    labels = name.split(".")
    if len(labels) < 2 or labels[-1] != "eth" or any(not re.fullmatch(r"[a-z0-9-]{1,63}", label) for label in labels):
        raise ValueError("set an enrolled lowercase ASCII .eth name")
    encoded = b"".join(bytes([len(label)]) + label.encode("ascii") for label in labels) + b"\0"
    if len(encoded) > 255:
        raise ValueError("ENS name is too long")
    return encoded


def resolve_recipient(cfg, w3=None):
    deployment = network(cfg.ens_network)
    name = dns_name(cfg.ens_name)
    if not cfg.ens_rpc or not Web3.is_address(cfg.ens_resolver):
        raise ValueError(f"configure the {deployment.label} RPC and enrolled ENSv2 resolver")
    w3 = w3 or Web3(Web3.HTTPProvider(cfg.ens_rpc, request_kwargs={"timeout": 10}))
    if w3.eth.chain_id != deployment.chain_id:
        raise ValueError(f"ENS RPC must be {deployment.label}")
    block = w3.eth.block_number

    def resolve(profile, result_type):
        query = Web3.keccak(text=f"{profile}(bytes32,uint256)")[:4] + w3.codec.encode(
            ["bytes32", "uint256"], [bytes(32), WHITECHAIN_COIN_TYPE]
        )
        data = Web3.keccak(text="resolve(bytes,bytes)")[:4] + w3.codec.encode(["bytes", "bytes"], [name, query])
        try:
            raw = w3.eth.call({"to": deployment.universal_resolver, "data": data}, block_identifier=block)
        except ContractLogicError as error:
            if isinstance(error.data, str) and error.data.startswith(RESOLVER_NOT_FOUND):
                raise ValueError(f"No ENSv2 resolver for {cfg.ens_name} on {deployment.label}") from error
            raise
        result, resolver = w3.codec.decode(["bytes", "address"], raw)
        if resolver.lower() != cfg.ens_resolver.lower():
            raise ValueError("ENS resolved through a different merchant resolver")
        return w3.codec.decode([result_type], result)[0]

    if not resolve("hasAddr", "bool"):
        raise ValueError("ENS name has no explicit Whitechain address")
    address = resolve("addr", "bytes")
    if len(address) != 20 or not any(address):
        raise ValueError("invalid ENS Whitechain address")
    return Web3.to_checksum_address(address)
