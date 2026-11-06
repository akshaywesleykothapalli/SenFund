"""Local dev chain: eth-tester behind a tiny JSON-RPC server on :8545, with MockUSDT + SenFundSettlement deployed.
Writes deployments/local.json. Import one of the printed funded keys into a browser wallet to try the checkout."""
import json, re, sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from eth_account import Account
from eth_tester import EthereumTester, PyEVMBackend
from web3 import EthereumTesterProvider, Web3
from backend import devchain
from backend.config import ROOT

# Well-known throwaway dev keys (publicly known, never use with real funds).
PAYER = Account.from_key("0x" + "22" * 32)
MERCHANT = Account.from_key("0x" + "11" * 32)
RECIPIENT = "0x000000000000000000000000000000000000bEEF"

tester = EthereumTester(PyEVMBackend())
provider = EthereumTesterProvider(tester)
w3 = Web3(provider)
dep = w3.eth.accounts[0]
for a in (PAYER.address, MERCHANT.address):
    w3.eth.send_transaction({"from": dep, "to": a, "value": 100 * 10**18})
usdt = devchain.deploy(w3, "MockUSDT", dep)
settle = devchain.deploy(w3, "SenFundSettlement", dep)
devchain.send(w3, usdt.functions.mint(PAYER.address, 100_000 * 10**6), dep)
out = {"domainName": "SenFund", "chainId": w3.eth.chain_id, "rpcUrl": "http://127.0.0.1:8545", "explorer": "", "settlement": settle.address,
       "token": usdt.address, "tokenDecimals": 6, "devMerchantKey": MERCHANT.key.hex(), "recipient": RECIPIENT,
       "confirmations": 1, "payerKey": PAYER.key.hex()}
(ROOT / "deployments").mkdir(exist_ok=True)
(ROOT / "deployments" / "local.json").write_text(json.dumps(out, indent=2))
print(json.dumps({k: out[k] for k in ("chainId", "settlement", "token")}), "\nPayer (dev key, test only):", PAYER.address)


QTY = {"nonce", "gas", "gasPrice", "value", "maxFeePerGas", "maxPriorityFeePerGas", "chainId", "fromBlock", "toBlock"}


def _int(v):
    return int(v, 16) if isinstance(v, str) and v.startswith("0x") else v


def native(method, params):
    # eth-tester wants Python ints where JSON-RPC sends hex quantities.
    snake = lambda k: re.sub(r"(?<!^)([A-Z])", r"_\1", k).lower()
    fix = lambda d: {snake(k): _int(v) if k in QTY else v for k, v in d.items()} if isinstance(d, dict) else d
    params = [fix(p) for p in params]
    if method == "eth_getBlockByNumber" and params:
        params[0] = _int(params[0])
    return params


def wire(v):
    # ...and returns snake_case keys with ints; JSON-RPC clients expect camelCase and hex.
    if isinstance(v, dict):
        return {re.sub(r"_([a-z])", lambda m: m.group(1).upper(), k): wire(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [wire(x) for x in v]
    if isinstance(v, bool) or v is None:
        return v
    if isinstance(v, int):
        return hex(v)
    if isinstance(v, bytes):
        return "0x" + v.hex()
    return v


class RPC(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "content-type")

    def do_OPTIONS(self):
        self.send_response(204); self._cors(); self.end_headers()

    def do_POST(self):
        req = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        reqs = req if isinstance(req, list) else [req]
        res = []
        for r in reqs:
            try:
                out = provider.make_request(r["method"], native(r["method"], r.get("params", [])))
            except Exception as e:  # report instead of dropping the connection
                out = {"error": {"code": -32000, "message": str(e)}}
            if r["method"] in ("eth_sendRawTransaction", "eth_sendTransaction") and "result" in out:
                tester.mine_blocks(1)  # automine
            res.append({"jsonrpc": "2.0", "id": r.get("id"), **{k: wire(v) if k == "result" else v for k, v in out.items() if k in ("result", "error")}})
        body = json.dumps(res if isinstance(req, list) else res[0], default=lambda b: "0x" + b.hex() if isinstance(b, bytes) else str(b)).encode()
        self.send_response(200); self._cors(); self.send_header("Content-Type", "application/json"); self.end_headers()
        self.wfile.write(body)


print("Local RPC on http://127.0.0.1:8545 (Ctrl+C to stop; state is in memory)")
ThreadingHTTPServer(("127.0.0.1", 8545), RPC).serve_forever()
