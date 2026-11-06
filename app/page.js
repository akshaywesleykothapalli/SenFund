import { connection } from "next/server";
import { accountMode } from "./account-server";
import { Motion, Pipeline, Reveal, Rise, Sketch } from "./motion";

const TX = "0xca8d066095a407552697f77dc866ae939390712a87e38eabb12dc52efc342c62";
const EXPLORER = "https://explorer.testnet.whitechain.io";

const stages = [
  ["Invoice", "Bill in USDT, share one link.", "invoice"],
  ["Pay", "Client pays test USDT from a wallet.", "wallet"],
  ["Verify", "Checked onchain. Receipt issued.", "receipt"],
  ["Convert", "USDT quoted to the payout currency.", "convert"],
  ["Pay out", "Local currency to your bank.", "payout"],
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
      <header className="siteHeader">
        <div className="wrap headerRow">
          <a className="wordmark" href="/">SenFund</a>
          <nav className="headerNav" aria-label="Main">
            <a href="#how">How it works</a>
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
            <Rise i={0}><p className="heroBadge">Whitechain Sepolia · Testnet demo</p></Rise>
            <Rise i={1}><h1>Invoice in USD.<br />Settle in USDT.<br /><em>Paid out in your currency.</em></h1></Rise>
            <Rise i={2}><p className="lede">For freelancers abroad with US clients. Payouts in INR, EUR, GBP, PHP, NGN, BRL and more.</p></Rise>
            <Rise i={3} className="heroActions">
              <a className="button primary big" href={signIn}>Start invoicing</a>
              <a className="button big" href="#how">See how it works</a>
            </Rise>
          </div>
          <Rise i={2} className="flow"><Sketch /></Rise>
        </section>

        <Reveal id="how" className="band">
          <div className="wrap">
            <p className="eyebrow center">How it works</p>
            <h2>Five steps</h2>
            <Pipeline steps={stages.map(([title, text, icon], i) => ({ title, text, d: icons[icon], sim: i >= 3 }))} />
          </div>
        </Reveal>

        <Reveal id="about" className="band">
          <div className="wrap about">
            <h2>Live on testnet</h2>
            <ul className="facts">
              <li><strong>3 USDT</strong> settled</li>
              <li><strong>Block 12352312</strong> Whitechain Sepolia</li>
              <li><strong>0</strong> real funds</li>
            </ul>
            <p><a href={`${EXPLORER}/tx/${TX}`} target="_blank" rel="noopener">View transaction</a></p>
            <p className="note">Convert and pay out are simulated.</p>
          </div>
        </Reveal>

        <Reveal id="access" className="wrap closing">
          <h2>Start invoicing</h2>
          {accounts ? (
            <>
              <a className="button primary big" href="/api/auth/sign-in">Sign up or log in</a>
            </>
          ) : (
            <>
              
              <a className="button primary big" href="/workspace">Open demo workspace</a>
            </>
          )}
        </Reveal>
      </main>

      <footer className="siteFooter">
        <div className="wrap footerRow">
          <a className="wordmark" href="/">SenFund</a>
          <nav aria-label="Footer">
            <a href="#how">How it works</a>
            <a href="#about">About</a>
            <a href="/workspace">Workspace</a>
          </nav>
          <p>Testnet only.</p>
        </div>
      </footer>
    </div>
    </Motion>
  );
}
