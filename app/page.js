import { connection } from "next/server";
import { accountMode } from "./account-server";
import { Float, Motion, Reveal, Rise } from "./motion";

const TX = "0xca8d066095a407552697f77dc866ae939390712a87e38eabb12dc52efc342c62";
const EXPLORER = "https://explorer.testnet.whitechain.io";

const stages = [
  ["Issue", "Create a USD invoice with an EIP-712 signed payment request and share one link."],
  ["Pay", "The client reviews the exact test USDT amount, network and recipient, then pays from their wallet."],
  ["Verify", "SenFund confirms the settlement onchain and issues an independently checkable receipt."],
  ["Convert", "A sample quote shows the simulated USD conversion rate, fee and net amount."],
  ["Pay out", "A mocked payout adapter shows the FX quote, fee, estimated INR and payout reference."],
];

const features = [
  ["Signed invoices", "Every payment request is signed and binds the invoice ID, merchant, recipient, token, amount, expiry and chain."],
  ["Onchain verification", "Settlement is confirmed against the real Whitechain Sepolia contract, with replay and duplicate protection."],
  ["Unified receipt", "One downloadable receipt separates the verified chain transaction from the simulated fiat stages."],
  ["Independent checkout", "The static checkout verifies payments even while the primary app is offline."],
];

function Icon({ d }) {
  return <svg aria-hidden="true" viewBox="0 0 24 24" width="24" height="24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"><path d={d} /></svg>;
}

const icons = {
  invoice: "M7 3h7l4 4v14H7zM14 3v4h4M10 12h6M10 16h6",
  wallet: "M4 7h15v12H4zM4 7l2-3h11l2 3M15 13h2",
  receipt: "M6 3h12v18l-3-2-3 2-3-2-3 2zM9 11l2 2 4-4",
  convert: "M7 8l-4 4 4 4M17 8l4 4-4 4M4 12h16",
  payout: "M12 3v12m0 0l-4-4m4 4l4-4M5 21h14",
};

function FlowCard({ i, className, eyebrow, title, sub, icon }) {
  return (
    <Rise i={i} className={"flowCard " + className}>
      <span className="flowIcon"><Icon d={icon} /></span>
      <span className="eyebrow">{eyebrow}</span>
      <strong>{title}</strong>
      <span className="flowSub">{sub}</span>
    </Rise>
  );
}

export default async function Page() {
  await connection();
  const accounts = accountMode();
  const signIn = accounts ? "/api/auth/sign-in" : "#access";
  return (
    <Motion>
    <div className="site">
      <div className="aurora" aria-hidden="true"><i /><i /><i /></div>
      <header className="siteHeader">
        <div className="wrap headerRow">
          <a className="wordmark" href="/">SenFund</a>
          <nav className="headerNav" aria-label="Main">
            <a href="#how">How it works</a>
            <a href="#features">Features</a>
            <a href="#about">About</a>
          </nav>
          <div className="headerActions">
            <a className="button plain" href={signIn}>Log in</a>
            <a className="button primary" href={signIn}>Sign up</a>
          </div>
          <details className="menu">
            <summary aria-label="Menu">Menu</summary>
            <nav aria-label="Mobile">
              <a href="#how">How it works</a>
              <a href="#features">Features</a>
              <a href="#about">About</a>
              <a href={signIn}>Log in</a>
              <a href={signIn}>Sign up</a>
            </nav>
          </details>
        </div>
      </header>

      <main className="siteMain">
        <section className="hero wrap">
          <div className="heroCopy">
            <Rise i={0}><p className="heroBadge"><span className="pulse" />Whitechain Sepolia · Testnet demo</p></Rise>
            <Rise i={1}><h1>Invoice in USD.<br />Settle in USDT.<br /><em>Paid out in INR.</em></h1></Rise>
            <Rise i={2}><p className="lede">SenFund lets Indian freelancers bill US clients in dollars, receive payment in test USDT onchain, and follow a verified receipt through simulated conversion and payout.</p></Rise>
            <Rise i={3} className="heroActions">
              <a className="button primary big" href={signIn}>Start invoicing</a>
              <a className="button big" href="#how">See how it works</a>
            </Rise>
            <Rise i={4} className="heroStats">
              <div><strong>3 test USDT</strong><span>verified settlement</span></div>
              <div><strong>Block 12352312</strong><span>Whitechain Sepolia</span></div>
              <div><strong>0 real funds</strong><span>simulated fiat stages</span></div>
            </Rise>
          </div>
          <figure className="flow" aria-label="Payment pipeline from invoice to verified receipt">
            <FlowCard i={0} className="invoiceCard" icon={icons.invoice} eyebrow="Invoice" title="25.00 USD" sub="Signed request · EIP-712" />
            <span className="flowLink" aria-hidden="true"><i /><i /></span>
            <FlowCard i={1} className="walletCard" icon={icons.wallet} eyebrow="Wallet payment" title="25 test USDT" sub="Whitechain Sepolia · chain 1874" />
            <span className="flowLink" aria-hidden="true"><i /><i /></span>
            <FlowCard i={2} className="receiptCard" icon={icons.receipt} eyebrow="Receipt" title="Settled" sub="Confirmed onchain · verified" />
            <Float className="flowChip chipConvert" i={1} y={8} duration={5}><span>Convert</span> simulated · 24.50 USD net</Float>
            <Float className="flowChip chipPayout" i={2} y={8} duration={6}><span>Payout</span> simulated · ₹1,920.00 est.</Float>
          </figure>
        </section>

        <Reveal id="how" className="band">
          <div className="wrap">
            <p className="eyebrow center">How it works</p>
            <h2>A payment, stage by stage</h2>
            <p className="bandSub">Blockchain settlement is real and verified. Conversion and payout are clearly labelled simulations.</p>
            <ol className="pipeline">
              {stages.map(([title, text], index) => (
                <li key={title}>
                  <span className="pipelineIndex">{String(index + 1).padStart(2, "0")}</span>
                  <h3>{title}{index >= 3 && <em className="simTag">simulated</em>}</h3>
                  <p>{text}</p>
                </li>
              ))}
            </ol>
          </div>
        </Reveal>

        <Reveal id="features" className="wrap features">
          <p className="eyebrow center">Features</p>
          <h2>Built for verifiable payments</h2>
          <div className="featureGrid">
            {features.map(([title, text]) => (
              <article key={title} className="featureCard">
                <h3>{title}</h3><p>{text}</p>
              </article>
            ))}
          </div>
        </Reveal>

        <Reveal className="wrap split">
          <div>
            <h2>For freelancers</h2>
            <p>Issue invoices in USD, track each one from sent to settled, and export receipts without chasing payment screenshots.</p>
          </div>
          <div>
            <h2>For clients</h2>
            <p>Pay through the shared link. No SenFund account is needed, only a wallet on the supported network.</p>
          </div>
        </Reveal>

        <Reveal id="about" className="band">
          <div className="wrap about">
            <p className="eyebrow">About SenFund</p>
            <h2>An early testnet product</h2>
            <p>A real settlement has run end to end on Whitechain Sepolia: 3 test USDT paid through the SenFund settlement contract, confirmed in block 12352312.</p>
            <p><a href={`${EXPLORER}/tx/${TX}`} target="_blank" rel="noopener">View the testnet transaction</a> <code>{TX.slice(0, 10)}…{TX.slice(-6)}</code></p>
            <p className="note">Testnet only. USD conversion and INR payout are simulated in this version. No real funds move and mainnet is disabled.</p>
          </div>
        </Reveal>

        <Reveal id="access" className="wrap closing">
          <h2>Start invoicing</h2>
          {accounts ? (
            <>
              <p>Sign in with your account to open your workspace.</p>
              <a className="button primary big" href="/api/auth/sign-in">Sign up or log in</a>
            </>
          ) : (
            <>
              <p>Accounts are not enabled on this server yet. You can explore the local testnet demo workspace instead.</p>
              <a className="button primary big" href="/workspace">Open local demo workspace</a>
            </>
          )}
        </Reveal>
      </main>

      <footer className="siteFooter">
        <div className="wrap footerRow">
          <a className="wordmark" href="/">SenFund</a>
          <nav aria-label="Footer">
            <a href="#how">How it works</a>
            <a href="#features">Features</a>
            <a href="#about">About</a>
            <a href="/workspace">Workspace</a>
          </nav>
          <p>Testnet software. Simulated conversion and payout.</p>
        </div>
      </footer>
    </div>
    </Motion>
  );
}
