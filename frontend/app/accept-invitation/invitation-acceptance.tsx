"use client";

import { ArrowRight, CheckCircle2, Eye, EyeOff, ShieldAlert } from "lucide-react";
import { TenantLink as Link } from "@/components/app/tenant-link";
import { FormEvent, useEffect, useState } from "react";
import { RecoveryShell } from "@/components/auth/recovery-shell";
import { apiRequest } from "@/lib/api";
import styles from "../forgot-password/recovery.module.css";

type Invitation = {
  email: string;
  display_name: string;
  tenant_name: string;
  sign_in_url: string;
  requires_password: boolean;
  sso_required: boolean;
  expires_at: string;
};

export function InvitationAcceptance({ token }: { token: string }) {
  const [invitation, setInvitation] = useState<Invitation | null>(null);
  const [loading, setLoading] = useState(Boolean(token));
  const [submitting, setSubmitting] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState(token ? "" : "This invitation link is incomplete.");
  const [complete, setComplete] = useState(false);

  useEffect(() => {
    let active = true;
    if (!token) return;
    apiRequest("/auth/invitations/inspect", {
      method: "POST",
      body: JSON.stringify({ token }),
    })
      .then(async (response) => {
        if (!active) return;
        if (!response.ok) {
          setError("This invitation is invalid or has expired.");
          return;
        }
        setInvitation((await response.json()) as Invitation);
      })
      .catch(() => active && setError("We could not verify this invitation right now."))
      .finally(() => active && setLoading(false));
    return () => { active = false; };
  }, [token]);

  const accept = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!invitation) return;
    const form = new FormData(event.currentTarget);
    const password = String(form.get("password") ?? "");
    const confirmation = String(form.get("confirmation") ?? "");
    setError("");
    if (invitation.requires_password && password.length < 12) {
      setError("Use at least 12 characters for your password.");
      return;
    }
    if (invitation.requires_password && password !== confirmation) {
      setError("The passwords do not match.");
      return;
    }
    setSubmitting(true);
    try {
      const response = await apiRequest("/auth/invitations/accept", {
        method: "POST",
        body: JSON.stringify({
          token,
          new_password: invitation.requires_password ? password : null,
        }),
      });
      if (!response.ok) {
        const payload = (await response.json().catch(() => null)) as { detail?: string } | null;
        setError(payload?.detail ?? "This invitation could not be accepted.");
        return;
      }
      setComplete(true);
    } catch {
      setError("Invitation acceptance is temporarily unavailable.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <RecoveryShell
      pageId="accept-invitation-top"
      eyebrow="Organisation invitation"
      title="Your place in TRANSPIRE is ready."
      description="Confirm your invitation and join the workspace where ideas become meaningful improvements."
      visualLabel="Secure organisational invitation"
      visualTitle="Join the people turning everyday observations into better ways of working."
      visualSteps={["Accept your verified invitation", "Enter your secure workspace", "Start noticing what could be better"]}
    >
      {loading ? (
        <div className={styles.status} role="status"><span className={styles.statusIcon}><i aria-hidden="true" /></span><div><h2>Verifying your invitation</h2><p>This should only take a moment.</p></div></div>
      ) : complete ? (
        <div className={styles.status} role="status"><span className={styles.statusIcon}><CheckCircle2 aria-hidden="true" size={20} /></span><div><h2>Welcome to TRANSPIRE</h2><p>Your access is active. {invitation?.sso_required ? "Continue with the Microsoft account matching your invited email." : "Sign in with your work email to continue."}</p></div><Link href={invitation?.sign_in_url ?? "/sign-in"}>Continue to sign in <ArrowRight aria-hidden="true" size={15} /></Link></div>
      ) : !invitation ? (
        <div className={styles.status} data-tone="error" role="alert"><span className={styles.statusIcon}><ShieldAlert aria-hidden="true" size={20} /></span><div><h2>Invitation unavailable</h2><p>{error}</p></div><Link href="/">Return to TRANSPIRE</Link></div>
      ) : (
        <form className={styles.form} onSubmit={accept}>
          <div className={styles.invitationSummary}>
            <span>Invited to</span><strong>{invitation.tenant_name}</strong><p>{invitation.display_name} · {invitation.email}</p>
          </div>
          {invitation.requires_password ? <>
            <div className={styles.field}><label htmlFor="invitation-password">Create password</label><div className={styles.passwordWrap}><input id="invitation-password" name="password" type={showPassword ? "text" : "password"} autoComplete="new-password" required minLength={12} /><button className={styles.passwordToggle} type="button" onClick={() => setShowPassword((value) => !value)} aria-label={showPassword ? "Hide password" : "Show password"}>{showPassword ? <EyeOff aria-hidden="true" size={17} /> : <Eye aria-hidden="true" size={17} />}</button></div><p className={styles.passwordHint}>Use at least 12 characters.</p></div>
            <div className={styles.field}><label htmlFor="invitation-confirmation">Confirm password</label><input id="invitation-confirmation" name="confirmation" type={showPassword ? "text" : "password"} autoComplete="new-password" required minLength={12} /></div>
          </> : <p className={styles.support}>{invitation.sso_required ? "This organisation uses Microsoft SSO. No TRANSPIRE password is required." : "Your existing TRANSPIRE password will remain unchanged."}</p>}
          {error ? <p className={styles.error} role="alert">{error}</p> : null}
          <button className={styles.submit} type="submit" disabled={submitting}>{submitting ? <><span>Activating access</span><i aria-hidden="true" /></> : <>Accept invitation <ArrowRight aria-hidden="true" size={17} /></>}</button>
        </form>
      )}
    </RecoveryShell>
  );
}
