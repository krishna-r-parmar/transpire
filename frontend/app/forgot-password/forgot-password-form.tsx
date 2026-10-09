"use client";

import { ArrowRight, MailCheck, TriangleAlert } from "lucide-react";
import { TenantLink as Link } from "@/components/app/tenant-link";
import { FormEvent, useState } from "react";
import { RecoveryShell } from "@/components/auth/recovery-shell";
import { apiRequest } from "@/lib/api";
import styles from "./recovery.module.css";

export function ForgotPasswordForm() {
  const [email, setEmail] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [serviceError, setServiceError] = useState(false);

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setError("");
    setServiceError(false);
    const normalizedEmail = email.trim();

    if (!normalizedEmail) {
      setError("Enter your work email address.");
      return;
    }
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(normalizedEmail)) {
      setError("Enter a valid work email address.");
      return;
    }

    setLoading(true);
    try {
      const response = await apiRequest("/auth/password-reset/request", {
        method: "POST",
        body: JSON.stringify({ email: normalizedEmail }),
      });
      if (!response.ok) {
        setServiceError(true);
        return;
      }
      setSubmitted(true);
    } catch {
      setServiceError(true);
    } finally {
      setLoading(false);
    }
  };

  return (
    <RecoveryShell
      pageId="forgot-password-top"
      eyebrow="Account recovery"
      title="Find your way back in."
      description="Enter your work email. If it matches an active account, we will send a private, time-limited reset link."
    >
      {submitted ? (
        <div className={styles.status} role="status">
          <span className={styles.statusIcon}><MailCheck aria-hidden="true" size={19} /></span>
          <div>
            <h2>Check your work email</h2>
            <p>
              If an active account matches {email.trim()}, password reset instructions are on their way.
            </p>
          </div>
          <Link href="/sign-in">Return to sign in</Link>
        </div>
      ) : (
        <form className={styles.form} noValidate onSubmit={handleSubmit}>
          {serviceError ? (
            <div className={styles.status} data-tone="error" role="alert">
              <span className={styles.statusIcon}><TriangleAlert aria-hidden="true" size={18} /></span>
              <div>
                <h2>Recovery is temporarily unavailable</h2>
                <p>Please wait a moment and try again.</p>
              </div>
            </div>
          ) : null}
          <div className={styles.field} data-invalid={Boolean(error)}>
            <label htmlFor="recovery-email">Work email</label>
            <input
              id="recovery-email"
              name="email"
              type="email"
              inputMode="email"
              autoComplete="email"
              placeholder="name@company.com"
              value={email}
              aria-invalid={Boolean(error)}
              aria-describedby={error ? "recovery-email-error" : "recovery-note"}
              onChange={(event) => {
                setEmail(event.target.value);
                if (error) setError("");
              }}
            />
            {error ? <p className={styles.error} id="recovery-email-error">{error}</p> : null}
          </div>
          <p className={styles.support} id="recovery-note">
            For privacy, the confirmation is the same whether or not an account is found.
          </p>
          <button className={styles.submit} type="submit" disabled={loading}>
            {loading ? <><i aria-hidden="true" /> Sending securely</> : <>Send reset link <ArrowRight aria-hidden="true" size={17} /></>}
          </button>
        </form>
      )}
    </RecoveryShell>
  );
}
