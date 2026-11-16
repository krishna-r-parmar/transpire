"use client";

import { Eye, Save } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { AdminShell } from "@/components/admin/admin-shell";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { DismissibleNotice } from "@/components/ui/dismissible-notice";
import { SectionCard } from "@/components/ui/workspace";
import { apiRequest } from "@/lib/api";
import { useAdminSession } from "@/lib/use-admin-session";
import { useTenantRouter as useRouter } from "@/lib/use-tenant-router";
import shared from "../admin.module.css";
import styles from "../configuration.module.css";
import register from "@/components/admin/admin-register.module.css";

type IdeaBankPolicy = { detail_level: "headline" | "operational" | "full"; show_contributor: boolean; show_financials: boolean };
type Confirmation = { title: string; description: string; confirmLabel: string; run: () => Promise<void> };

export function IdeaBankPolicyConsole() {
  const router = useRouter();
  const { session, loading } = useAdminSession();
  const [loaded, setLoaded] = useState(false);
  const [ideaBankPolicy, setIdeaBankPolicy] = useState<IdeaBankPolicy>({ detail_level: "operational", show_contributor: true, show_financials: false });
  const [message, setMessage] = useState("");
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
        apiRequest("/admin/configuration/idea-bank-policy"),
      ]);
      if (responses.some((response) => response.status === 401)) return router.replace("/sign-in");
      if (responses.some((response) => response.status === 403)) return router.replace("/home");
      if (responses[0].ok) setIdeaBankPolicy(await responses[0].json() as IdeaBankPolicy);
      if (responses.some((response) => !response.ok)) setError("Some settings could not be loaded. Retry in a moment.");
    } catch { setError("TRANSPIRE could not reach the configuration service. Check the connection, then retry."); }
    finally { setLoaded(true); }
  }, [router]);

  useEffect(() => {
    if (!session) return;
    const timer = window.setTimeout(() => void loadConfiguration(), 0);
    return () => window.clearTimeout(timer);
  }, [loadConfiguration, session]);

  const saveIdeaBankPolicy = async () => {
    setBusy("policy"); flash("");
    try {
      const response = await apiRequest("/admin/configuration/idea-bank-policy", { method: "PUT", body: JSON.stringify(ideaBankPolicy) });
      if (!response.ok) { const payload = await response.json().catch(() => null) as { detail?: string } | null; return flash(payload?.detail ?? "The Idea Bank policy could not be saved.", true); }
      setIdeaBankPolicy(await response.json() as IdeaBankPolicy); flash("Idea Bank visibility policy saved.");
    } catch { flash("The visibility service is temporarily unavailable.", true); }
    finally { setBusy(""); }
  };

  if (loading || !session) return <main className={shared.loading}>Loading administration</main>;

  return (
    <AdminShell session={session} active="idea_bank_policy" title="Idea Bank visibility" description="How much of each idea people outside its approval route can see in the Idea Bank.">
      {message || error ? <div className={register.notices}>
        {message ? <DismissibleNotice onDismiss={() => setMessage("")}>{message}</DismissibleNotice> : null}
        {error ? <DismissibleNotice tone="error" onDismiss={() => setError("")}>{error}</DismissibleNotice> : null}
      </div> : null}
      {loaded ? <IdeaBankPolicyEditor policy={ideaBankPolicy} onChange={setIdeaBankPolicy} onSave={() => void saveIdeaBankPolicy()} busy={busy === "policy"} /> : <p className={register.empty}>Loading visibility policy</p>}
      <ConfirmDialog open={Boolean(confirmation)} title={confirmation?.title ?? "Confirm action"} description={confirmation?.description ?? ""} confirmLabel={confirmation?.confirmLabel ?? "Confirm"} busyLabel="Working" busy={Boolean(busy)} onClose={() => setConfirmation(null)} onConfirm={() => void confirmAction()} />
    </AdminShell>
  );
}

function IdeaBankPolicyEditor({ policy, onChange, onSave, busy }: { policy: IdeaBankPolicy; onChange: (policy: IdeaBankPolicy) => void; onSave: () => void; busy: boolean }) {
  const levels: Array<{ value: IdeaBankPolicy["detail_level"]; label: string; description: string }> = [
    { value: "headline", label: "Headline", description: "Reference, title, type, category, and submission date." },
    { value: "operational", label: "Operational", description: "Adds subcategory, process area, SQDCP, baseline, and target." },
    { value: "full", label: "Full context", description: "Also shares the problem statement and business case." },
  ];
  return <SectionCard className={styles.policy} icon={<Eye size={17} />} title="Decide what the Idea Bank reveals." description="The backend applies this policy before idea data leaves the tenant boundary." meta="Tenant sharing policy"><fieldset><legend>Detail level</legend><div className={styles.choices}>{levels.map((level) => <button key={level.value} type="button" aria-pressed={policy.detail_level === level.value} onClick={() => onChange({ ...policy, detail_level: level.value })}><span><strong>{level.label}</strong><small>{level.description}</small></span>{policy.detail_level === level.value ? <span className={styles.selected}><CheckMark /></span> : null}</button>)}</div></fieldset><div className={styles.policyToggles}><button type="button" aria-pressed={policy.show_contributor} onClick={() => onChange({ ...policy, show_contributor: !policy.show_contributor })}><span><strong>Show contributor name</strong><small>Turn off to share ideas anonymously.</small></span><span className={styles.switch}><em aria-hidden="true">{policy.show_contributor ? "On" : "Off"}</em><i data-on={policy.show_contributor}><b /></i></span></button><button type="button" aria-pressed={policy.show_financials} onClick={() => onChange({ ...policy, show_financials: !policy.show_financials })}><span><strong>Show financial estimates</strong><small>Annual saving, cost avoidance, and investment.</small></span><span className={styles.switch}><em aria-hidden="true">{policy.show_financials ? "On" : "Off"}</em><i data-on={policy.show_financials}><b /></i></span></button></div><button className={styles.policySave} type="button" onClick={onSave} disabled={busy}><Save size={16} />{busy ? "Saving policy" : "Save visibility policy"}</button></SectionCard>;
}

function CheckMark() { return <span aria-hidden="true">✓</span>; }
