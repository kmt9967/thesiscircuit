"use client";

import { createPortal } from "react-dom";
import { useEffect, useRef, useState } from "react";

type NavItem = { id: string; label: string; detail: string };
type NavGroup = { label: string; items: NavItem[] };

const groups: NavGroup[] = [
  { label: "Intelligence", items: [
    { id: "market", label: "Market Intelligence", detail: "Broker observations and option snapshots" },
    { id: "regime", label: "Market Regime", detail: "Deterministic feature classification" },
  ] },
  { label: "Strategy", items: [
    { id: "arena", label: "Strategy Arena", detail: "Trend, Range, and Defensive agents" },
    { id: "council", label: "Decision Council", detail: "Critic and allocator verdict" },
    { id: "risk", label: "Risk Engine", detail: "Non-overridable policy gates" },
  ] },
  { label: "Positions", items: [
    { id: "position", label: "Current Position", detail: "Actual Alpaca PAPER position" },
    { id: "original-trade", label: "Original Paper Trade", detail: "Verified order and fill lifecycle" },
  ] },
  { label: "Research", items: [
    { id: "shadow", label: "Shadow Desk", detail: "Counterfactual, never broker-executed" },
    { id: "leaderboard", label: "Agent Leaderboard", detail: "Evidence-weighted quality scores" },
    { id: "cycles", label: "Autonomous Cycles", detail: "Finite dry-run research batches" },
    { id: "audit", label: "Research Audit", detail: "Immutable cycle stages" },
    { id: "architecture", label: "Architecture", detail: "Fail-closed reliability controls" },
  ] },
];

function Mark() {
  return <span className="brand-mark" aria-hidden="true"><i /><b /></span>;
}

export default function Navigation({ active, onNavigate }: { active: string; onNavigate: (id: string) => void }) {
  const [openGroup, setOpenGroup] = useState<string | null>(null);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [mounted, setMounted] = useState(false);
  const [accordions, setAccordions] = useState<Record<string, boolean>>({ Intelligence: true, Strategy: true });
  const navRef = useRef<HTMLElement>(null);

  useEffect(() => setMounted(true), []);
  useEffect(() => {
    const close = (event: PointerEvent) => {
      if (navRef.current && !navRef.current.contains(event.target as Node)) setOpenGroup(null);
    };
    const escape = (event: KeyboardEvent) => {
      if (event.key === "Escape") { setOpenGroup(null); setMobileOpen(false); }
    };
    document.addEventListener("pointerdown", close);
    window.addEventListener("keydown", escape);
    return () => { document.removeEventListener("pointerdown", close); window.removeEventListener("keydown", escape); };
  }, []);
  useEffect(() => {
    if (!mobileOpen) return;
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => { document.body.style.overflow = previous; };
  }, [mobileOpen]);

  const navigate = (id: string) => {
    setOpenGroup(null);
    setMobileOpen(false);
    onNavigate(id);
  };

  const drawer = mobileOpen ? <div className="mobile-layer" role="presentation">
    <button className="mobile-backdrop" aria-label="Close navigation" onClick={() => setMobileOpen(false)} />
    <aside className="mobile-drawer" role="dialog" aria-modal="true" aria-label="Site navigation">
      <div className="drawer-head">
        <button className="brand-button" onClick={() => navigate("overview")}><Mark /><span>THESIS<b>CIRCUIT</b></span></button>
        <button className="icon-button" aria-label="Close navigation" onClick={() => setMobileOpen(false)}>×</button>
      </div>
      <div className="drawer-status"><span className="status-dot" />PAPER ONLY <b>EXECUTION OFF</b></div>
      <div className="drawer-scroll">
        <button className={`drawer-link ${active === "overview" ? "active" : ""}`} onClick={() => navigate("overview")}>Overview <span>Command center</span></button>
        {groups.map(group => {
          const expanded = Boolean(accordions[group.label]);
          return <div className="drawer-group" key={group.label}>
            <button className="drawer-accordion" aria-expanded={expanded} onClick={() => setAccordions(value => ({ ...value, [group.label]: !expanded }))}>{group.label}<span>{expanded ? "−" : "+"}</span></button>
            {expanded ? <div className="drawer-items">{group.items.map(item => <button key={item.id} className={active === item.id ? "active" : ""} onClick={() => navigate(item.id)}><b>{item.label}</b><small>{item.detail}</small></button>)}</div> : null}
          </div>;
        })}
      </div>
      <p className="drawer-disclosure">SIMULATED PAPER TRADING — NO REAL FUNDS</p>
    </aside>
  </div> : null;

  return <>
    <header className="site-header">
      <div className="nav-shell">
        <button className="brand-button" onClick={() => navigate("overview")} aria-label="ThesisCircuit overview"><Mark /><span>THESIS<b>CIRCUIT</b></span></button>
        <nav className="desktop-nav" aria-label="Primary" ref={navRef}>
          <button className={active === "overview" ? "active" : ""} onClick={() => navigate("overview")}>Overview</button>
          {groups.map(group => {
            const current = group.items.some(item => item.id === active);
            const open = openGroup === group.label;
            return <div className="nav-group" key={group.label}>
              <button className={current ? "active" : ""} aria-expanded={open} onClick={() => setOpenGroup(open ? null : group.label)}>{group.label}<span aria-hidden="true">⌄</span></button>
              {open ? <div className="nav-menu">{group.items.map(item => <button key={item.id} className={active === item.id ? "active" : ""} onClick={() => navigate(item.id)}><span>{item.label}</span><small>{item.detail}</small></button>)}</div> : null}
            </div>;
          })}
        </nav>
        <div className="nav-state"><span className="status-dot pulse" /><b>PAPER</b><span>EXECUTION OFF</span></div>
        <button className="hamburger" aria-label="Open navigation" aria-expanded={mobileOpen} onClick={() => setMobileOpen(true)}><span /><span /><span /></button>
      </div>
    </header>
    {mounted ? createPortal(drawer, document.body) : null}
  </>;
}
