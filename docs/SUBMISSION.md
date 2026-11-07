# SenFund demo script (2–3 minutes)

Testnet only. Whitechain Sepolia (chain 1874). All conversion and payout amounts are simulated.

| Time | Screen | Say |
|---|---|---|
| 0:00 | Workspace | "SenFund lets a freelancer bill in USD and get paid in test USDT on Whitechain." |
| 0:15 | New invoice form | Create the invoice by hand: amount in test USDT, client, description, and a payout corridor (IN, EU, MX, KE, AE and more, all simulated). "Client pays in test USDT." |
| 0:40 | Checkout link | "The link holds a signed EIP-712 invoice. Nothing private is in it." Show ENS check passing. |
| 1:00 | Wallet | Pay the invoice. "The contract accepts each invoice once." |
| 1:20 | Explorer | Show the transaction and the verified contract. |
| 1:35 | Invoice PAID | Run conversion. "Simulated USD to INR or EUR quote." |
| 1:50 | Payout | Choose Mudrex unavailable. "Protected P2P fallback. Licensed provider not available in this demo (requires identity verification). No order was submitted. The simulated payout waits for simulated bank credit." Click Simulate bank credit. |
| 2:20 | Evidence pack | Download `senfund-evidence-<id>.json`. Show tx hash, block, route, fallback reason, simulated refs. No emails or bank details. |
| 2:40 | Close | "Checkout works with SenFund offline. MIT licensed. Live payouts stay disabled." |

## Wallet actions you must do

| Action | Proof to capture |
|---|---|
| Pay a new invoice in test USDT from the browser wallet | Explorer tx URL, invoice ID, evidence JSON |
| Rotate the ENS merchant record (pending) | ENS explorer record-change tx URL; checkout refusing old address |
| Replacement payment after rotation (pending) | Second explorer tx URL to the new address |
| Grant scoped delegation (pending) | Delegation tx or signature, scope shown in wallet |
| Outage recovery: stop app, pay, restart (pending) | Explorer tx while app is down; invoice PAID after restart |
| Record the video | Video URL |

## Links

| Item | URL |
|---|---|
| Settlement contract (verified) | https://explorer.testnet.whitechain.io/address/0x613677fc94907367944DE1f0E4B88C44488B9B58 |
| Official test-USDT payment | https://explorer.testnet.whitechain.io/tx/0xca8d066095a407552697f77dc866ae939390712a87e38eabb12dc52efc342c62 |
| ENSv2 name | https://sepolia.app.ens.domains/merchant.senfund.eth |
| Live URL | pending |
| Video | pending |
