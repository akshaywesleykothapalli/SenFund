# SenFund CRE and CCIP 2.0 local demo

## Run it on this Mac

```sh
cd "$HOME/Desktop/SenFund"
export PATH="$HOME/Desktop/SenFund/.data/tools:$PATH"
.venv/bin/python scripts/ccip_demo.py --case success
```

The Desktop repo uses its existing testnet credentials, Python dependencies and local CRE tools. The included paid-invoice fixture targets the enrolled Sepolia ENS name. The runner starts SenFund's HTTP backend on a free loopback port, opens a fresh database seeded with public payment fields, and deploys the CCIP contracts into a fresh in-memory EVM. It prints the results and saves raw CRE output, the trigger, the exit status, and the app/contract proof under `.data/`. Use `--output /path/to/new-directory` to capture to a specific location.

## Run from the website

In the Desktop repo, configure the existing testnet merchant signing key in the ignored `.env` using the same signer as your checkout. Keep the configured Sepolia ENS name, resolver and public RPC. Compile the CCIP contracts if needed. With ports 8700 and 8702 free, run these in separate terminals from the copy:

```sh
export PATH="$HOME/Desktop/SenFund/.data/tools:$PATH"
SENFUND_ENV=testnet SENFUND_CRE_PAYOUTS=1 SENFUND_CCIP_LOCAL=1 .venv/bin/python -m backend.server
```

```sh
sh scripts/run_static.sh
```

Open the [local dashboard](http://127.0.0.1:8700/), or start `npm run dev` and use the Next.js dashboard. Create a small test invoice and open its signed link. Checkout displays the live ENSv2 recipient match before enabling payment. The client uses their testnet wallet to pay on Whitechain Sepolia. Verify the receipt, simulate conversion, then choose **Run CRE + CCIP simulation**. The invoice displays the finalized ENS match, the CCIP receiver state change and message ID, and the resulting simulated payout. The CCIP EVM is local to the backend process and resets on restart.

The local website defaults to Sepolia ENS. For mainnet ENS, follow [ENS setup](ENS_SETUP.md) and use a newly paid invoice tied to that mainnet record. The Whitechain payment and Chainlink Local delivery still use test environments. [Official ENS bounty criteria](https://ethglobal.com/events/mumbai/prizes/ens)

## Show the reviewer

| Case | What the output should prove |
| --- | --- |
| `--case success` | CRE matches the live Whitechain receipt, finalized ENS recipient, and current HTTP provider snapshot. The CCIP receiver moves from route `0` to `1`. The simulated primary payout becomes `COMPLETED`. |
| `--case mudrex_unavailable` | CRE selects P2P before primary dispatch. The CCIP receiver moves from route `0` to `2`. The simulated P2P order waits for bank credit. |
| `--case timeout_recovery` | The first attempt receives a primary authorization, then the simulated provider times out. A retry during a simulated outage returns `HOLD`. The receiver still shows route `1` and the app creates zero orders. |

1. Open the [public Whitechain receipt](https://explorer.testnet.whitechain.io/tx/0xca8d066095a407552697f77dc866ae939390712a87e38eabb12dc52efc342c62) for the 3 test-USDT payment.
2. Run the `success` case. Open the generated `cli.stdout` and point to the result's run ID and four passed checks. The workflow reads Ethereum Sepolia ENS directly and obtains settlement and provider evidence from the backend over HTTP. The provider is simulated.
3. Open `proof.json`. Match the CRE run ID and invoice digest to the CCIP approval. Show the local message ID, transaction hash, receiver state before and after, and resulting simulated payout. The normal payout HTTP handler uses the relay in this demo. The handler can dispatch only after the relay reads a matching approval from the receiver.
4. Run `timeout_recovery` or show its captured proof. To show how the contract handles invalid deliveries, run `.venv/bin/python -m pytest -q tests/test_ccip_local.py`. The tests cover repeated delivery, conflicting routes, non-operator submissions, expired or altered signatures, wrong chain and sender, and a direct receiver call.

### Captured proof

- [Primary payout](evidence/combined-success/success/proof.json) and [CRE transcript](evidence/combined-success/success/cli.stdout)
- [P2P fallback](evidence/combined-fallback/mudrex_unavailable/proof.json) and [CRE transcript](evidence/combined-fallback/mudrex_unavailable/cli.stdout)
- [First attempt timed out](evidence/combined-timeout/timeout/proof.json), then [CRE blocked fallback](evidence/combined-timeout/mudrex_unavailable/proof.json)

The first timeout test encountered a transient receipt lookup failure and held the payout before CCIP delivery. A rerun completed both timeout steps. If a public RPC stalls during the walkthrough, the captured transcripts are available above.

## What was built

- [CRE workflow](../cre/payout/main.ts) validates the input receipt and run challenge, resolves the finalized ENS record, and compares the provider response to the pre-run snapshot. It reports the four checks in its decision. [The backend](../backend/cre_payout.py) verifies those checks, matches the result to the current run and receipt, and rechecks both live settlement and provider state before dispatch.
- [CCIP sender and receiver](../contracts/src/PayoutDecisionCCIP.sol) use CCIP 2.0 `ExtraArgsV3` with the default finalized delivery policy. A locally generated operator key signs a short-lived authorization bound to the destination contract, invoice digest, settlement transaction and block, log index, recipient, run ID, and route. The destination accepts only the configured router, source selector and sender. It records one route per digest.
- [Local relay](../backend/ccip_local.py) submits the signed authorization through Chainlink's router, checks that the send and receive events agree, and reads the persisted approval before the simulated provider can be called.

CRE makes live reads against Whitechain Sepolia and Ethereum Sepolia. CCIP uses the official Chainlink Local 0.3.1 router and CCIP 2.0.0 contracts on a single local EVM. The Ethereum Sepolia and Polygon Amoy selectors represent the logical lane in this simulation. The router delivers synchronously, so the recorded transaction and message IDs are local, and public explorer links apply only to the underlying Whitechain payment. This demo uses a trusted local operator relay to bridge the CRE CLI result into CCIP. Sponsor acceptance of local-router evidence for the CCIP bounty remains to be confirmed. [ETHGlobal bounty requirements](https://ethglobal.com/events/mumbai/prizes/chainlink) · [Chainlink Local behavior](https://docs.chain.link/chainlink-local/learn/ccip-v2-local)

## Setup on a fresh checkout

1. Follow the [root README](../README.md) Python and settlement-contract setup. Run `npm --prefix cre/payout ci`.
2. Install Bun and the CRE CLI, add them to PATH, and verify the CRE session with `cre whoami`. Log in if needed. Configure `SENFUND_ENV=testnet`, `SENFUND_ENS_NAME=merchant.senfund.eth`, `SENFUND_ENS_RESOLVER=0x0a2b85e2472e7549D79dB010CcbdfA52E00C38d3` and a working Ethereum Sepolia HTTPS RPC as `SENFUND_ENS_RPC`. The runner enables CRE itself and uses its own test database. No merchant signing key is needed.
3. Run `.venv/bin/python scripts/compile_ccip.py`. It fetches and verifies the pinned Solidity source archives and builds the local router, sender and receiver. Then run the demo command.
