# SenFund

### Cross-border invoices with a payment trail you can verify

SenFund helps freelancers send signed invoices, accept wallet payments, and keep a clear record of settlement. Clients pay through a shareable checkout link. Merchants follow the payment in their workspace and download receipts and evidence for their records.

The current build runs on **Whitechain Sepolia**. Onchain payments use test tokens. Currency conversion and bank payouts are simulated.

![SenFund illustration of invoices connecting independent work across borders](public/images/senfund-footer.webp)

## How it works

1. **Create an invoice.** Enter the client, service description, amount and payment asset. USDT invoices also support a local payout corridor.
2. **Share the signed link.** The payment request protects the amount, asset and receiving address.
3. **Pay from a wallet.** Checkout validates the request and checks the recipient against the configured ENS record before approval.
4. **Verify settlement.** The workspace reconciles the confirmed payment and shows its public transaction reference.
5. **Keep the receipt.** Download the payment receipt or evidence pack. For USDT invoices, explore a separate simulated conversion and bank payout.

## What you can do

### Merchant workspace

- See receiving-wallet balances and verified incoming payments.
- Search invoices by client, description, invoice ID or transaction.
- Filter awaiting payments, settled invoices, items needing attention and completed payout simulations.
- Follow settlement, conversion and payout as separate stages.
- Inspect fees, route decisions and timestamped activity.
- Export receipts, evidence packs and a payment statement.

### Independent checkout

Clients can open an invoice link without creating an account. Checkout uses the signed payment details and public chain reads, so an already issued link can still settle while the merchant service is offline, provided checkout hosting and its RPC services remain available. The merchant service reconciles confirmed payments when it returns.

### Wallets and payment assets

Test USDT invoices support the simulated conversion and payout flow. Test WBT invoices settle to the signed recipient as wrapped WBT. Checkout can wrap the payer's WBT shortfall before approval.

Account mode supports wallet ownership proofs through a signed message. The current account experience is a local pilot with operator-controlled invoice issuance.

### Local currency previews

USDT invoices can preview payouts in INR, EUR, GBP, PHP, NGN, BRL, MXN, KES and AED. Quotes use fixture exchange rates and fees. They are simulated estimates.

The payout demo supports a primary route, a protected P2P fallback when the primary is unavailable before dispatch, and a hold when the outcome of a previous attempt is uncertain. An uncertain primary attempt is reconciled before another payout can proceed.

## Recorded payment proof

Invoice **inv_4fe69ac0f479** settled **3 test USDT** to the Whitechain address resolved from **merchant.senfund.eth**. The public receipt is recorded at block **12,352,312** on chain **1874**.

| Record | Verification |
| --- | --- |
| Payment | [Inspect the recorded test-USDT transaction](https://explorer.testnet.whitechain.io/tx/0xca8d066095a407552697f77dc866ae939390712a87e38eabb12dc52efc342c62) |
| Settlement contract | [Inspect the source-verified contract](https://explorer.testnet.whitechain.io/address/0x613677fc94907367944DE1f0E4B88C44488B9B58?tab=contract) |
| Merchant name | [Inspect the ENS name on Sepolia](https://sepolia.explorer.ens.domains/merchant.senfund.eth) |

Onchain stablecoin settlement gives the payer and merchant a shared public record of the signed amount and destination, which can be checked independently of SenFund's database.

## Integrations

**Whitechain** provides the testnet settlement rail and public payment record.

**ENS** resolves the configured recipient and lets checkout detect a receiving-address mismatch before approval. Record changes block stale links in checkout. Existing contract signatures expire or require onchain cancellation to revoke them.

**Chainlink CRE** can gate simulated payout routing using settlement, ENS and provider evidence. The optional **Chainlink Local CCIP** demo records a payout decision in a local EVM. That CCIP demonstration runs locally.

## CROPS

**Censorship resistance.** Independent checkout lets an existing invoice settle while the merchant service is offline. Checkout hosting, wallet RPC and ENS RPC remain dependencies.

**Open source.** SenFund is available under the MIT license. The repository includes the application, contracts and supporting documentation.

**Privacy.** Checkout requests exclude private invoice descriptions, client names, email addresses and bank details. The merchant service stores account and invoice information locally. Wallet and ENS RPC providers can observe requests made to them. Public settlement exposes wallet addresses and token amounts.

**Security.** Signed payment requests protect invoice terms, checkout validates the configured recipient, and the contract enforces single settlement. Account mode applies invoice ownership checks. The current demo uses a configured merchant signer, and public deployment requires further review.

## Current scope

- Whitechain settlement uses test tokens with no monetary value.
- Currency conversion, provider orders and bank credits are simulated.
- Live payouts, a real P2P escrow and a partner marketplace are outside the current build.
- Account mode is a local pilot. Multi-freelancer enrolment and production identity flows require additional work.
- Public ENS rotation and delegation proofs, a recorded testnet outage run, a hosted demo and a final walkthrough video remain submission tasks.

## Project documentation

- [Product overview](PRODUCT.md)
- [Requirements and release criteria](docs/SenFund%20Requirements.md)
- [Account pilot status](docs/SRS_IMPLEMENTATION.md)
- [ENS setup](docs/ENS_SETUP.md)
- [Chainlink workflow demo](cre/README.md)
- [Local CRE and CCIP demonstration](docs/CHAINLINK_LOCAL_DEMO.md)
- [Submission checklist](docs/SUBMISSION.md)
- [Whitechain feedback](WHITECHAIN_FEEDBACK.md)

## License

[MIT](LICENSE) · SenFund team
