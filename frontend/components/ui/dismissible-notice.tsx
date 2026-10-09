"use client";

import { X } from "lucide-react";
import { ReactNode } from "react";
import styles from "./dismissible-notice.module.css";

export function DismissibleNotice({ children, tone = "success", onDismiss }: { children: ReactNode; tone?: "success" | "error"; onDismiss: () => void }) {
  return <div className={styles.notice} data-tone={tone} role={tone === "error" ? "alert" : "status"} aria-live={tone === "error" ? "assertive" : "polite"}>
    <p>{children}</p>
    <button type="button" onClick={onDismiss} aria-label="Dismiss notification"><X aria-hidden="true" size={16} /></button>
  </div>;
}
