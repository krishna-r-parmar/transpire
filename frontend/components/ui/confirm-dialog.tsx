"use client";

import { AlertTriangle, X } from "lucide-react";
import { useCallback, useEffect, useId, useRef, useState } from "react";
import styles from "./ui-controls.module.css";

type ConfirmDialogProps = {
  open: boolean;
  title: string;
  description: string;
  confirmLabel: string;
  busyLabel?: string;
  confirmationText?: string;
  onClose: () => void;
  onConfirm: () => Promise<void> | void;
  busy?: boolean;
  tone?: "danger" | "default";
};

export function ConfirmDialog({ open, title, description, confirmLabel, busyLabel = "Working", confirmationText, onClose, onConfirm, busy = false, tone = "danger" }: ConfirmDialogProps) {
  const titleId = useId();
  const descriptionId = useId();
  const dialog = useRef<HTMLElement>(null);
  const cancelButton = useRef<HTMLButtonElement>(null);
  const [typedValue, setTypedValue] = useState("");
  const confirmed = !confirmationText || typedValue === confirmationText;

  const closeDialog = useCallback(() => {
    setTypedValue("");
    onClose();
  }, [onClose]);

  const confirmDialog = async () => {
    await onConfirm();
    setTypedValue("");
  };

  useEffect(() => {
    if (!open) return;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    cancelButton.current?.focus();
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !busy) {
        closeDialog();
        return;
      }
      if (event.key !== "Tab") return;
      const focusable = dialog.current?.querySelectorAll<HTMLElement>("button:not(:disabled), input:not(:disabled)");
      if (!focusable?.length) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    window.addEventListener("keydown", closeOnEscape);
    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", closeOnEscape);
    };
  }, [busy, closeDialog, open]);

  if (!open) return null;

  return (
    <div className={styles.dialogLayer} role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget && !busy) closeDialog(); }}>
      <section ref={dialog} className={styles.dialog} role="alertdialog" aria-modal="true" aria-labelledby={titleId} aria-describedby={descriptionId} data-tone={tone}>
        <div className={styles.dialogIcon}><AlertTriangle aria-hidden="true" size={20} /></div>
        <button className={styles.dialogClose} type="button" aria-label="Close confirmation" onClick={closeDialog} disabled={busy}><X aria-hidden="true" size={19} /></button>
        <div className={styles.dialogCopy}>
          <p>Confirm action</p>
          <h2 id={titleId}>{title}</h2>
          <span id={descriptionId}>{description}</span>
        </div>
        {confirmationText ? <label className={styles.confirmationField}>Type <strong>{confirmationText}</strong> to continue<input value={typedValue} onChange={(event) => setTypedValue(event.target.value)} autoComplete="off" spellCheck={false} /></label> : null}
        <div className={styles.dialogActions}>
          <button ref={cancelButton} type="button" onClick={closeDialog} disabled={busy}>Keep unchanged</button>
          <button type="button" data-tone={tone} disabled={busy || !confirmed} onClick={() => void confirmDialog()}>{busy ? busyLabel : confirmLabel}</button>
        </div>
      </section>
    </div>
  );
}
