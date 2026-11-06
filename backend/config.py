"""SenFund configuration. Testnet only: production and live payouts are refused at load time."""
import json
import os
from dataclasses import dataclass, replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

WHITECHAIN_SEPOLIA = {
    "chain_id": 1874,
    "name": "Whitechain Sepolia",
    "rpc_url": "https://rpc.testnet.whitechain.io",
    "explorer": "https://explorer.testnet.whitechain.io",
    "usdt": "0xcedfB56113143d55b2358b8CFbB0dEB5Ad2f55a7",  # official Whitechain test USDT
    "usdt_decimals": 6,
}
ALLOWED_ENVS = {"testnet", "local", "test"}


@dataclass(frozen=True)
class Config:
    env: str
    chain_id: int
    rpc_url: str
    explorer: str
    settlement: str
    token: str
    token_decimals: int
    merchant_key: str
    recipient: str
    confirmations: int
    db_path: str
    invoice_ttl: int = 3600
    from_block: int = 0
    domain_name: str = "SenFund"
    ens_rpc: str = ""
    ens_name: str = ""
    ens_resolver: str = ""
    cre_payouts: bool = False

    def with_(self, **kw):
        return replace(self, **kw)


def _load_dotenv(path: Path = ROOT / ".env"):
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


def setting(key: str, default=None):
    return os.environ.get(key, os.environ.get(key.replace("SENFUND_", "SENFUN_", 1), default))


def guard(env: str):
    if env not in ALLOWED_ENVS:
        raise RuntimeError(f"SENFUND_ENV={env!r} refused: this build runs on testnet/local only")
    if any(os.environ.get(key, "0") not in ("", "0", "false")
           for key in ("SENFUND_LIVE_PAYOUTS", "SENFUN_LIVE_PAYOUTS")):
        raise RuntimeError("Live payouts are disabled in this build")


def load() -> Config:
    _load_dotenv()
    env = setting("SENFUND_ENV", "testnet")
    guard(env)
    default_dep = "local.json" if env == "local" else "whitechain-sepolia.json"
    dep_path = Path(setting("SENFUND_DEPLOYMENT", ROOT / "deployments" / default_dep))
    dep = json.loads(dep_path.read_text()) if dep_path.exists() else {}
    chain_id = int(dep.get("chainId", WHITECHAIN_SEPOLIA["chain_id"]))
    if env == "testnet" and chain_id != WHITECHAIN_SEPOLIA["chain_id"]:
        raise RuntimeError(f"testnet env must use chain {WHITECHAIN_SEPOLIA['chain_id']}, got {chain_id}")
    default_db = ROOT / ".data" / f"senfund-{env}.sqlite3"
    legacy_db = ROOT / ".data" / f"senfun-{env}.sqlite3"
    return Config(
        env=env,
        chain_id=chain_id,
        rpc_url=setting("SENFUND_RPC_URL", dep.get("rpcUrl", WHITECHAIN_SEPOLIA["rpc_url"])),
        explorer=dep.get("explorer", WHITECHAIN_SEPOLIA["explorer"]),
        settlement=dep.get("settlement", ""),
        token=dep.get("token", WHITECHAIN_SEPOLIA["usdt"]),
        token_decimals=int(dep.get("tokenDecimals", WHITECHAIN_SEPOLIA["usdt_decimals"])),
        merchant_key=os.environ.get("MERCHANT_PRIVATE_KEY", dep.get("devMerchantKey", "")),
        recipient=os.environ.get("MERCHANT_RECIPIENT", dep.get("recipient", "")),
        confirmations=int(setting("SENFUND_CONFIRMATIONS", dep.get("confirmations", 2))),
        from_block=int(setting("SENFUND_FROM_BLOCK", dep.get("deployBlock", 0))),
        db_path=setting("SENFUND_DB", str(legacy_db if not default_db.exists() and legacy_db.exists() else default_db)),
        domain_name=dep.get("domainName", "SenFun" if dep.get("settlement") else "SenFund"),
        ens_rpc=setting("SENFUND_ENS_RPC", ""),
        ens_name=setting("SENFUND_ENS_NAME", ""),
        ens_resolver=setting("SENFUND_ENS_RESOLVER", ""),
        cre_payouts=setting("SENFUND_CRE_PAYOUTS", "0") == "1",
    )


def web3_for(cfg: Config):
    from web3 import Web3
    # The public Whitechain RPC rejects the default python-requests User-Agent with 403.
    return Web3(Web3.HTTPProvider(cfg.rpc_url, request_kwargs={"headers": {"User-Agent": "Mozilla/5.0 SenFund/0.1"}, "timeout": 20}))
