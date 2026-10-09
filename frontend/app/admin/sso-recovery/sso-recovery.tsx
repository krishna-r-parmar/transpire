"use client";

import { ShieldCheck } from "lucide-react";
import { FormEvent, useEffect, useState } from "react";
import { RecoveryShell } from "@/components/auth/recovery-shell";
import { apiRequest } from "@/lib/api";
import { useTenantRouter as useRouter } from "@/lib/use-tenant-router";
import styles from "../../forgot-password/recovery.module.css";

export function SSORecovery({ token }: { token: string }) {
  const router = useRouter();
  const [ready, setReady] = useState(false);
  const [busy, setBusy] = useState(Boolean(token));
  const [error, setError] = useState(token ? "" : "This recovery link is incomplete.");

  useEffect(() => {
    if (!token) return;
    apiRequest("/auth/sso/recovery/redeem", { method: "POST", body: JSON.stringify({ token }) })
      .then(async (response) => {
        if (!response.ok) {
          const payload = await response.json().catch(() => null) as { detail?: string } | null;
          setError(payload?.detail ?? "This recovery link is invalid or expired.");
          return;
        }
        window.history.replaceState(null, "", window.location.pathname);
        setReady(true);
      })
      .catch(() => setError("Recovery is temporarily unavailable."))
      .finally(() => setBusy(false));
  }, [token]);

  const repair = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const directoryId = String(new FormData(event.currentTarget).get("directory_id") ?? "").trim();
    setBusy(true); setError("");
    try {
      const response = await apiRequest("/admin/sso/recovery", { method: "PUT", body: JSON.stringify({ entra_directory_id: directoryId }) });
      if (!response.ok) {
        const payload = await response.json().catch(() => null) as { detail?: string } | null;
        setError(payload?.detail ?? "The SSO configuration could not be repaired.");
        return;
      }
      router.replace("/admin/configuration?sso=recovery");
    } catch { setError("Recovery is temporarily unavailable."); }
    finally { setBusy(false); }
  };

  return <RecoveryShell pageId="sso-recovery-top" eyebrow="Restricted platform recovery" title="Repair Microsoft sign-in only." description="This temporary session cannot access ideas, projects, people, or exports." visualLabel="Audited recovery" visualTitle="Restore authentication without opening access to organisational data." visualSteps={["Verify the platform-issued link", "Correct the Entra directory", "Validate Microsoft sign-in again"]}>
    {busy && !ready ? <div className={styles.status} role="status"><span className={styles.statusIcon}><i aria-hidden="true" /></span><div><h2>Verifying recovery access</h2><p>This single-use link is being checked.</p></div></div> : ready ? <form className={styles.form} onSubmit={repair}><div className={styles.invitationSummary}><span>Permitted action</span><strong>Microsoft SSO configuration only</strong><p>All normal TRANSPIRE data and administration remain blocked.</p></div><div className={styles.field}><label htmlFor="recovery-directory">Correct Microsoft Entra tenant ID</label><input id="recovery-directory" name="directory_id" required pattern="[0-9a-fA-F-]{36}" placeholder="00000000-0000-0000-0000-000000000000" /></div>{error ? <p className={styles.error} role="alert">{error}</p> : null}<button className={styles.submit} type="submit" disabled={busy}><ShieldCheck size={17} />{busy ? "Saving repair" : "Save and require revalidation"}</button></form> : <div className={styles.status} data-tone="error" role="alert"><span className={styles.statusIcon}>!</span><div><h2>Recovery unavailable</h2><p>{error}</p></div></div>}
  </RecoveryShell>;
}
