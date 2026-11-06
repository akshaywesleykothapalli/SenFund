import pytest
from eth_account import Account
from web3 import EthereumTesterProvider, Web3

from backend import devchain
from backend.config import Config
from backend.service import SenFund

MERCHANT = Account.from_key("0x" + "11" * 32)
RECIPIENT = "0x000000000000000000000000000000000000bEEF"


@pytest.fixture
def env(tmp_path):
    w3 = Web3(EthereumTesterProvider())
    payer = w3.eth.accounts[0]
    usdt = devchain.deploy(w3, "MockUSDT", payer)
    settle = devchain.deploy(w3, "SenFundSettlement", payer)
    devchain.send(w3, usdt.functions.mint(payer, 10_000 * 10**6), payer)
    cfg = Config(env="test", chain_id=w3.eth.chain_id, rpc_url="", explorer="https://explorer.testnet.whitechain.io",
                 settlement=settle.address, token=usdt.address, token_decimals=6, merchant_key=MERCHANT.key.hex(),
                 recipient=RECIPIENT, confirmations=2, db_path=str(tmp_path / "t.sqlite3"))
    app = SenFund(cfg, w3=w3)

    class E: pass
    e = E()
    e.w3, e.payer, e.usdt, e.settle, e.cfg, e.app = w3, payer, usdt, settle, cfg, app
    e.mine = lambda n=1: [w3.testing.mine() for _ in range(n)]
    return e
