# SenFund Build Plan

Use [SenFund Requirements](SenFund%20Requirements.md) for the sponsor acceptance criteria and the production release gates.

1. **ENSv2 and checkout.** Backend invoice creation resolves the enrolled merchant address. Static checkout independently verifies the signature and pinned approval configuration, then compares the current ENS result. Use [ENSv2 setup](ENS_SETUP.md) to configure a real subname and record. Local tests cover the resolution and rejection paths. Public subname, permission delegation, rotation and hosted demo proof remain open.
2. **Whitechain settlement.** Compile the SenFund contract, validate checkout on the local chain, and use the Whitechain deployment script with funded test wallets. Verify the contract on the explorer and record the official test USDT payment. Demonstrate recovery with the merchant backend stopped.
3. **Chainlink CRE.** The [workflow and dashboard runner](../cre/README.md) are implemented for the demo. Complete an authenticated CLI simulation against public Whitechain and ENS evidence, then capture the workflow result and matching dashboard decision.
4. **Submission.** Use one walkthrough showing the issuer, payer, route decision and receipt. Include source, explorer links, verified ENS changes, CRE evidence and Whitechain feedback. The payout remains simulated.

## Wallet and corridors

- Each user links a Whitechain Sepolia (chain 1874) wallet by signing a personal_sign proof. The user signs in their own wallet.
- The Wallet view shows testnet balances from `GET /api/balance/<address>` (400 for a bad address, 502 if the RPC fails).
- "Withdraw to bank" gives a quote only (amount × rate − fee). It is labelled "Simulated — no money moves".
- Clients pay in test USDT. Corridors come from `/api/config`: IN, EU, MX, KE, AE and more. Conversion and payout stay simulated.
