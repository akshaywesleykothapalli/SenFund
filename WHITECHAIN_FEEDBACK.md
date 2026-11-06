# Whitechain developer feedback

- The public RPC (`https://rpc.testnet.whitechain.io`) returns HTTP 403 for the default python-requests User-Agent. A browser-like User-Agent works. This is not documented, and it breaks web3.py out of the box.
- It is unclear whether Whitechain Sepolia supports the Cancun EVM version. The contracts build with `evmVersion: cancun` (OpenZeppelin 5 uses `mcopy`). If deployment fails, recompile for `paris`/`shanghai`. To confirm during deployment.
- The test USDT address (`0xcedf…55a7`, 6 decimals) was hard to find from the docs.
