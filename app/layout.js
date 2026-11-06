import "./style.css";

export const metadata = {
  title: "Invoices | SenFund",
  description: "Issue and reconcile test USDT invoices on Whitechain Sepolia.",
};

export default function Layout({ children }) {
  return <html lang="en"><body>{children}</body></html>;
}
