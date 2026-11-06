# SenFund Chainlink CRE Demo

The payout workflow joins three sources. It reads the enrolled Whitechain recipient from ENSv2 on Ethereum Sepolia, checks SenFund's confirmed Whitechain receipt over HTTP, and queries the simulated provider's availability and order state over HTTP. SenFund applies the decision only if the receipt and provider attempt still match and the latest ENS recipient remains valid.

## Run through the dashboard

1. Install Bun and the [official CRE CLI](https://docs.chain.link/cre/getting-started/cli-installation/macos-linux). Run `cre login` for your own account and ensure `cre` and `bun` are on the backend's PATH.
2. In `cre/payout`, run `npm ci` and `npm run check`.
3. Configure the enrolled ENSv2 name, resolver and Ethereum Sepolia RPC in the project `.env`. Wait for the ENS record transaction to finalize. Use a confirmed Whitechain Sepolia invoice and run the simulated conversion. The workflow configuration assumes the merchant server is on port 8700. Adjust `payout/config.json` for a different local port.
4. Set `SENFUND_CRE_PAYOUTS=1` and restart the merchant server. Choose a scenario and click **Run Chainlink CRE payout simulation**. The dashboard shows the decision and source. For P2P, use **Simulate bank credit** after the demo order is waiting for credit.
5. Use separate invoices for Mudrex success, Mudrex unavailable before dispatch, and an unresolved attempt. To show the last case, first select **Mudrex times out**. Select the unavailable scenario on the same invoice and run the workflow again. It should show a hold and create no fallback order.

The backend invokes the CLI without broadcasting. The HTTP trigger payload contains the run nonce, public receipt fields, simulated scenario and enrolled ENS settings. The runner accepts only the result from its own child process. Neither the workflow nor its HTTP evidence endpoints send real payouts. For a manual simulation, use the [documented HTTP trigger command](https://docs.chain.link/cre/guides/workflow/using-triggers/http-trigger/testing-in-simulation) from this directory with the same inputs. Manual results do not apply payouts to the app.
