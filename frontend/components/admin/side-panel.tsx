"use client";

import { X } from "lucide-react";
import { useEffect, useId, useRef, type ReactNode } from "react";
import styles from "./admin-register.module.css";

type SidePanelProps = {
  open: boolean;
  title: string;
  description?: string;
  onClose: () => void;
  children: ReactNode;
};

/** Right-hand panel for adding and editing a single record without leaving the register. */
export function SidePanel({ open, title, description, onClose, children }: SidePanelProps) {
  const titleId = useId();
  const panel = useRef<HTMLElement>(null);
  const opener = useRef<Element | null>(null);

  useEffect(() => {
    if (!open) return;
    opener.current = document.activeElement;
    const first = panel.current?.querySelector<HTMLElement>("input, select, textarea, button:not([data-close])");
    first?.focus();
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const onKeyDown = (event: KeyboardEvent) => { if (event.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKeyDown);
    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", onKeyDown);
      (opener.current as HTMLElement | null)?.focus?.();
    };
  }, [onClose, open]);

  if (!open) return null;
  return <div className={styles.panelLayer}>
    <button type="button" className={styles.panelBackdrop} aria-label="Close panel" tabIndex={-1} onClick={onClose} />
    <aside ref={panel} className={styles.panel} role="dialog" aria-modal="true" aria-labelledby={titleId}>
      <header>
        <div><h2 id={titleId}>{title}</h2>{description ? <p>{description}</p> : null}</div>
        <button type="button" data-close className={styles.panelClose} onClick={onClose} aria-label="Close panel"><X size={18} aria-hidden="true" /></button>
      </header>
      <div className={styles.panelBody}>{children}</div>
    </aside>
  </div>;
}

export type StatusFilterValue = "active" | "inactive" | "all";

export function StatusFilter({ value, onChange, counts, labels = { active: "Active", inactive: "Inactive", all: "All" } }: { value: StatusFilterValue; onChange: (value: StatusFilterValue) => void; counts: Record<StatusFilterValue, number>; labels?: Record<StatusFilterValue, string> }) {
  return <div className={styles.segmented} role="group" aria-label="Filter by status">
    {(["active", "inactive", "all"] as const).map((key) => <button key={key} type="button" aria-pressed={value === key} onClick={() => onChange(key)}>{labels[key]}<span>{counts[key]}</span></button>)}
  </div>;
}
