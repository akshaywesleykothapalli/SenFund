"use client";

import { useId, useState } from "react";
import { motion, useReducedMotion } from "framer-motion";

export default function Disclosure({ title, children, className = "" }) {
  const [open, setOpen] = useState(false);
  const reduce = useReducedMotion();
  const id = useId();
  const triggerId = id + "-trigger";
  const panelId = id + "-panel";

  return <div className={`disclosure ${className}`} data-open={open}>
    <button id={triggerId} type="button" className="disclosureTrigger"
      aria-expanded={open} aria-controls={panelId} onClick={() => setOpen(value => !value)}>
      <span>{title}</span>
      <motion.svg aria-hidden="true" viewBox="0 0 20 20" width="20" height="20"
        fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"
        animate={{ rotate: open ? 180 : 0 }} transition={{ duration: reduce ? 0 : .25 }}>
        <path d="m5 8 5 5 5-5" />
      </motion.svg>
    </button>
    <motion.div id={panelId} role="region" aria-labelledby={triggerId}
      aria-hidden={!open} inert={!open} className="disclosurePanel"
      initial={false} animate={{ height: open ? "auto" : 0, opacity: open ? 1 : 0 }}
      transition={{ height: { duration: reduce ? 0 : .3, ease: [.22, 1, .36, 1] }, opacity: { duration: reduce ? 0 : .18 } }}>
      <div className="disclosureBody">{children}</div>
    </motion.div>
  </div>;
}
