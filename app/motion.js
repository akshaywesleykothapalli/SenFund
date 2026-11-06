"use client";
import { MotionConfig, motion } from "framer-motion";

const ease = [0.2, 0.8, 0.2, 1];

export function Motion({ children }) {
  return <MotionConfig reducedMotion="user">{children}</MotionConfig>;
}

export function Reveal({ as = "section", ...props }) {
  const Tag = motion[as];
  return <Tag initial={{ opacity: 0, y: 16 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true, margin: "-60px" }} transition={{ duration: 0.6, ease }} {...props} />;
}

export function Rise({ i = 0, ...props }) {
  return <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.7, ease, delay: 0.15 + i * 0.12 }} whileHover={{ y: -4 }} {...props} />;
}

export function Float({ i = 0, y = 10, duration = 6, ...props }) {
  return <motion.div
    animate={{ y: [0, -y, 0] }}
    transition={{ duration, ease: "easeInOut", repeat: Infinity, delay: i * 0.6 }}
    {...props} />;
}

export function FlowDot({ delay = 0, ...props }) {
  return <motion.span
    className="flowDot"
    animate={{ offsetDistance: ["0%", "100%"] }}
    transition={{ duration: 2.4, ease: "linear", repeat: Infinity, delay }}
    {...props} />;
}
