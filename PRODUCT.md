# Product

<!-- impeccable:product-schema 1 -->

> Facts marked *(inferred)* come from repository docs and copy, not a user interview. Confirm or correct them.

## Platform

web

## Users

- Primary: freelancers and small businesses outside the US who bill US clients in USD and want the money in their local bank account. *(inferred from workspace copy)*
- Secondary: the payer (the US client), who opens a checkout link and pays an invoice from a browser wallet.
- Evaluators: hackathon judges reviewing the Whitechain, ENS and Chainlink CRE integration. *(inferred from SUBMISSION.md)*

## Product Purpose

SenFund lets a merchant send a USD invoice that the client pays in USDT on Whitechain. Each payment is verified onchain. SenFund then converts the USD and pays out in the merchant's local currency. Success: an invoice settles onchain and the payout reaches the merchant with a verifiable receipt.

## Positioning

- Every payment is verified against an onchain settlement contract and an official token transfer, not a processor's word.
- The merchant identity resolves through an ENSv2 name (e.g. `merchant.senfund.eth`).
- A Chainlink CRE workflow picks the payout route. It falls back from the primary provider to P2P without ever paying twice.

## Operating Context

- The merchant workspace is a Next.js app on :3000. It runs with a local Python settlement service.
- The checkout (:8702) is static and reads the chain directly, so payers can still pay while the merchant app is down.
- Flows: onboarding with a corridor picker, invoice issue, payer checkout, payment verification, simulated conversion, and payout with a recovery path.
- There is an optional LLM drafter for invoice notes, with a template fallback, and a payout advisor line.

## Capabilities and Constraints

- Testnet only: Whitechain Sepolia (chain 1874) and Ethereum Sepolia for ENS. Mainnet and live payouts are disabled.
- USD conversion and local-currency payout are **simulated**. No real fiat moves.
- Payout routes: Mudrex as the primary route, with P2P fallback. If a primary order's outcome is uncertain, the payout goes on hold rather than retrying through P2P.
- The product targets many payout currencies (INR, EUR, GBP, PHP, NGN, BRL and more). Today the workspace offers only the India (INR) and EU (EUR) corridors. INR is not the primary currency.
- Open: which other corridors come next, and live provider approval.

## Brand Commitments

- Name: SenFund.
- Voice: plain, factual, and honest about what is simulated. Copy must label simulated steps as simulated.

## Evidence on Hand

- A verified demo: invoice `inv_4fe69ac0f479` settled 3 test USDT and recorded a simulated ₹160.00 payout (see README.md for the explorer and ENS links).
- A verified settlement contract on the Whitechain testnet explorer.
- Docs: `docs/SUBMISSION.md`, `docs/evidence/`.
- None yet: real customers, testimonials, live volume, pricing. Never fabricate them.

## Product Principles

1. Show proof: every money claim links to onchain or receipt evidence.
2. Say plainly what is simulated.
3. Treat currency as neutral: no corridor is the default hero.
4. Payer paths keep working when merchant services are down.
5. Never pay out twice. When a result is uncertain, hold the payout.
