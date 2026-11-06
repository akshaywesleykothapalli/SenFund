# SenFund submission

Payouts in this build are simulated. No real money moves. Fill every `TODO` before submitting.

## Links

| Item | Link |
|------|------|
| Source | TODO repo URL |
| Live web app | TODO deploy URL |
| Walkthrough video | TODO video URL |
| Settlement contract (verified) | TODO Whitechain explorer URL |
| Sample settle transaction | TODO explorer tx URL |
| ENSv2 name and record change | TODO ENS app / explorer URL |
| CRE evidence | `docs/evidence/cre-<invoice>-<scenario>.json` (from `scripts/cre_capture.py`) |

## Walkthrough script (about 4 minutes)

| # | Shot | Say |
|---|------|-----|
| 1 | Workspace, empty state, corridor picker | "A freelancer in India gets paid in USDT on Whitechain and receives INR." |
| 2 | Create an invoice, copy checkout link | "The invoice is signed by the merchant. The payer cannot change the amount or recipient." |
| 3 | Checkout page, wallet connect, approve and settle | "The payer settles on-chain in one flow." |
| 4 | Explorer: settle tx and SETTLED event | "The backend verifies this event, not the browser." |
| 5 | Invoice shows PAID, then route decision | "CRE reads the receipt and the ENSv2 record, then picks Mudrex, P2P or hold." |
| 6 | Run `scripts/cre_capture.py`, show JSON | "This is the CRE decision for this receipt." |
| 7 | Stop backend, run `scripts/recovery_demo.py` | "A payment made while we are down is found on restart." |
| 8 | Receipt and evidence pack export | "The owner exports a receipt with every hash." |
| 9 | Closing slide with links | "Simulated payouts today. Live adapters stay disabled until licensed." |

Record shots 3 and 4 on testnet, not the local chain.

## Whitechain feedback

- What worked: TODO (e.g. RPC reliability, block times, explorer search)
- Friction: TODO (e.g. faucet limits, contract verification steps, missing docs)
- Requests: TODO
