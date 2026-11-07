"use client";
import { MotionConfig, motion, useReducedMotion } from "framer-motion";
import { useEffect, useState } from "react";

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

const draw = (delay, duration = 0.7) => ({ initial: { pathLength: 0, opacity: 0 }, animate: { pathLength: 1, opacity: 1 }, transition: { duration, delay, ease } });
const show = (delay) => ({ initial: { opacity: 0, y: 6 }, animate: { opacity: 1, y: 0 }, transition: { duration: 0.5, delay, ease } });

// Line sketch draws once: invoice -> stablecoin -> local payout. Labels then cycle through example pairs.
const pairs = [["25 USDT", "₮", "₹", "INR"], ["40 USDC", "$", "€", "EUR"], ["30 USDT", "₮", "£", "GBP"], ["50 USDC", "$", "₱", "PHP"], ["60 USDT", "₮", "R$", "BRL"]];
export function Sketch() {
  const reduce = useReducedMotion();
  const [i, setI] = useState(0);
  useEffect(() => { if (reduce) return; const t = setInterval(() => setI((n) => (n + 1) % pairs.length), 3200); return () => clearInterval(t); }, [reduce]);
  const [amount, coin, sign, cur] = pairs[i];
  const swap = (d) => (i ? { initial: { opacity: 0, y: 6 }, animate: { opacity: 1, y: 0 }, transition: { duration: 0.4, ease } } : show(d));
  const text = { fill: "currentColor", stroke: "none", fontWeight: 700 };
  const label = { ...text, fontSize: 11, fontWeight: 600, opacity: 0.6, textAnchor: "middle" };
  return (
    <svg className="sketch" viewBox="0 0 480 220" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-label="A stablecoin invoice settles onchain and is paid out in a local currency such as INR, EUR or GBP (simulated)" role="img">
      <motion.path d="M40 40h70l22 22v118H40z M110 40v22h22 M56 86h56 M56 106h56 M56 126h36" {...draw(0.1, 0.9)} />
      <motion.text x="56" y="160" fontSize="15" {...text} key={"a"+i} {...swap(0.8)}>{amount}</motion.text>
      <motion.text x="86" y="204" {...label} {...show(0.8)}>Invoice</motion.text>

      <motion.path d="M150 110H198" {...draw(1.0, 0.45)} />
      <motion.path d="M190 102l8 8-8 8" {...draw(1.4, 0.2)} />

      <motion.g style={{ transformOrigin: "240px 110px" }} initial={{ scale: 0.6, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} transition={{ delay: 1.5, type: "spring", stiffness: 260, damping: 20 }}>
        <circle cx="240" cy="110" r="34" />
        <circle cx="240" cy="110" r="25" strokeDasharray="2 5" opacity="0.5" />
        <text x="240" y="117" fontSize="20" textAnchor="middle" {...text}>{coin}</text>
      </motion.g>
      <motion.text x="240" y="204" {...label} {...show(1.7)}>Verified onchain</motion.text>

      <motion.path d="M282 110H338" {...draw(2.0, 0.45)} />
      <motion.path d="M330 102l8 8-8 8" {...draw(2.4, 0.2)} />

      <motion.path d="M360 90l50-28 50 28z M368 96v64 M388 96v64 M432 96v64 M452 96v64 M356 168h108" {...draw(2.5, 0.9)} />
      <motion.text x="410" y="138" fontSize="20" textAnchor="middle" {...text} key={"s"+i} {...swap(3.2)}>{sign}</motion.text>
      <motion.text x="410" y="204" {...label} key={"c"+i} {...swap(3.2)}>{cur} payout · simulated</motion.text>
    </svg>
  );
}

// "How it works": steps advance one at a time like frames; click to jump.
export function Pipeline({ steps }) {
  const reduce = useReducedMotion();
  const [active, setActive] = useState(0);
  const [auto, setAuto] = useState(!reduce);
  useEffect(() => {
    if (!auto || reduce) return;
    const id = setTimeout(() => setActive((v) => (v + 1) % steps.length), 2800);
    return () => clearTimeout(id);
  }, [active, auto, reduce, steps.length]);
  return (
    <ol className="pipeline">
      {steps.map(({ title, text, d, sim }, i) => (
        <li key={title} className={i === active ? "on" : i < active ? "done" : ""}>
          <button type="button" onClick={() => { setAuto(false); setActive(i); }} aria-current={i === active ? "step" : undefined}>
            <span className="pipelineIndex"><svg aria-hidden="true" viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round"><path d={d} /></svg></span>
            <h3>{i + 1}. {title}{sim && <em className="simTag">simulated</em>}</h3>
            <p>{text}</p>
            {i === active && auto && <motion.i className="pipelineBar" key={active} initial={{ scaleX: 0 }} animate={{ scaleX: 1 }} transition={{ duration: 2.8, ease: "linear" }} />}
          </button>
        </li>
      ))}
    </ol>
  );
}
