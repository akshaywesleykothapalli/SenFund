# SenFund

SenFund lets you send USD invoices that customers pay in test USDT on Whitechain Sepolia (chain 1874). Each payment is verified onchain. The USD conversion and the INR payout are **simulated**. Mainnet and live payouts are disabled.

## Setup

Use Python 3.13 and Node.js 24 or later. The Next.js workspace and its HTTP API use the existing local Python settlement service for invoice signing, persistence, reconciliation and the CRE runner. Checkout is served independently so payer links keep working when either merchant process stops.
```
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
npm ci
(cd contracts && npm ci)
.venv/bin/python scripts/compile.py
```

## Run locally (no testnet needed)
Run each command in its own terminal:
```
.venv/bin/python scripts/local_chain.py                 # local RPC :8545, writes deployments/local.json
SENFUND_ENV=local .venv/bin/python -m backend.server     # app + dashboard :8700
SENFUND_ENV=local bash scripts/run_static.sh             # merchant site :8701, checkout :8702
npm run dev                                              # Next.js merchant workspace :3000
```
The checkout (:8702) is static and reads the chain directly, so payers can still pay and verify while the app is stopped. The dashboard scans recent confirmed blocks while catching up on older blocks. If a receipt has yet to appear, paste its payment transaction hash into the invoice’s **Submit tx hash** field.

## Whitechain Sepolia
1. Configure test-only keys from `.env.example`. Fund the payer with official test USDT and WBT, and the deployer with WBT.
2. Configure an enrolled merchant subname in ENSv2 on Ethereum Sepolia. See [ENSv2 setup](docs/ENS_SETUP.md).
3. Run `.venv/bin/python scripts/deploy.py`. Verify the contract on the Whitechain explorer using `contracts/out/SenFundSettlement.standard-input.json`.
4. Start the backend, `npm run dev` and `bash scripts/run_static.sh` in separate terminals. Open the [Next.js merchant workspace](http://127.0.0.1:3000/). The workspace binds to loopback for this demo. The static script builds `checkout/trust.json`. For separate hosting, publish the checkout directory including that generated file. Use a dedicated public, browser-accessible ENS RPC with no secrets.
5. Issue a new invoice, pay with the browser wallet and record the explorer transaction. For a command-line smoke test, use `.venv/bin/python scripts/pay.py <invoice-id>`.

Existing deployment metadata without a domain name uses its original signing domain, and older environment variables and default database paths are still recognized. New deployments use the SenFund domain. Use a fresh database when intentionally switching to a new deployment, so stored invoices stay associated with the contract that signed them.

## Verified demo

Invoice `inv_4fe69ac0f479` settled **3 test USDT** to the Whitechain address resolved from `merchant.senfund.eth` on Ethereum Sepolia. After the ENS registration finalized, the local Chainlink CRE simulation selected Mudrex and recorded a simulated **₹160.00** payout.

- [ENSv2 merchant name](https://sepolia.explorer.ens.domains/merchant.senfund.eth)
- [Whitechain settlement transaction](https://explorer.testnet.whitechain.io/tx/0xca8d066095a407552697f77dc866ae939390712a87e38eabb12dc52efc342c62)
- [Verified settlement contract](https://explorer.testnet.whitechain.io/address/0x613677fc94907367944DE1f0E4B88C44488B9B58?tab=contract)

## Public demo evidence

Run `.venv/bin/python scripts/demo.py check --payer <public-address> --deployer <public-address>` for a read-only readiness report. The check uses a 25 USDT demo amount by default. Pass `--amount` for another invoice amount. The report checks Whitechain, the official token, funding, ENS resolution, the deployed contract and the CRE login.

After Whitechain source verification and a confirmed invoice payment, run `.venv/bin/python scripts/demo.py evidence <invoice-id>`. The exporter checks the canonical receipt and the matching official USDT transfer, then prints public JSON containing the explorer links, token amount and log indexes. Save the JSON if you need a machine-readable record for submission.

## Demo both payout routes

Create and pay a separate test invoice for each run, verify its onchain payment, and run simulated USD conversion.

- **Mudrex succeeds** completes the simulated INR payout on the primary route.
- **Mudrex unavailable → P2P fallback** opens a simulated P2P order and waits for **Simulate bank credit**. The receipt records the route, fallback reason, and simulated order reference.
- **Mudrex accepts order, response lost** puts the payout on hold. Re-running checks the saved order before retrying. An uncertain primary order never triggers a second payout through P2P.

Both routes use local fixtures and move zero real INR. Live routes require separate provider approval, a supported production network, and verified bank payout evidence.

## Chainlink CRE

[Run the Chainlink CRE payout demo](cre/README.md). Set `SENFUND_CRE_PAYOUTS=1` to gate the dashboard payout behind the CLI simulation.

## Tests
```
.venv/bin/python -m pytest -q tests
node --test tests/checkout.test.cjs
npm run build
```
The tests cover tampered invoices, wrong chain or token, duplicate settlement, uncertain payout retries, and recovery with the app stopped. GitHub Actions builds the contracts, runs these suites, and checks the CRE workflow types without testnet keys.

## Submission docs
`docs/SenFund Requirements.md`, `docs/BUILD_PLAN.md`, `docs/prompts/`, `AI_USE.md`, `THIRD_PARTY_NOTICES.md`, `WHITECHAIN_FEEDBACK.md`.

## Invoice creation retries

Send an `Idempotency-Key` header when creating an invoice through the local merchant API. Generate a new key for each intended invoice, and reuse it when retrying the same request after a timeout. The service returns the original invoice and checkout link, including after a restart. Reusing a key with different invoice details returns HTTP 409.

The responsive website and a future mobile client can share the invoice contract and signed checkout format. The current merchant API binds to loopback. A native client on a separate device requires an authenticated, HTTPS merchant API deployment.
