# SenFund SRS implementation status

This is the implementation tracker for the [Product SRS](SenFund%20Product%20SRS.md). The account work is a private single operator pilot. The original local testnet demo remains a separate launch mode.

| Requirements | Current coverage | Remaining acceptance work |
| --- | --- | --- |
| ID-01 | OpenID Connect sign in, verified email, stable issuer and subject identity, revocable sessions and sign out on all devices. | Configure a real provider and verify registration and provider recovery. Integrate recovery events with local session revocation. |
| ID-02 | Editable display name, verified email and verified wallet list. | Connect profile to an approved ENS enrolment and add client profiles when the portal is built. |
| AUTH-01 | Server enforces owner access on invoice reads, lists, exports and mutations. Unassigned legacy invoices are hidden. The two account test verifies denial across accounts and separates shared email from identity. | Prove issuance and settlement for two independently enrolled freelancers. |
| WAL-01 | Wallet proof binds a single use message to account, session, address, purpose, origin and chain. Recent provider authentication is required. | Run browser wallet approval on actual supported devices and add issuance rate limits. |
| WAL-02 | The original testnet checkout verifies a configured ENS recipient. Wallet proofs can be recorded separately. | Per freelancer enrolment, curated checkout trust, receiving wallet change controls and auditable approval. A recorded wallet proof does not change the settlement destination. |
| INV-01 and INV-02 | Signed links and durable creation retries. Account mode scopes issuance and retries to the owner. The contract enforces expiry and supports merchant cancellation. | Per freelancer wallet signatures and draft validation, cancellation receipt tracking, and a testnet wallet rotation run. The pilot can only issue through the original configured signer. |
| PAY-01 and PAY-02 | Independent checkout, signed payment preflight, restart reconciliation, reorg checks and explicit token transfer verification in the normal receipt path. | Repeat the public outage and mobile browser acceptance runs with the account based workflow. |
| PAY-03 and REC-01 | The original demo keeps settlement, conversion and payout separate. Account mode protects private exports and keeps simulated stages labelled. | CRE evidence routes now require the invoice owner in account mode, and the two account test covers denial. Startup still refuses CRE with account mode until the CRE runner itself authenticates to those routes. Capture safe fallback and hold evidence across the account based flow. |
| CLI-01 and MOB-01 | Shared web API and responsive layout. | Verified client invitations and portal, native app, mobile identity and wallet handoff, and HTTPS deployment. |
| LIVE-01 | Testnet and simulation guards remain in place. | Production funding and bank evidence, provider approval, and separate live pilot. |
| NFR-01 and NFR-02 | Owner checks, bridge secret, scoped HttpOnly cookies, write origin checks, signed identity tokens and public link field separation. | Deployment review, enforced provider MFA and rate limits, native token validation, retention and deletion. |
| NFR-03 and NFR-04 | Transactional ownership, idempotency, single use wallet challenges, receipt deduplication and independent checkout. | Backup and restore exercise, broader concurrency tests and public outage proof. |
| NFR-05 through NFR-08 | Responsive views and test coverage in the existing CI workflow. | Pagination, load tests, accessibility audit, operational alerts and API versioning. |

## Run the account pilot

1. Create a confidential OpenID Connect web application at your chosen identity provider. Enable verified email and register the exact callback, such as `http://127.0.0.1:3000/api/auth/callback` for loopback development. The issuer must use HTTPS and publish signing keys.
2. Copy the account mode settings in `.env.example` into the local `.env`. Generate a separate random API bridge secret. Configure both the Python service and Next.js from that file. Keep CRE disabled for this mode. Its evidence routes are owner gated, but the CRE runner has no authenticated path to them yet.
3. Start the backend, independent checkout and Next.js as described in the [README](../README.md). Sign in through the provider. The profile endpoint returns the verified account ID.
4. Set the explicitly approved identity provider subject as `SENFUND_OPERATOR_SUBJECT` to allow that operator to issue through the configured demo signer. Other accounts may update their profile and prove wallet ownership. They have no invoice signing capability.
5. Assign an existing invoice only after verifying who owns it. Run `.venv/bin/python scripts/assign_invoice_owner.py <invoice-id> <account-id>`. Unassigned invoices are hidden in account mode and an existing assignment cannot be overwritten by the command.
6. Keep this pilot bound to loopback until the remaining public deployment requirements are met. Use an isolated database for separate demo or account experiments.

The provider integration follows [OpenID Connect Core](https://www.openid.net/specs/openid-connect-core-1_0.html) and the [OAuth security best current practice](https://www.rfc-editor.org/rfc/rfc9700.html). Local tests exercise the trusted identity handoff and wallet proofs. Live provider and wallet prompts are separate acceptance steps.
