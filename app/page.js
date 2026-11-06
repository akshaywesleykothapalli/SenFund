import { connection } from "next/server";
import { accountMode } from "./account-server";

const TX = "0xca8d066095a407552697f77dc866ae939390712a87e38eabb12dc52efc342c62";
const EXPLORER = "https://explorer.testnet.whitechain.io";

const steps = [
  ["Create and share an invoice", "Enter a USD amount and a client. SenFund signs the request and gives you one link to send.", "M7 3h7l4 4v14H7zM14 3v4h4M10 12h6M10 16h6"],
  ["Client pays from their wallet", "The client opens the link, checks the merchant and amount, and approves the exact USDT amount.", "M4 7h15v12H4zM4 7l2-3h11l2 3M15 13h2"],
  ["Verify settlement and get the receipt", "SenFund confirms the onchain settlement event, then you download a receipt for your records.", "M6 3h12v18l-3-2-3 2-3-2-3 2zM9 11l2 2 4-4"],
];

function Icon({ d }) {
  return <svg aria-hidden="true" viewBox="0 0 24 24" width="24" height="24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"><path d={d} /></svg>;
}

export default async function Page() {
  await connection();
  const accounts = accountMode();
  const signIn = accounts ? "/api/auth/sign-in" : "#access";
  return (
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
          <h1>Send an invoice. Get paid in USDT.</h1>
          <figure className="flow" aria-label="A 3.00 USD demo invoice paid with test USDT and settled with a receipt">
            <div className="card invoiceCard">
              <span className="eyebrow">Invoice</span>
              <strong>3.00 USD</strong>
              <span>SenFund testnet invoice</span>
            </div>
            <div className="card walletCard">
              <span className="eyebrow">Wallet payment</span>
              <strong>3 test USDT</strong>
              <span>Approved and settled onchain</span>
            </div>
            <div className="card receiptCard">
              <span className="eyebrow">Receipt</span>
              <strong>Settled</strong>
              <span>Block 12352312</span>
            </div>
          </figure>
          <p className="lede">Bill clients in dollars, let them pay from any compatible wallet, and keep a verified receipt for every payment.</p>
          <div className="heroActions">
            <a className="button primary" href={signIn}>Sign up</a>
            <a className="button" href="#how">See how it works</a>
          </div>
        </section>

        <section id="how" className="band reveal">
          <div className="wrap">
            <h2>How it works</h2>
            <ol className="steps">
              {steps.map(([title, text, d]) => (
                <li key={title}><Icon d={d} /><h3>{title}</h3><p>{text}</p></li>
              ))}
            </ol>
          </div>
        </section>

        <section className="wrap split reveal">
          <div>
            <h2>For freelancers</h2>
            <p>Issue invoices in USD, track each one from sent to settled, and export receipts without chasing payment screenshots.</p>
          </div>
          <div>
            <h2>For clients</h2>
            <p>Pay through the shared link. No SenFund account is needed, only a wallet on the supported network.</p>
          </div>
        </section>

        <section id="about" className="band reveal">
          <div className="wrap about">
            <h2>About SenFund</h2>
            <p>SenFund is an early testnet product. A real settlement has run end to end on Whitechain Sepolia: 3 test USDT paid through the SenFund settlement contract, confirmed in block 12352312.</p>
            <p><a href={`${EXPLORER}/tx/${TX}`} target="_blank" rel="noopener">View the testnet transaction</a> <code>{TX.slice(0, 10)}…{TX.slice(-6)}</code></p>
            <p className="note">Testnet only. USD conversion and INR payout are simulated in this version. No real funds move and mainnet is disabled.</p>
          </div>
        </section>

        <section id="access" className="wrap closing reveal">
          <h2>Start invoicing</h2>
          {accounts ? (
            <>
              <p>Sign in with your account to open your workspace.</p>
              <a className="button primary" href="/api/auth/sign-in">Sign up or log in</a>
            </>
          ) : (
            <>
              <p>Accounts are not enabled on this server yet. You can explore the local testnet demo workspace instead.</p>
              <a className="button primary" href="/workspace">Open local demo workspace</a>
            </>
          )}
        </section>
      </main>

      <footer className="siteFooter">
        <div className="wrap footerRow">
          <a className="wordmark" href="/">SenFund</a>
          <nav aria-label="Footer">
            <a href="#how">How it works</a>
            <a href="#about">About</a>
            <a href="/workspace">Workspace</a>
          </nav>
          <p>Testnet software. Simulated conversion and payout.</p>
        </div>
      </footer>
    </div>
  );
}
