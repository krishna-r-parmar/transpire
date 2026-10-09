"use client";

import { BellRing, Camera, Check, FileClock, LogOut, Save, Trash2 } from "lucide-react";
import { useTenantRouter as useRouter } from "@/lib/use-tenant-router";
import { useEffect, useMemo, useState } from "react";
import { AdminShell } from "@/components/admin/admin-shell";
import { AuditLog } from "@/app/audit/audit-workspace";
import { ProfileAvatar } from "@/components/app/profile-avatar";
import { DismissibleNotice } from "@/components/ui/dismissible-notice";
import { SelectField } from "@/components/ui/select-field";
import { apiRequest } from "@/lib/api";
import { useSession } from "@/lib/use-session";
import styles from "./profile.module.css";

type Settings = { email_idea_updates: boolean; email_approval_updates: boolean; compact_lists: boolean; timezone: string };
type Profile = { display_name: string; email: string; tenant_name: string; roles: string[]; settings: Settings; contributions: Array<{ date: string; count: number }>; total_ideas: number; submitted_ideas: number; has_photo: boolean; avatar_updated_at: string | null };

const timezones = [
  { value: "Asia/Kolkata", label: "India", description: "Asia / Kolkata" },
  { value: "UTC", label: "Coordinated Universal Time", description: "UTC" },
  { value: "Europe/London", label: "United Kingdom", description: "Europe / London" },
  { value: "America/New_York", label: "US Eastern", description: "America / New York" },
  { value: "Asia/Singapore", label: "Singapore", description: "Asia / Singapore" },
];

export function ProfileWorkspace() {
  const router = useRouter();
  const { session, loading: sessionLoading } = useSession();
  const [profile, setProfile] = useState<Profile | null>(null);
  const [name, setName] = useState("");
  const [settings, setSettings] = useState<Settings | null>(null);
  const [busy, setBusy] = useState<"" | "save" | "photo" | "signout">("");
  const [notice, setNotice] = useState<{ tone: "success" | "error"; text: string } | null>(null);

  useEffect(() => {
    if (!session) return;
    apiRequest("/profile").then(async (response) => {
      if (!response.ok) throw new Error("Profile could not be loaded.");
      const payload = await response.json() as Profile;
      setProfile(payload); setName(payload.display_name); setSettings(payload.settings);
    }).catch((error: Error) => setNotice({ tone: "error", text: error.message }));
  }, [session]);

  const weeks = useMemo(() => {
    if (!profile) return [];
    const cells = [...profile.contributions];
    const leading = new Date(`${cells[0]?.date}T00:00:00`).getDay();
    return [...Array.from({ length: leading }, () => null), ...cells];
  }, [profile]);

  const save = async (event: React.FormEvent) => {
    event.preventDefault(); if (!settings) return;
    setBusy("save"); setNotice(null);
    try {
      const response = await apiRequest("/profile", { method: "PATCH", body: JSON.stringify({ display_name: name.trim(), settings }) });
      if (!response.ok) throw new Error("Your profile could not be saved. Check the name and try again.");
      const updated = await response.json() as Profile;
      setProfile(updated); setName(updated.display_name); setSettings(updated.settings);
      window.dispatchEvent(new CustomEvent("transpire:profile-updated", { detail: { displayName: updated.display_name } }));
      setNotice({ tone: "success", text: "Profile and preferences saved." });
    } catch (error) { setNotice({ tone: "error", text: error instanceof Error ? error.message : "Profile could not be saved." }); }
    finally { setBusy(""); }
  };

  const signOut = async () => { setBusy("signout"); try { await apiRequest("/auth/logout", { method: "POST" }); } finally { router.replace("/sign-in"); } };

  const uploadPhoto = async (file: File | undefined) => {
    if (!file) return;
    if (!["image/jpeg", "image/png", "image/webp"].includes(file.type) || file.size > 2 * 1024 * 1024) {
      setNotice({ tone: "error", text: "Choose a JPEG, PNG, or WebP image smaller than 2 MB." }); return;
    }
    setBusy("photo"); setNotice(null);
    try {
      const response = await apiRequest("/profile/photo", { method: "PUT", headers: { "Content-Type": file.type }, body: file });
      const body = await response.json().catch(() => null) as { detail?: string; avatar_updated_at?: string } | null;
      if (!response.ok) throw new Error(body?.detail ?? "The profile photo could not be uploaded.");
      setProfile((current) => current ? { ...current, has_photo: true, avatar_updated_at: body?.avatar_updated_at ?? new Date().toISOString() } : current);
      window.dispatchEvent(new Event("transpire:profile-photo-updated"));
      setNotice({ tone: "success", text: "Profile photo updated." });
    } catch (error) { setNotice({ tone: "error", text: error instanceof Error ? error.message : "The profile photo could not be uploaded." }); }
    finally { setBusy(""); }
  };

  const removePhoto = async () => {
    setBusy("photo"); setNotice(null);
    try {
      const response = await apiRequest("/profile/photo", { method: "DELETE" });
      if (!response.ok) throw new Error("The profile photo could not be removed.");
      setProfile((current) => current ? { ...current, has_photo: false, avatar_updated_at: null } : current);
      window.dispatchEvent(new Event("transpire:profile-photo-updated"));
      setNotice({ tone: "success", text: "Profile photo removed." });
    } catch (error) { setNotice({ tone: "error", text: error instanceof Error ? error.message : "The profile photo could not be removed." }); }
    finally { setBusy(""); }
  };

  if (sessionLoading || !session || !profile || !settings) return <main className={styles.loading} aria-busy="true">Preparing your profile…</main>;

  return <AdminShell session={session} active="profile" eyebrow="Personal workspace" title="Your TRANSPIRE profile" description="Keep your identity current, choose how TRANSPIRE communicates with you, and see the improvement habit you are building.">
    {notice ? <DismissibleNotice tone={notice.tone} onDismiss={() => setNotice(null)}>{notice.text}</DismissibleNotice> : null}
    <form className={styles.layout} onSubmit={(event) => void save(event)}>
      <section className={styles.editor}>
        <header className={styles.profileHeader}><ProfileAvatar name={name || profile.display_name} size="large" hasPhoto={profile.has_photo} /><div><p>Profile details</p><h2>How you appear in TRANSPIRE</h2><span>Your photo and name help colleagues recognise you across ideas and approvals.</span><div className={styles.photoActions}><label><Camera size={15} />{profile.has_photo ? "Replace photo" : "Add photo"}<input type="file" accept="image/jpeg,image/png,image/webp" onChange={(event) => { void uploadPhoto(event.target.files?.[0]); event.target.value = ""; }} /></label>{profile.has_photo ? <button type="button" onClick={() => void removePhoto()} disabled={Boolean(busy)}><Trash2 size={15} />Remove</button> : null}</div><small>JPEG, PNG, or WebP. Maximum 2 MB.</small></div></header>
        <label><span>Display name</span><input value={name} minLength={2} maxLength={200} required onChange={(event) => setName(event.target.value)} /></label>
        <div className={styles.readOnly}><span>Email address</span><strong>{profile.email}</strong><small>Managed by your authenticated account.</small></div>
        <div className={styles.identityFacts}><div><span>Organisation</span><strong>{profile.tenant_name}</strong></div><div><span>Access</span><strong>{profile.roles.length ? profile.roles.map(labelRole).join(", ") : "Contributor"}</strong></div></div>
      </section>
      <div className={styles.side}>
        <section className={styles.contribution}>
          <header><div><p>Contribution activity</p><h2>Your improvement rhythm</h2><span>Ideas submitted during the last 365 days.</span></div><div className={styles.totals}><strong>{profile.submitted_ideas}</strong><span>submitted</span><small>{profile.total_ideas} including drafts</small></div></header>
          <div className={styles.graphFrame}><div className={styles.graph} aria-label="Idea contributions over the last year">{weeks.map((day, index) => day ? <span key={day.date} data-level={Math.min(day.count, 4)} title={`${day.date}: ${day.count} ${day.count === 1 ? "idea" : "ideas"}`} aria-label={`${day.date}: ${day.count} ${day.count === 1 ? "idea" : "ideas"}`} /> : <i key={`blank-${index}`} />)}</div></div>
          <div className={styles.legend}><span>Less</span>{[0, 1, 2, 3, 4].map((level) => <i key={level} data-level={level} />)}<span>More</span></div>
          <p className={styles.graphNote}><Check size={15} />Drafts are counted in your total, while the graph records completed submissions.</p>
        </section>
        <section className={styles.preferences}><div><BellRing size={18} /><div><p>Preferences</p><h3>Notifications and workspace</h3></div></div>
          <Preference label="Idea lifecycle emails" description="Receive status and charter updates for ideas you own." value={settings.email_idea_updates} onChange={(value) => setSettings({ ...settings, email_idea_updates: value })} />
          <Preference label="Approval assignment emails" description="Be notified when an approval stage becomes yours." value={settings.email_approval_updates} onChange={(value) => setSettings({ ...settings, email_approval_updates: value })} />
          <Preference label="Compact list density" description="Show more list rows when this preference is supported." value={settings.compact_lists} onChange={(value) => setSettings({ ...settings, compact_lists: value })} />
          <SelectField id="profile-timezone" name="timezone" label="Timezone" value={settings.timezone} options={timezones} onChange={(value) => setSettings({ ...settings, timezone: value })} />
          <div className={styles.actions}><button className={styles.secondary} type="button" onClick={() => void signOut()} disabled={Boolean(busy)}><LogOut size={16} />{busy === "signout" ? "Signing out" : "Sign out"}</button><button className={styles.primary} type="submit" disabled={Boolean(busy) || name.trim().length < 2}><Save size={16} />{busy === "save" ? "Saving" : "Save profile"}</button></div>
        </section>
      </div>
    </form>
    <section className={styles.auditSection} id="audit-log" aria-labelledby="profile-audit-title">
      <header><FileClock size={19} /><div><p>Accountability</p><h2 id="profile-audit-title">Audit log</h2><span>{session.roles.includes("tenant_admin") ? "Review governed activity across this organisation." : "Review events you performed or that affected your submissions."}</span></div></header>
      <AuditLog session={session} embedded />
    </section>
  </AdminShell>;
}

function Preference({ label, description, value, onChange }: { label: string; description: string; value: boolean; onChange: (value: boolean) => void }) {
  return <button className={styles.preference} type="button" aria-pressed={value} onClick={() => onChange(!value)}><span><strong>{label}</strong><small>{description}</small></span><i data-on={value}><b /></i></button>;
}

function labelRole(role: string) { return role.split("_").map((word) => word.charAt(0).toUpperCase() + word.slice(1)).join(" "); }
