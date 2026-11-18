"use client";

import { Check, CheckCircle2, Clock, KeyRound, Link2, Save, ShieldCheck, TriangleAlert, Users } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { AdminShell } from "@/components/admin/admin-shell";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { DismissibleNotice } from "@/components/ui/dismissible-notice";
import { SectionCard, StatusPill } from "@/components/ui/workspace";
import { apiRequest, apiUrl } from "@/lib/api";
import { useAdminSession } from "@/lib/use-admin-session";
import { useTenantRouter as useRouter } from "@/lib/use-tenant-router";
import shared from "../admin.module.css";
import styles from "../configuration.module.css";
import register from "@/components/admin/admin-register.module.css";

type SSOMember = { membership_id: string; email: string; display_name: string; status: string; linked: boolean; ready: boolean; reason: string | null };
type SSOConfiguration = { status: "not_configured" | "configured" | "validated" | "active"; entra_directory_id: string | null; client_id_configured: boolean; validated_at: string | null; activated_at: string | null; active_user_count: number; ready_user_count: number; notification_count: number; members: SSOMember[] };
type Confirmation = { title: string; description: string; confirmLabel: string; run: () => Promise<void> };

export function SignInConsole({ returnedFromSSOValidation = false }: { returnedFromSSOValidation?: boolean }) {
  const router = useRouter();
  const { session, loading } = useAdminSession("owner");
  const [loaded, setLoaded] = useState(false);
  const [sso, setSSO] = useState<SSOConfiguration | null>(null);
  const [message, setMessage] = useState(returnedFromSSOValidation ? "Microsoft sign-in was validated with your tenant administrator account." : "");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState("");
  const [confirmation, setConfirmation] = useState<Confirmation | null>(null);
  const flash = (text: string, isError = false) => { setMessage(isError ? "" : text); setError(isError ? text : ""); };
  const confirmAction = async () => {
    if (!confirmation) return;
    await confirmation.run();
    setConfirmation(null);
  };

  const loadConfiguration = useCallback(async () => {
    try {
      const responses = await Promise.all([
        apiRequest("/admin/sso"),
      ]);
      if (responses.some((response) => response.status === 401)) return router.replace("/sign-in");
      if (responses.some((response) => response.status === 403)) return router.replace("/home");
      if (responses[0].ok) setSSO(await responses[0].json() as SSOConfiguration);
      if (responses.some((response) => !response.ok)) setError("Some settings could not be loaded. Retry in a moment.");
    } catch { setError("TRANSPIRE could not reach the configuration service. Check the connection, then retry."); }
    finally { setLoaded(true); }
  }, [router]);

  useEffect(() => {
    if (!session) return;
    const timer = window.setTimeout(() => void loadConfiguration(), 0);
    return () => window.clearTimeout(timer);
  }, [loadConfiguration, session]);

  const saveSSO = async (directoryId: string) => {
    setBusy("sso:save"); flash("");
    try {
      const response = await apiRequest("/admin/sso", { method: "PUT", body: JSON.stringify({ entra_directory_id: directoryId }) });
      const payload = await response.json().catch(() => null) as SSOConfiguration & { detail?: string } | null;
      if (!response.ok) return flash(payload?.detail ?? "Microsoft SSO configuration could not be saved.", true);
      setSSO(payload); flash("Microsoft Entra directory saved. Complete the administrator test next.");
    } catch { flash("Microsoft SSO configuration is temporarily unavailable.", true); }
    finally { setBusy(""); }
  };

  const validateSSO = () => { window.location.assign(apiUrl("/admin/sso/validate")); };

  const activateSSO = async () => {
    setBusy("sso:activate"); flash("");
    try {
      const response = await apiRequest("/admin/sso/activate", { method: "POST" });
      const payload = await response.json().catch(() => null) as SSOConfiguration & { detail?: string } | null;
      if (!response.ok) return flash(payload?.detail ?? "Microsoft SSO could not be activated.", true);
      if (!payload) return flash("Microsoft SSO returned an incomplete activation response.", true);
      setSSO(payload); flash(`Microsoft SSO is now required. ${payload.notification_count} user notifications are queued.`);
    } catch { flash("Microsoft SSO activation is temporarily unavailable.", true); }
    finally { setBusy(""); }
  };

  if (loading || !session) return <main className={shared.loading}>Loading administration</main>;

  return (
    <AdminShell session={session} active="sign_in" title="Microsoft sign-in" description="Move this organisation from passwords to Microsoft sign-in without changing any TRANSPIRE data.">
      {message || error ? <div className={register.notices}>
        {message ? <DismissibleNotice onDismiss={() => setMessage("")}>{message}</DismissibleNotice> : null}
        {error ? <DismissibleNotice tone="error" onDismiss={() => setError("")}>{error}</DismissibleNotice> : null}
      </div> : null}
      {loaded && !sso ? <p className={register.empty}>Microsoft sign-in settings could not be loaded.</p> : <SSOEditor key={sso?.entra_directory_id ?? "new"} configuration={sso} busy={busy} onSave={saveSSO} onValidate={validateSSO} onActivate={() => setConfirmation({ title: "Move this organisation to Microsoft SSO?", description: `Password sign-in will stop for new sessions. ${sso?.active_user_count ?? 0} active users will be notified, while existing sessions and all TRANSPIRE data remain unchanged.`, confirmLabel: "Move to Microsoft SSO", run: activateSSO })} />}
      <ConfirmDialog open={Boolean(confirmation)} title={confirmation?.title ?? "Confirm action"} description={confirmation?.description ?? ""} confirmLabel={confirmation?.confirmLabel ?? "Confirm"} busyLabel="Working" busy={Boolean(busy)} onClose={() => setConfirmation(null)} onConfirm={() => void confirmAction()} />
    </AdminShell>
  );
}

function SSOEditor({ configuration, busy, onSave, onValidate, onActivate }: { configuration: SSOConfiguration | null; busy: string; onSave: (directoryId: string) => Promise<void>; onValidate: () => void; onActivate: () => void }) {
  const [directoryId, setDirectoryId] = useState(configuration?.entra_directory_id ?? "");
  if (!configuration) return <div className={styles.ssoLoading} role="status">Loading Microsoft SSO readiness</div>;
  const ready = configuration.active_user_count > 0 && configuration.active_user_count === configuration.ready_user_count;
  const validated = Boolean(configuration.validated_at);
  const active = configuration.status === "active";
  const readiness = active ? { label: "Active", tone: "success" as const, Icon: CheckCircle2 } : ready && validated ? { label: "Ready", tone: "success" as const, Icon: CheckCircle2 } : { label: "Pending", tone: "warning" as const, Icon: Clock };
  return <div className={styles.ssoLayout}>
    <SectionCard icon={<KeyRound size={17} />} title="Move sign-in without moving user data." description="SSO links Microsoft identities to existing TRANSPIRE users, memberships, roles, ideas, projects, and history." meta="Microsoft Entra ID">
      <ol className={styles.ssoSteps}>
        <SSOStep number={1} complete={Boolean(configuration.entra_directory_id)} title="Connect the directory" detail="Use the Microsoft Entra tenant ID for this organisation." />
        <SSOStep number={2} complete={validated} title="Validate with an administrator" detail="A real Microsoft login must match your current tenant administrator." />
        <SSOStep number={3} complete={active} title="Move to SSO" detail="New sign-ins use Microsoft only. Existing sessions continue normally." />
      </ol>
      <div className={shared.field}><label htmlFor="entra-directory-id">Microsoft Entra tenant ID</label><input id="entra-directory-id" value={directoryId} onChange={(event) => setDirectoryId(event.target.value)} placeholder="00000000-0000-0000-0000-000000000000" disabled={active || busy !== ""} /></div>
      {!configuration.client_id_configured ? <div className={styles.ssoWarning} role="alert"><strong><TriangleAlert aria-hidden="true" size={16} />Platform setup required</strong><span>The Microsoft application credentials must be configured before this directory can be tested.</span></div> : null}
      <div className={styles.ssoActions}>
        <button type="button" onClick={() => void onSave(directoryId)} disabled={active || busy !== "" || !directoryId || !configuration.client_id_configured}><Save size={16} />{busy === "sso:save" ? "Saving" : "Save directory"}</button>
        <button type="button" onClick={onValidate} disabled={active || busy !== "" || !configuration.entra_directory_id}><ShieldCheck size={16} />Test Microsoft sign-in</button>
      </div>
    </SectionCard>
    <SectionCard className={styles.ssoReadiness} icon={<Users size={17} />} title={active ? "Microsoft SSO is active" : `${configuration.ready_user_count} of ${configuration.active_user_count} people ready`} description="Cutover readiness" actions={<StatusPill tone={readiness.tone} icon={<readiness.Icon aria-hidden="true" size={14} />}>{readiness.label}</StatusPill>}>
      <dl><div><dt>Administrator test</dt><dd>{validated ? `Passed ${new Date(configuration.validated_at!).toLocaleString()}` : "Required"}</dd></div><div><dt>Existing sessions</dt><dd>Remain active until normal expiry</dd></div><div><dt>User notifications</dt><dd>{active ? `${configuration.notification_count} queued` : `${configuration.active_user_count} will be queued`}</dd></div></dl>
      <div className={styles.ssoPeople}>{configuration.members.map((member) => <div key={member.membership_id}><span className={styles.ssoPerson}><strong>{member.display_name}</strong><small>{member.email}</small></span>{member.linked ? <StatusPill tone="success" icon={<Link2 aria-hidden="true" size={14} />}>Linked</StatusPill> : member.ready ? <StatusPill tone="success" icon={<CheckCircle2 aria-hidden="true" size={14} />}>Ready</StatusPill> : <StatusPill tone="warning" icon={<TriangleAlert aria-hidden="true" size={14} />}>Action required</StatusPill>}</div>)}</div>
      {!active ? <button className={styles.activateSSO} type="button" onClick={onActivate} disabled={busy !== "" || !ready || !validated}><ShieldCheck size={17} />Move to Microsoft SSO</button> : <p className={styles.activeNote}><CheckCircle2 aria-hidden="true" size={16} />Password sign-in is disabled for this tenant. Platform-controlled recovery remains available for SSO repair.</p>}
    </SectionCard>
  </div>;
}

function SSOStep({ number, complete, title, detail }: { number: number; complete: boolean; title: string; detail: string }) {
  return <li data-complete={complete}><span aria-hidden="true">{complete ? <Check size={15} /> : number}</span><div><strong>{complete ? <span className={shared.srOnly}>Complete: </span> : null}{title}</strong><small>{detail}</small></div></li>;
}
