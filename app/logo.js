export default function Logo({ className = "wordmark", caption }) {
  return <a className={className} href="/" aria-label="SenFund home">SenFund<span className="brandDot" aria-hidden="true">.</span>{caption && <span className="brandCaption">{caption}</span>}</a>;
}
