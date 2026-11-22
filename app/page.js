import Disclosure from "./disclosure";
import Logo from "./logo";
import { connection } from "next/server";
import { accountMode, localAuthMode } from "./account-server";
import { Motion, Pipeline, Reveal, Rise, Sketch } from "./motion";

const TX = "0xca8d066095a407552697f77dc866ae939390712a87e38eabb12dc52efc342c62";
const CONTRACT = "0x613677fc94907367944DE1f0E4B88C44488B9B58";
const EXPLORER = "https://explorer.testnet.whitechain.io";

const stages = [
  ["Invoice", "Set an amount and share a signed payment link.", "invoice"],
  ["Pay", "The client opens the link and pays from their wallet.", "wallet"],
  ["Verify", "SenFund verifies the onchain payment and issues a receipt.", "receipt"],
  ["Convert", "For USDT invoices, preview the conversion to local currency.", "convert"],
  ["Pay out", "CRE selects a route or holds an unresolved attempt.", "payout"],
];

const icons = {
  invoice: "M7 3h7l4 4v14H7zM14 3v4h4M10 12h6M10 16h6",
  wallet: "M4 7h15v12H4zM4 7l2-3h11l2 3M15 13h2",
  receipt: "M6 3h12v18l-3-2-3 2-3-2-3 2zM9 11l2 2 4-4",
  convert: "M7 8l-4 4 4 4M17 8l4 4-4 4M4 12h16",
  payout: "M12 3v12m0 0l-4-4m4 4l4-4M5 21h14",
};

export default async function Page() {
  await connection();
  const accounts = accountMode();
  const signIn = localAuthMode() ? "/login" : accounts ? "/api/auth/sign-in" : "/workspace";
  const signUp = localAuthMode() ? "/login?mode=signup" : signIn;
  return (
    <Motion>
    <div className="site">
      <header className="siteHeader">
        <div className="wrap headerRow">
          <Logo />
          <nav className="headerNav" aria-label="Main">
            <a href="#how">How it works</a>
            <a href="#payment-proof">Payment proof</a>
            <a href="#questions">FAQs</a>
          </nav>
          <div className="headerActions"><span className="headerNetwork"><i aria-hidden="true" />Testnet demo</span>
            <a className="button plain" href={signIn}>Log in</a>
            <a className="button primary" href={signUp}>{accounts ? "Create account" : "Open workspace"}</a>
          </div>
          <details className="menu">
            <summary aria-label="Menu">Menu</summary>
            <nav aria-label="Mobile">
              <a href="#how">How it works</a>
            <a href="#payment-proof">Payment proof</a>
            <a href="#questions">FAQs</a>
              <a href={signIn}>Log in</a>
              <a href={signUp}>{accounts ? "Create account" : "Open workspace"}</a>
            </nav>
          </details>
        </div>
      </header>

      <main className="siteMain">
        <section className="hero wrap">
          <div className="heroCopy">
            <Rise i={0}><p className="heroBadge">Whitechain Sepolia · Testnet demo</p></Rise>
            <Rise i={1}><h1>Invoice in USD.<br />Settle in USDT.<br /><em>Your currency. Every step clear.</em></h1></Rise>
            <Rise i={2}><p className="lede">Send a signed invoice, track the onchain payment, and preview a simulated payout in INR, EUR and more.</p></Rise>
            <Rise i={3} className="heroActions">
              <a className="button primary big" href={signIn}>Start invoicing</a>
              <a className="button big" href="#how">See how it works</a>
            </Rise>
            <Rise i={4} className="heroStats">
              <div><strong>Your wallet</strong><span>Direct testnet settlement</span></div>
              <div><strong>ENS verified</strong><span>Recipient checked before approval</span></div>
              <div><strong>Portable proof</strong><span>Receipts and evidence exports</span></div>
            </Rise>
          </div>
          <Rise i={2} className="flow"><Sketch /><p className="sketchCaption">Illustrative flow · payout amounts are simulated</p></Rise>
        </section>

        <section id="how" className="band">
          <div className="wrap">
            <p className="eyebrow center">How it works</p>
            <h2>Five steps</h2>
            <Pipeline steps={stages.map(([title, text, icon]) => ({ title, text, d: icons[icon] }))} />
            <p className="pipelineNote">Payments settle on testnet. Conversion and bank payouts are simulated.</p>
          </div>
        </section>

        <Reveal id="payment-proof" className="wrap proofSection">
          <div className="proofIntro"><p className="eyebrow">Follow the money</p><h2>A payment you can<br />check for yourself.</h2><p>One recorded invoice. One public transaction. See where the test USDT went, then follow the same trail from your own workspace.</p>
            <a className="button primary big" href={`${EXPLORER}/tx/${TX}`} target="_blank" rel="noreferrer">Inspect payment on explorer ↗</a>
          </div>
          <div className="receiptShadow">
            <article className="proofReceipt" aria-label="Recorded testnet payment receipt">
              <header className="receiptHeading"><Logo className="wordmark receiptWordmark" /><p>PAYMENT RECEIPT</p><span className="receiptStatus">SETTLED ONCHAIN · TESTNET</span></header>
              <div className="receiptTotal"><span>AMOUNT RECEIVED</span><p className="proofAmount">3.00 <span>test USDT</span></p></div>
              <p className="proofInvoice">INVOICE # inv_4fe69ac0f479</p>
              <dl className="proofFacts"><div><dt>Network</dt><dd>Whitechain Sepolia</dd></div><div><dt>Chain ID</dt><dd>1874</dd></div><div><dt>Block</dt><dd>12,352,312</dd></div><div><dt>Recipient name</dt><dd>merchant.senfund.eth</dd></div></dl>
              <section className="receiptReferences" aria-label="Public verification references">
                <div><h3>PAYMENT TRANSACTION</h3><a href={`${EXPLORER}/tx/${TX}`} target="_blank" rel="noreferrer" aria-label="Inspect payment transaction on Whitechain explorer"><code>{TX}</code><span className="receiptLinkHint">Inspect transaction ↗</span></a></div>
                <div><h3>VERIFIED SETTLEMENT CONTRACT</h3><a href={`${EXPLORER}/address/${CONTRACT}?tab=contract`} target="_blank" rel="noreferrer" aria-label="Inspect verified settlement contract on Whitechain explorer"><code>{CONTRACT}</code><span className="receiptLinkHint">Inspect contract ↗</span></a></div>
              </section>
              <footer className="receiptEnd"><p>PUBLIC RECORD · KEEP FOR REFERENCE</p><p className="proofFootnote">Recorded testnet example. Test tokens have no monetary value. This receipt is not a live balance.</p><span aria-hidden="true">* * * * *</span></footer>
            </article>
          </div>
        </Reveal>
        <section className="wrap proofFeatures" aria-label="What the receipt shows">
          <Reveal className="proofFeature"><span className="featureNumber">01</span><h3>Know who receives it</h3><p>Checkout checks the signed recipient against the configured ENS record before requesting wallet approval.</p></Reveal>
          <Reveal className="proofFeature"><span className="featureNumber">02</span><h3>Keep the settlement proof</h3><p>The payer and merchant can check the transaction, amount and destination on the same public explorer.</p></Reveal>
          <Reveal className="proofFeature"><span className="featureNumber">03</span><h3>Track each stage separately</h3><p>Your workspace separates onchain settlement from simulated conversion and payout. Download receipts and evidence after verification.</p></Reveal>
        </section>
        <section className="wrap editorialSection" aria-label="Built for independent work">
          <Reveal className="editorialCard"><div className="editorialImage"><img src="/images/senfund-invoice.webp" alt="An illustrated freelancer desk with a laptop and paper invoices beside an arched window." width="1200" height="800" loading="lazy" /></div><div><p className="eyebrow">Made for your working day</p><h2>More time for the work.<br />Less time chasing proof.</h2><p>Issue the invoice, share a signed link, and follow settlement in your workspace. Keep the receipt when the payment is verified.</p><a href={signUp}>Start with an invoice ↗</a></div></Reveal>
          <Reveal className="editorialCard"><div className="editorialImage"><img src="/images/senfund-connections.webp" alt="A stone bridge between two cities with a paper ribbon and gold connection arcs." width="1200" height="800" loading="lazy" /></div><div><p className="eyebrow">A shared record</p><h2>Different places.<br />The same payment trail.</h2><p>Clients and freelancers can inspect the same onchain transaction. The demo keeps simulated conversion and bank payout separate from settlement.</p><a href="#payment-proof">Follow the recorded payment ↗</a></div></Reveal>
        </section>
        <Reveal id="questions" className="wrap questionsSection">
          <div><p className="eyebrow">Before you start</p><h2>A little clarity.</h2><p className="bandSub">What happens onchain, and what the demo simulates.</p></div>
          <div className="faqList">
            <Disclosure title="Does SenFund hold the invoice payment?"><p>The settlement contract transfers the test token directly from the payer to the recipient signed into the invoice.</p></Disclosure>
            <Disclosure title="Are bank payouts real?"><p>Conversion rates, fees, provider orders and bank credits are demo fixtures. All payout amounts are simulated. Live payouts are disabled.</p></Disclosure>
            <Disclosure title="Does the client need an account?"><p>The client opens the signed payment link and uses a compatible browser wallet. Checkout requires test tokens and gas on Whitechain Sepolia.</p></Disclosure>
            <Disclosure title="What if the merchant server goes offline?"><p>An already issued link can settle through the independently hosted checkout using wallet and ENS RPCs. The merchant service reconciles confirmed payments when it returns.</p></Disclosure>
          </div>
        </Reveal>
        <Reveal id="access" className="wrap accessPanel">
          <div><p className="eyebrow">From invoice to proof</p><h2>Your next invoice,<br />with a clearer trail.</h2><p>Create a signed link, follow the payment, and keep the receipt.</p></div>
          <div className="accessActions"><a className="button primary big" href={signUp}>{accounts ? "Create your account" : "Open demo workspace"} ↗</a><a href="#payment-proof">Explore the recorded payment</a><small>Testnet settlement · simulated bank payouts</small></div>
        </Reveal>
      </main>

      <footer className="siteFooter landingFooter">
        <div className="wrap footerGrid">
          <div className="footerBrand"><Logo /><p>Across borders.<br />Every step checkable.</p><span className="footerNetwork">Whitechain Sepolia · Testnet</span></div>
          <nav aria-label="Product links"><h3>Explore</h3><a href="#how">How it works</a><a href="#payment-proof">Payment proof</a><a href="#questions">Common questions</a><a href="/workspace">Merchant workspace</a></nav>
          <nav aria-label="Verification links"><h3>Verify</h3><a href={`${EXPLORER}/tx/${TX}`} target="_blank" rel="noreferrer">Recorded payment ↗</a><a href={`${EXPLORER}/address/${CONTRACT}?tab=contract`} target="_blank" rel="noreferrer">Settlement contract ↗</a><a href="https://github.com/akshaywesleykothapalli/SenFund" target="_blank" rel="noreferrer">Source code ↗</a></nav>
          <div className="footerAccount"><h3>Your workspace</h3><p>Invoices, wallet records and downloadable payment evidence in one place.</p><a className="button" href={signIn}>{accounts ? "Log in" : "Open workspace"} ↗</a></div>
        </div>
        <div className="wrap footerLegal"><span>© {new Date().getFullYear()} SenFund</span><p>Test assets only. Conversion and bank payouts are simulated.</p><a href="#">Back to top ↑</a></div>
        <div className="footerArtwork"><img src="/images/senfund-footer.webp" alt="" width="1536" height="512" loading="lazy" /></div>
      </footer>
    </div>
    </Motion>
  );
}
