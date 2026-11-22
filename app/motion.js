"use client";
import { AnimatePresence, MotionConfig, motion, useInView, useReducedMotion } from "framer-motion";
import { useEffect, useRef, useState } from "react";

const ease = [0.22, 1, 0.36, 1];

export const Motion = ({ children }) => <MotionConfig reducedMotion="user">{children}</MotionConfig>;

export const Reveal = ({ as = "section", ...props }) => {
  const Tag = motion[as];
  return <Tag initial={{ opacity: 0, y: 24 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true, amount: 0.2 }} transition={{ duration: 0.6, ease }} {...props} />;
};

export const Rise = ({ i = 0, ...props }) => (
  <motion.div initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.6, delay: 0.08 * i, ease }} {...props} />
);

export const Stagger = ({ as = "ol", children, ...props }) => {
  const Tag = motion[as];
  return (
    <Tag initial="hide" whileInView="show" viewport={{ once: true, amount: 0.3 }} variants={{ show: { transition: { staggerChildren: 0.09 } } }} {...props}>
      {children}
    </Tag>
  );
};

export const Item = (props) => (
  <motion.li variants={{ hide: { opacity: 0, y: 18 }, show: { opacity: 1, y: 0, transition: { duration: 0.5, ease } } }} {...props} />
);

const pairs = [["25 USDT", "₹", "INR"], ["40 USDT", "€", "EUR"], ["30 USDT", "£", "GBP"], ["50 USDT", "₱", "PHP"], ["60 USDT", "R$", "BRL"]];
export function Sketch() {
  const reduce = useReducedMotion();
  const target = useRef(null);
  const inView = useInView(target, { amount: 0.15 });
  const [index, setIndex] = useState(0);
  const running = inView && !reduce;
  useEffect(() => {
    if (!running) return;
    const timer = setInterval(() => setIndex(value => (value + 1) % pairs.length), 3000);
    return () => clearInterval(timer);
  }, [running]);
  const [amount, sign, currency] = pairs[index];
  const text = { fill: "currentColor", stroke: "none", fontWeight: 650 };
  const label = { ...text, fontSize: 11, fontWeight: 500, textAnchor: "middle", fill: "#746b5c" };
  const cycle = { duration: 3, repeat: Infinity, ease: "linear" };
  return <div className="sketchScene" ref={target}>
    <svg className="sketch" viewBox="0 0 500 230" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" role="img" aria-label="Illustration of a test USDT invoice, verified onchain settlement and simulated local currency payout.">
      <g><path d="M28 36h76l24 24v124H28z M104 36v24h24 M44 82h62 M44 102h62 M44 122h36" />
        <AnimatePresence mode="sync" initial={false}><motion.text key={amount} x="44" y="162" fontSize="14" {...text} initial={{opacity:0}} animate={{opacity:1}} exit={{opacity:0}} transition={{duration: reduce ? 0 : .24}}>{amount}</motion.text></AnimatePresence>
      </g>
      <path d="M146 110h52m-8-8 8 8-8 8 M290 110h52m-8-8 8 8-8 8" stroke="#c9bea9" />
      {running && <><motion.circle r="3.5" fill="#b58a3e" stroke="none" animate={{cx:[146,198,198,198],cy:110,opacity:[0,1,0,0]}} transition={{...cycle,times:[0,.32,.4,1]}} /><motion.circle r="3.5" fill="#b58a3e" stroke="none" animate={{cx:[290,290,342,342],cy:110,opacity:[0,0,1,0]}} transition={{...cycle,times:[0,.42,.75,1]}} /></>}
      <circle cx="244" cy="110" r="34" fill="#f3ebdb" />
      <motion.circle cx="244" cy="110" r="25" stroke="#b58a3e" strokeDasharray="2 5" style={{transformOrigin:"244px 110px"}} animate={{rotate:running ? 360 : 0}} transition={{duration:12,repeat:running ? Infinity : 0,ease:"linear"}} />
      <text x="244" y="118" fontSize="23" textAnchor="middle" {...text}>₮</text>
      <path d="M362 90l50-28 50 28z M370 98v64 M390 98v64 M434 98v64 M454 98v64 M358 170h108" />
      <AnimatePresence mode="sync" initial={false}><motion.g key={currency} initial={{opacity:0}} animate={{opacity:1}} exit={{opacity:0}} transition={{duration:reduce ? 0 : .24}}>
        <text x="412" y="140" fontSize="23" textAnchor="middle" {...text}>{sign}</text>
        <text x="412" y="210" {...label}>{currency} payout · simulated</text>
      </motion.g></AnimatePresence>
      <text x="78" y="210" {...label}>Invoice</text><text x="244" y="210" {...label}>Verified onchain</text>
    </svg>
  </div>;
}

export function HeroVisual() {
  const reduce = useReducedMotion();
  const ref = useRef(null);
  const visible = useInView(ref, { amount: .15 });
  const floating = visible && !reduce;
  return <div className="heroVisual" ref={ref}>
    <motion.div className="heroArtFrame" initial={{opacity:0,scale:reduce ? 1 : .97}} animate={{opacity:1,scale:1}} transition={{duration:.7,ease}}>
      <img src="/images/senfund-invoice.webp" alt="A freelancer’s desk overlooking a connected city, illustrated in ink and gold." width="1200" height="800" fetchPriority="high" />
    </motion.div>
    <motion.div className="heroInvoiceSlip" animate={{y:floating ? [0,-7,0] : 0,rotate:floating ? [-5,-3,-5] : -5}} transition={{duration:6,repeat:floating ? Infinity : 0,ease:"easeInOut"}}>
      <div className="slipTop"><span>SenFund<span className="brandDot">.</span></span><span>01 / INVOICE</span></div>
      <p>TESTNET EXAMPLE</p><strong>25.00 <span>test USDT</span></strong>
      <div className="slipRule" /><div className="slipBottom"><span>Signed invoice</span><svg aria-hidden="true" width="18" height="18" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="m4 10 4 4 8-8" /></svg></div>
    </motion.div>
    <motion.div className="heroIdentity" animate={{y:floating ? [0,5,0] : 0}} transition={{duration:5,repeat:floating ? Infinity : 0,ease:"easeInOut"}}>
      <span className="identityIcon" aria-hidden="true">↗</span><div><strong>Your name. Your wallet.</strong><span>Recipient checked with ENS</span></div>
    </motion.div>
    <div className="heroFlowPanel"><div className="heroPanelTop"><span>THE PAYMENT TRAIL</span><span className="heroPanelDot">Testnet + simulation</span></div><Sketch /></div>
    <span className="heroArtNote">Independent work. Connected payments.</span>
  </div>;
}

export function Pipeline({ steps }) {
  const list = useRef(null);
  const inView = useInView(list, { once: true, amount: 0.15 });
  const reduce = useReducedMotion();
  const visible = inView || reduce;

  return (
    <ol ref={list} className="pipeline">
      {steps.map(({ title, text, d }, i) => (
        <li key={title}>
          <motion.div className="pipelineCard" whileHover={reduce ? undefined : { y: -5, scale: 1.015 }} transition={{ type: "spring", stiffness: 280, damping: 24 }}>
            <span className="pipelineIndex"><svg aria-hidden="true" viewBox="0 0 24 24" width="21" height="21" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"><path d={d} /></svg></span>
            <div>
              <h3>{i + 1}. {title}</h3>
              <p>{text}</p>
            </div>
          </motion.div>
          {i < steps.length - 1 && <svg className="pipelineArc" aria-hidden="true" viewBox="0 0 144 120" preserveAspectRatio="none" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <motion.path d="M8 4 C93 4 51 116 136 116" vectorEffect="non-scaling-stroke"
              initial={{ pathLength: 0, opacity: 0 }}
              animate={{ pathLength: visible ? 1 : 0, opacity: visible ? 1 : 0 }}
              transition={visible && !reduce ? { duration: 0.47, delay: i * 0.48, ease } : { duration: 0 }} />
            <motion.path d="M128 110 L136 116 L128 119" vectorEffect="non-scaling-stroke"
              initial={{ opacity: 0 }} animate={{ opacity: visible ? 1 : 0 }}
              transition={visible && !reduce ? { duration: 0.14, delay: i * 0.48 + 0.38 } : { duration: 0 }} />
          </svg>}
        </li>
      ))}
    </ol>
  );
}
