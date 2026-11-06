"""Deploy SenFundSettlement to Whitechain Sepolia (chain 1874) and write deployments/whitechain-sepolia.json.
Needs DEPLOYER_PRIVATE_KEY (funded with test WBT) in .env. Refuses any other chain."""
import json, os, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from eth_account import Account
from backend import devchain
from backend.config import ROOT, WHITECHAIN_SEPOLIA, load, web3_for

os.environ.setdefault("SENFUND_ENV", "testnet")
cfg = load()
w3 = web3_for(cfg)
if w3.eth.chain_id != WHITECHAIN_SEPOLIA["chain_id"]:
    raise RuntimeError(f"refusing: RPC is chain {w3.eth.chain_id}")
key = os.environ["DEPLOYER_PRIVATE_KEY"]
me = Account.from_key(key).address
print("deployer", me, "balance", w3.eth.get_balance(me) / 1e18, "WBT")
c = devchain.deploy(w3, "SenFundSettlement", me, key)
out = {"domainName": "SenFund", "chainId": 1874, "rpcUrl": WHITECHAIN_SEPOLIA["rpc_url"], "explorer": WHITECHAIN_SEPOLIA["explorer"],
       "settlement": c.address, "token": WHITECHAIN_SEPOLIA["usdt"], "tokenDecimals": 6, "confirmations": 2,
       "deployBlock": w3.eth.block_number}
(ROOT / "deployments" / "whitechain-sepolia.json").write_text(json.dumps(out, indent=2))
print("SenFundSettlement:", f"{WHITECHAIN_SEPOLIA['explorer']}/address/{c.address}")
