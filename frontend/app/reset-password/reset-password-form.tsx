"use client";

import { ArrowRight, CheckCircle2, Eye, EyeOff, Link2Off } from "lucide-react";
import { TenantLink as Link } from "@/components/app/tenant-link";
import { FormEvent, useState } from "react";
import { RecoveryShell } from "@/components/auth/recovery-shell";
import { apiRequest } from "@/lib/api";
import styles from "../forgot-password/recovery.module.css";

type ResetPasswordFormProps = {
  token: string;
};

export function ResetPasswordForm({ token }: ResetPasswordFormProps) {
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [errors, setErrors] = useState<{ password?: string; confirmation?: string }>({});
  const [loading, setLoading] = useState(false);
  const [complete, setComplete] = useState(false);
  const [linkError, setLinkError] = useState(!token);

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const nextErrors: typeof errors = {};
    if (password.length < 12) nextErrors.password = "Use at least 12 characters.";
    if (confirmation !== password) nextErrors.confirmation = "Passwords do not match.";
    setErrors(nextErrors);
    if (Object.keys(nextErrors).length > 0) return;

    setLoading(true);
    try {
      const response = await apiRequest("/auth/password-reset/complete", {
        method: "POST",
        body: JSON.stringify({ token, new_password: password }),
      });
      if (!response.ok) {
        setLinkError(response.status === 400);
        if (response.status !== 400) {
          setErrors({ password: "Password reset is temporarily unavailable. Try again." });
        }
        return;
      }
      window.history.replaceState({}, "", "/reset-password?complete=1");
      setComplete(true);
    } catch {
      setErrors({ password: "Password reset is temporarily unavailable. Try again." });
    } finally {
      setLoading(false);
    }
  };

  return (
    <RecoveryShell
      pageId="reset-password-top"
      eyebrow="Secure password reset"
      title={complete ? "Access restored." : "Choose a new password."}
      description={complete ? "Your previous sessions have been closed to protect your account." : "Create a strong password you do not use for another service."}
    >
      {complete ? (
        <div className={styles.status} role="status">
          <span className={styles.statusIcon}><CheckCircle2 aria-hidden="true" size={19} /></span>
          <div>
            <h2>Your password has been changed</h2>
            <p>Sign in again on each device using your new password.</p>
          </div>
          <Link href="/sign-in">Continue to sign in</Link>
        </div>
      ) : linkError ? (
        <div className={styles.status} data-tone="error" role="alert">
          <span className={styles.statusIcon}><Link2Off aria-hidden="true" size={19} /></span>
          <div>
            <h2>This reset link cannot be used</h2>
            <p>It may have expired or already been used. Request a new private link.</p>
          </div>
          <Link href="/forgot-password">Request another link</Link>
        </div>
      ) : (
        <form className={styles.form} noValidate onSubmit={handleSubmit}>
          <div className={styles.field} data-invalid={Boolean(errors.password)}>
            <label htmlFor="new-password">New password</label>
            <div className={styles.passwordWrap}>
              <input
                id="new-password"
                name="new-password"
                type={showPassword ? "text" : "password"}
                autoComplete="new-password"
                value={password}
                aria-invalid={Boolean(errors.password)}
                aria-describedby={errors.password ? "new-password-error" : "password-hint"}
                onChange={(event) => {
                  setPassword(event.target.value);
                  if (errors.password) setErrors((current) => ({ ...current, password: undefined }));
                }}
              />
              <button
                className={styles.passwordToggle}
                type="button"
                aria-label={showPassword ? "Hide password" : "Show password"}
                aria-pressed={showPassword}
                onClick={() => setShowPassword((visible) => !visible)}
              >
                {showPassword ? <EyeOff aria-hidden="true" size={17} /> : <Eye aria-hidden="true" size={17} />}
              </button>
            </div>
            {errors.password ? <p className={styles.error} id="new-password-error">{errors.password}</p> : null}
            <p className={styles.passwordHint} id="password-hint">Use at least 12 characters.</p>
          </div>

          <div className={styles.field} data-invalid={Boolean(errors.confirmation)}>
            <label htmlFor="confirm-password">Confirm new password</label>
            <input
              id="confirm-password"
              name="confirm-password"
              type={showPassword ? "text" : "password"}
              autoComplete="new-password"
              value={confirmation}
              aria-invalid={Boolean(errors.confirmation)}
              aria-describedby={errors.confirmation ? "confirm-password-error" : undefined}
              onChange={(event) => {
                setConfirmation(event.target.value);
                if (errors.confirmation) setErrors((current) => ({ ...current, confirmation: undefined }));
              }}
            />
            {errors.confirmation ? <p className={styles.error} id="confirm-password-error">{errors.confirmation}</p> : null}
          </div>

          <button className={styles.submit} type="submit" disabled={loading}>
            {loading ? <><i aria-hidden="true" /> Securing account</> : <>Reset password <ArrowRight aria-hidden="true" size={17} /></>}
          </button>
        </form>
      )}
    </RecoveryShell>
  );
}
