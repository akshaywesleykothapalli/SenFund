"use client";
// Plain wrappers: the site is intentionally static (no entrance, hover or looping motion).
export const Motion = ({ children }) => children;
export const Reveal = ({ as: Tag = "section", ...props }) => <Tag {...props} />;
export const Rise = ({ i, ...props }) => <div {...props} />;
export const Float = ({ i, y, duration, ...props }) => <div {...props} />;
export const FlowDot = ({ delay, ...props }) => null;
