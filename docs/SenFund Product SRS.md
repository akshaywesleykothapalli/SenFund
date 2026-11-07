# SenFund Product SRS

6 November 2026 · Proposed product baseline for the website and mobile app

## 1. Product scope

SenFund lets an Indian freelancer issue a USD invoice to an overseas client, receive a wallet payment, and give both parties independently verifiable settlement evidence. The product must track any fiat payout separately from blockchain settlement.

The current milestone uses official test USDT on Whitechain Sepolia, chain 1874. Ethereum Sepolia hosts ENSv2 identity records. Chainlink CRE and the provider fixtures demonstrate simulated USD conversion and INR payout. Live funds and bank payouts require the separate release gates in the existing SenFund Requirements. This SRS adds accounts, roles and mobile requirements to that specification.

## 2. Account and access model

Use one identity system and one API for the website and mobile app. Every registered person has an individual account and credentials. An account can hold a freelancer role, a client role or both. The server grants and checks access for each invoice and action. Switching workspace changes navigation and context. It grants no new permissions.

| Capability | Freelancer | Registered client | Guest payer |
| --- | --- | --- | --- |
| Register, sign in and manage own profile | Required | Required for portal access | No account required |
| Enrol receiving wallet and ENS identity | Own freelancer profile | Unavailable | Unavailable |
| Create, sign, share or cancel an invoice | Own invoices | Unavailable | Unavailable |
| View private invoice details and history | Own invoices | Invoices explicitly assigned to that account | Unavailable |
| View signed payment terms and pay with a wallet | Via checkout link | Via assigned invoice or checkout link | Via checkout link |
| View chain proof | Own invoice and public chain evidence | Assigned invoice and public chain evidence | Checkout evidence and public chain evidence |
| Download a private receipt | Own eligible invoices | Assigned invoices | Public chain evidence only |
| Run payout simulation | Own eligible invoices | Unavailable | Unavailable |

An invite links an account to an invoice. A wallet connection proves control of an address when backed by a valid signature. A confirmed chain receipt identifies the paying wallet. These are distinct facts. An address match alone never claims an invoice or grants access to its private data. A guest can pay a shared invoice without a platform password.

For the first release, use an established identity provider with verified email and provider managed account recovery. Use the provider’s supported sign in options. Require recent authentication for sensitive changes and stronger authentication for receiving wallet, ENS and recovery changes. Wallet linking is a separate step. Do not collect recovery phrases or user wallet private keys.

## 3. Current implementation and gaps

| Area | Verified or implemented | Required next |
| --- | --- | --- |
| Website and API | Responsive Next.js workspace and local API, backed by the Python settlement service. Invoice creation supports durable request retries. | Registration, sessions, workspace roles, object ownership, and authenticated HTTPS access for mobile. |
| Profiles and wallet trust | The demo uses a configured merchant signer, enrolled ENS name and independently hosted checkout trust file. | User profiles, wallet ownership proof, per freelancer signing and trusted enrolment for more than one merchant. |
| Settlement | A public Whitechain Sepolia transaction settled 3 official test USDT to the ENS resolved merchant. The dashboard verified it. | Revalidate the flow through two isolated freelancer accounts and mobile browsers. Verify cancellation, stale recipient behavior and outage recovery. |
| INR workflow | The recorded CRE run selected Mudrex and produced a simulated ₹160 payout after ENS finality. | Preserve simulation labels and verify the fallback and hold acceptance cases in the account based product. |
| Native app | The website supports mobile widths. | Native packaging, platform wallet handoff and authenticated API access are planned. |

Evidence for the baseline is recorded in the [repository README](https://github.com/akshaywesleykothapalli/SenFund/blob/main/README.md#verified-demo) and the [Whitechain settlement transaction](https://explorer.testnet.whitechain.io/tx/0xca8d066095a407552697f77dc866ae939390712a87e38eabb12dc52efc342c62).

## 4. Functional requirements

**P0** is the account based testnet release. **P1** adds the client portal and native app. Live finance is a separate gated milestone.

| ID | Priority | Requirement | Acceptance |
| --- | --- | --- | --- |
| ID-01 | P0 | Register a freelancer, verify email, sign in, sign out, recover access and revoke sessions. Use a durable internal account ID and verified identity provider subject. Email is contact data. | Unverified sessions cannot issue invoices. Recovery revokes prior sessions. Private routes deny access after sign out. |
| ID-02 | P0 | Store the freelancer’s display or business name, verified email, enrolment status and associated payment identities. Use only user supplied or verified data. | A freelancer can edit their own profile and cannot edit another profile. Missing values remain unset. |
| AUTH-01 | P0 | Authorize every private read, list, write, export and action against the actor and invoice or profile. Persist the owner ID server side and derive it from the session when creating an invoice. | Two freelancers cannot list, inspect, modify, export or trigger actions on each other’s invoices even with known IDs. Changing the role, owner or invoice ID in the request grants no access. |
| WAL-01 | P0 | Verify wallet control with a single use, expiring signature challenge bound to the authenticated account, expected origin, chain, address and purpose. Keep the signing wallet and payout recipient distinct in the model even when their addresses match. | A reused, expired, wrong address or wrong origin challenge fails. A guest payer connects a wallet only to authorize payment. |
| WAL-02 | P0 | Enrol a controlled ENSv2 name and dedicated resolver, confirm its explicit Whitechain address, and link it to the freelancer’s verified receiving wallet. Record who approved the mapping. | A missing record, unexpected resolver or substituted recipient blocks issuance and checkout. Changing a receiving wallet requires fresh proof, reauthentication and an audit event. |
| INV-01 | P0 | Create a draft with client details, service description, exact USD amount and payment expiry. Resolve the recipient and have the enrolled merchant wallet sign the EIP-712 request. Store a signed invoice only after server verification. Preserve durable idempotency per owner and environment. | Retrying after a lost response returns the same invoice and checkout link. An altered draft or signature fails. A reused request key with different details returns HTTP 409. |
| INV-02 | P0 | Share a portable signed link that contains the payment fields only. Keep client details, service description and bank details out of the link and public logs. Support onchain cancellation by the signing merchant and expiry. | A stale ENS record blocks approval. The signed recipient is never silently replaced. The invoice is marked cancelled after verified onchain cancellation. |
| PAY-01 | P0 | Show the testnet, token, amount, recipient and expiry before requesting wallet approval. Check the signer, token, spender, signed amount and current recipient against trust configured outside the link. Keep checkout independent of the merchant backend. | Tampered, expired, cancelled and already settled invoices do not request payment. Checkout can settle and show chain proof while the merchant backend is offline. |
| PAY-02 | P0 | Verify exact token transfer, invoice digest, payer, recipient, emitting contract, canonical block and confirmation threshold. Record settlement once and reconcile after restart. Flag a confirmed reorg for review. | A submitted hash remains pending until verified. Duplicate submissions produce one receipt. A reorg pauses downstream actions and preserves audit history. |
| PAY-03 | P0 | Keep chain settlement, simulated USD conversion and simulated INR payout as separate state machines. Route through the CRE gate when enabled. Allow simulated P2P only on confirmed predispatch unavailability. | A completed testnet transfer never appears as bank credit. An ambiguous provider outcome yields a hold, retains the attempt key and produces no duplicate or fallback payout. |
| REC-01 | P0 | Show settlement status, explorer link and a downloadable receipt for the owner. Give guest checkout public chain proof only. Keep private receipt and audit access behind authorization. | Export omits bank data and credentials, marks simulated figures as simulated, and distinguishes chain confirmation from payout status. |
| CLI-01 | P1 | Register clients using the same identity service. Assign invoice access through a revocable invite bound to the intended verified email or account. Provide a client inbox, checkout and client receipt. | A different signed in account cannot claim the invite. Forwarding a guest payment link never reveals private fields or grants portal membership. |
| MOB-01 | P1 | Ship a native client using the same invoice and status API over HTTPS. Use system browser sign in with Authorization Code and PKCE, secure device token storage, and platform verified app links. Use a supported wallet handoff for transactions. | Returning from a wallet reopens the correct invoice and fetches server verified status. Cancellation or app termination during handoff is recoverable. Invalid callback state never establishes a session. |
| LIVE-01 | Gated | Enable live settlement or bank payout only after the existing production requirements are independently met. Define the permitted network, custody, sender and provider onboarding, real quotes and fees, settlement evidence, bank documentation and operational controls. | Testnet data cannot enter live adapters. Real INR credit requires authenticated provider or bank evidence tied to the invoice. |

## 5. Backend architecture and data

| Record | Minimum fields or relationships |
| --- | --- |
| Account and role | Internal account ID, identity provider subject, verification state, role assignments and session revocation metadata. |
| Freelancer profile | Owner ID, display name, onboarding state and active payment identity. |
| Wallet and enrolment | Account ID, chain, address, purpose, proof time, status, ENS name, resolver, receiving address and enrolment version. Keep historical mappings. |
| Invoice and access grant | Owner ID, optional assigned client ID, invoice state, signed request and digest, token and chain, exact amount, expiry, and private invoice details. Access grants record who assigned access and when it was accepted or revoked. |
| Payment and payout | Chain receipt identity, confirmations, canonical block, operation and provider keys, evidence source, environment and state transitions. |
| Audit event | Actor or service ID, action, target, result, timestamp and request ID. Exclude secrets and unnecessary personal data. |

Next.js serves the web workspace and its API layer. Keep Python as the authority for invoice persistence, receipt verification, reconciliation and the CRE runner. The Python service stays private. Authenticated caller identity must be verified at the trusted boundary and enforced where private data is queried or changed. Do not accept an actor ID from an untrusted request header. Keep the public payer surface separate from the merchant API.

**Multiple freelancers are an explicit architecture change.** The current checkout trust file pins a single signer and ENS identity. For the first multi freelancer test, use a curated, independently hosted enrolment list from a trusted origin, with a signer, name, resolver and active status for each approved freelancer. Checkout looks up the merchant in that list and independently verifies the chain record. The link must never define its own trust entry. Publish updates through the approved enrolment process. The current contract recovers ECDSA signatures, so the first merchant signing flow supports compatible externally owned wallets. Smart account signing requires contract support and separate testing.

For migration, add owner and access fields before exposing any private API. Explicitly assign existing demo invoices to the verified operator account. Keep unassigned records inaccessible. Preserve receipt identity, signed requests, existing idempotency records and audit history. Never infer ownership from an email or from a payment address.

## 6. Nonfunctional requirements

| ID | Category | Requirement and acceptance |
| --- | --- | --- |
| NFR-01 | Security | Use HTTPS outside loopback. Protect web sessions with secure, HTTP only cookies and appropriate CSRF defenses. Verify native token issuer, audience and expiry. Rate limit sign in, wallet challenges, invoice creation and public checkout lookups. Security tests cover horizontal and vertical privilege escalation. |
| NFR-02 | Privacy | Minimize collected profile data and separate public payment fields from private invoice records. Keep personal data offchain and restrict logs and exports. Define retention and deletion policies before public onboarding. Deleting local data cannot remove public blockchain events. |
| NFR-03 | Integrity | Use integer token units and exact decimal currency arithmetic. Make owner scoping, idempotency, receipt deduplication and payout state updates transactional. Race and restart tests must demonstrate no duplicate invoice or payout for the same logical request. |
| NFR-04 | Reliability | Preserve the independent checkout during merchant service outages. A failed RPC lookup never confirms payment or invalidates a known receipt on its own. Reconcile after restart and exercise database backup and restore before public onboarding. |
| NFR-05 | Performance | Paginate invoice and audit lists. Measure API latency and reconciliation lag with representative loads before setting numeric service targets. Report chain confirmation and finality delays separately from application latency. |
| NFR-06 | Accessibility | Target WCAG 2.2 AA for the web workspace and checkout. Verify keyboard navigation, accessible input errors, readable status labels without color, and small screen layout. Test the wallet approval and return flow on supported iOS and Android browsers before native rollout. |
| NFR-07 | Observability | Trace invoice creation, verification, reconciliation and payout decisions with opaque correlation IDs. Surface provider and chain failures without leaking credentials or exposing private receipt data. Alert on stuck reconciliation and unresolved payout attempts. |
| NFR-08 | Delivery | CI must build the web application and run backend, contract, checkout and authorization tests. Version the API before native clients depend on it. Keep testnet, simulator and production credentials and data separated. |

## 7. Build order and acceptance gates

1. **Accounts and ownership.** Implement registration, verified sessions, freelancer profiles and invoice ownership migration. Prove the access boundary with two freelancer accounts before exposing a shared HTTPS endpoint.
2. **Wallet and invoice issuance.** Implement wallet ownership proof, merchant signing, ENS enrolment and curated checkout trust. Have both freelancers issue invoices and verify each link resolves to the correct merchant. Exercise retry, cancellation and stale recipient cases.
3. **Client payment and receipt.** Keep guest payment available, test mobile browser checkout, reconcile a payment after an outage and verify one private receipt per confirmed settlement. Preserve the current CRE demo and exercise its hold and safe fallback paths.
4. **Client portal and native app.** Add optional client registration, invoice invitations and client receipts. Stabilize the authenticated API and complete native sign in and wallet return tests.
5. **Live payout pilot.** Require explicit approval and complete the existing provider, network and bank evidence gates. Treat pricing, actual fees and exchange rates as separate verified inputs. Account roles do not determine fee rules.

## 8. Standards and related requirements

The existing [SenFund Requirements](SenFund%20Requirements.md) covers sponsor integrations and the provider and bank release gates.

1. [OWASP object level authorization](https://api-security.owasp.org/editions/2023/en/0xa1-broken-object-level-authorization/) and [session management](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet).
2. [ERC-4361 wallet signing and challenge validation](https://eips.ethereum.org/EIPS/eip-4361) and [EIP-712 typed signatures](https://eips.ethereum.org/EIPS/eip-712).
3. [OAuth for native applications](https://www.rfc-editor.org/rfc/rfc8252.html) and [OAuth security best current practice](https://www.rfc-editor.org/rfc/rfc9700.html).
4. [WCAG 2.2](https://www.w3.org/TR/WCAG22/).

## Wallet and corridors

- Each user links a Whitechain Sepolia (chain 1874) wallet by signing a personal_sign proof. The user signs in their own wallet.
- The Wallet view shows testnet balances from `GET /api/balance/<address>` (400 for a bad address, 502 if the RPC fails).
- "Withdraw to bank" gives a quote only (amount × rate − fee). It is labelled "Simulated — no money moves".
- Clients pay in test USDT. Corridors come from `/api/config`: IN, EU, MX, KE, AE and more. Conversion and payout stay simulated.
