import "./style.css";

export const metadata = {
  title: "SenFund",
  icons: { icon: "/icon.svg" },
  description: "Issue and reconcile test USDT invoices on Whitechain Sepolia.",
};

export default function Layout({ children }) {
  return <html lang="en"><body>{children}</body></html>;
}
