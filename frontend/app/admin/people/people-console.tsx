"use client";

import { Ban, BellRing, ShieldCheck, CheckCircle2, CircleDot, Clock, Lock, Mail, MailPlus, RefreshCw, UserCheck, UserX, Users, type LucideIcon } from "lucide-react";
import { useTenantRouter as useRouter } from "@/lib/use-tenant-router";
import { FormEvent, useCallback, useEffect, useState } from "react";
import { AdminShell } from "@/components/admin/admin-shell";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { DismissibleNotice } from "@/components/ui/dismissible-notice";
import { SearchField } from "@/components/ui/search-field";
import { SelectField } from "@/components/ui/select-field";
import { StatusPill } from "@/components/ui/workspace";
import { SidePanel } from "@/components/admin/side-panel";
import register from "@/components/admin/admin-register.module.css";
import { apiRequest } from "@/lib/api";
import { useAdminSession } from "@/lib/use-admin-session";
import { roleName, roleNames } from "@/lib/roles";
import styles from "../admin.module.css";

type Member = {
  id: string;
  email: string;
  display_name: string;
  status: string;
  roles: string[];
  can_manage: boolean;
  last_signed_in_at: string | null;
};

type Role = { key: string; name: string; description: string; rank: number; assignable: boolean };
type Invitation = {
  id: string;
  email: string;
  display_name: string;
  role_key: string;
  status: "pending" | "expired" | "revoked";
  expires_at: string;
  last_sent_at: string;
};

type ReminderState = { last_signed_in_at: string | null; cooldown_until: string | null };
type ReminderOverview = { cooldown_hours: number; candidates: (ReminderState & { membership_id: string })[] };
type ReminderResult = { queued: string[]; skipped: { membership_id: string; reason: "cooldown" | "not_eligible" }[] };

const reminderDate = new Intl.DateTimeFormat("en-IN", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" });
const relativeTime = new Intl.RelativeTimeFormat("en", { numeric: "auto" });

function signedInAgo(date: Date) {
  const minutes = Math.round((date.getTime() - Date.now()) / 60_000);
  if (Math.abs(minutes) < 1) return "just now";
  if (Math.abs(minutes) < 60) return relativeTime.format(minutes, "minute");
  const hours = Math.round(minutes / 60);
  if (Math.abs(hours) < 24) return relativeTime.format(hours, "hour");
  const days = Math.round(hours / 24);
  if (Math.abs(days) < 30) return relativeTime.format(days, "day");
  return `on ${new Intl.DateTimeFormat("en-IN", { day: "2-digit", month: "short", year: "numeric" }).format(date)}`;
}

type DirectoryFilter ="all" | "active" | "invited" | "inactive";
const filterOf = (state: string): Exclude<DirectoryFilter, "all"> => state === "active" ? "active" : ["invited", "pending", "expired"].includes(state) ? "invited" : "inactive";

type Tone = "neutral" | "info" | "success" | "warning" | "danger";

const accountStates: Record<string, { label: string; invitationLabel?: string; tone: Tone; Icon: LucideIcon }> = {
  active: { label: "Active", tone: "success", Icon: CheckCircle2 },
  invited: { label: "Invited", tone: "info", Icon: Mail },
  pending: { label: "Pending", invitationLabel: "Invitation pending", tone: "info", Icon: Mail },
  expired: { label: "Expired", invitationLabel: "Invitation expired", tone: "warning", Icon: Clock },
  revoked: { label: "Revoked", invitationLabel: "Invitation revoked", tone: "danger", Icon: Ban },
  inactive: { label: "Inactive", tone: "neutral", Icon: UserX },
  locked: { label: "Locked", tone: "danger", Icon: Lock },
};

function AccountStatus({ state, invitation = false }: { state: string; invitation?: boolean }) {
  const entry = accountStates[state] ?? { label: state.replaceAll("_", " "), tone: "neutral" as const, Icon: CircleDot };
  return <StatusPill tone={entry.tone} icon={<entry.Icon aria-hidden="true" size={14} />}>{invitation ? entry.invitationLabel ?? entry.label : entry.label}</StatusPill>;
}

function initials(name: string, fallback: string) {
  const letters = name.split(/\s+/).filter(Boolean).map((word) => word[0]).join("").slice(0, 2);
  return (letters || fallback.slice(0, 1)).toLocaleUpperCase();
}

type Confirmation = {
  title: string;
  description: string;
  confirmLabel: string;
  busyLabel: string;
  run: () => Promise<void>;
};

export function PeopleConsole() {
  const router = useRouter();
  const { session, loading } = useAdminSession();
  const [inviteOpen, setInviteOpen] = useState(false);
  const [filter, setFilter] = useState<DirectoryFilter>("all");
  const [members, setMembers] = useState<Member[]>([]);
  const [roles, setRoles] = useState<Role[]>([]);
  const [invitations, setInvitations] = useState<Invitation[]>([]);
  const [roleKey, setRoleKey] = useState("idea_submitter");
  const [roleTarget, setRoleTarget] = useState<Member | null>(null);
  const [nextRole, setNextRole] = useState("");
  const [confirmation, setConfirmation] = useState<Confirmation | null>(null);
  const [confirming, setConfirming] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [busyAction, setBusyAction] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [reminders, setReminders] = useState<Record<string, ReminderState>>({});
  const [cooldownHours, setCooldownHours] = useState(0);

  const loadDirectory = useCallback(async () => {
    const [membersResponse, rolesResponse, invitationsResponse, remindersResponse] = await Promise.all([
      apiRequest("/admin/members"),
      apiRequest("/admin/roles"),
      apiRequest("/admin/invitations"),
      apiRequest("/admin/check-in-reminders").catch(() => null),
    ]);
    if (remindersResponse?.ok) {
      const overview = (await remindersResponse.json()) as ReminderOverview;
      setCooldownHours(overview.cooldown_hours);
      setReminders(Object.fromEntries(overview.candidates.map(({ membership_id, ...state }) => [membership_id, state])));
    }
    if (membersResponse.status === 403 || rolesResponse.status === 403) {
      router.replace("/home");
      return;
    }
    if (membersResponse.ok) setMembers((await membersResponse.json()) as Member[]);
    if (rolesResponse.ok) {
      const availableRoles = ((await rolesResponse.json()) as Role[]).sort((a, b) => a.rank - b.rank);
      setRoles(availableRoles);
      const grantable = availableRoles.filter((role) => role.assignable);
      setRoleKey((current) => grantable.some((role) => role.key === current) ? current : grantable.find((role) => role.key === "idea_submitter")?.key ?? grantable[0]?.key ?? "");
    }
    if (invitationsResponse.ok) setInvitations((await invitationsResponse.json()) as Invitation[]);
  }, [router]);

  useEffect(() => {
    if (!session) return;
    const timer = window.setTimeout(() => void loadDirectory(), 0);
    return () => window.clearTimeout(timer);
  }, [loadDirectory, session]);

  const invite = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setSubmitting(true);
    setMessage("");
    setError("");
    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    try {
      const response = await apiRequest("/admin/invitations", {
        method: "POST",
        body: JSON.stringify({
          display_name: String(form.get("display_name") ?? "").trim(),
          email: String(form.get("email") ?? "").trim(),
          role_key: roleKey,
        }),
      });
      if (!response.ok) {
        const payload = (await response.json().catch(() => null)) as { detail?: string } | null;
        setError(payload?.detail ?? "The invitation could not be sent.");
        return;
      }
      formElement.reset();
      setInviteOpen(false);
      setMessage("Invitation queued. The person will appear here after accepting it.");
      await loadDirectory();
    } catch {
      setError("Invitations are temporarily unavailable.");
    } finally {
      setSubmitting(false);
    }
  };

  const invitationAction = async (invitation: Invitation, action: "resend" | "revoke") => {
    setBusyAction(`${action}:${invitation.id}`);
    setError(""); setMessage("");
    try {
      const response = await apiRequest(`/admin/invitations/${invitation.id}${action === "resend" ? "/resend" : ""}`, { method: action === "resend" ? "POST" : "DELETE" });
      if (!response.ok) {
        const payload = (await response.json().catch(() => null)) as { detail?: string } | null;
        setError(payload?.detail ?? `Invitation could not be ${action === "resend" ? "resent" : "revoked"}.`);
      } else {
        setMessage(action === "resend" ? "A fresh invitation was queued and the previous link was revoked." : "Invitation revoked.");
        await loadDirectory();
      }
    } catch {
      setError("Invitation controls are temporarily unavailable.");
    } finally {
      setBusyAction("");
    }
  };

  const memberAction = async (member: Member, status: "active" | "inactive") => {
    setBusyAction(`member:${member.id}`); setError(""); setMessage("");
    try {
      const response = await apiRequest(`/admin/members/${member.id}/status`, { method: "PATCH", body: JSON.stringify({ status }) });
      if (!response.ok) {
        const payload = (await response.json().catch(() => null)) as { detail?: string } | null;
        setError(payload?.detail ?? "Member status could not be changed.");
      } else {
        setMessage(status === "inactive" ? "Member deactivated and sessions revoked." : "Member reactivated.");
        await loadDirectory();
      }
    } catch {
      setError("Member controls are temporarily unavailable.");
    } finally {
      setBusyAction("");
    }
  };

  const openRoleChange = (member: Member) => {
    setRoleTarget(member);
    setNextRole(member.roles[0] ?? "");
  };

  const changeRole = async () => {
    if (!roleTarget || !nextRole) return;
    setBusyAction(`role:${roleTarget.id}`); setError(""); setMessage("");
    try {
      const response = await apiRequest(`/admin/members/${roleTarget.id}/role`, { method: "PATCH", body: JSON.stringify({ role_key: nextRole }) });
      if (!response.ok) {
        const payload = (await response.json().catch(() => null)) as { detail?: string } | null;
        setError(typeof payload?.detail === "string" ? payload.detail : "The role could not be changed.");
        return;
      }
      setMessage(`${roleTarget.display_name} is now a ${roleName(nextRole)}.`);
      setRoleTarget(null);
      await loadDirectory();
    } catch {
      setError("Role controls are temporarily unavailable.");
    } finally {
      setBusyAction("");
    }
  };

  const grantableRoles = roles.filter((role) => role.assignable);

  const remind = async (member: Member) => {
    setBusyAction(`remind:${member.id}`); setError(""); setMessage("");
    try {
      const response = await apiRequest("/admin/check-in-reminders", { method: "POST", body: JSON.stringify({ membership_ids: [member.id] }) });
      if (!response.ok) {
        const payload = (await response.json().catch(() => null)) as { detail?: string } | null;
        setError(typeof payload?.detail === "string" ? payload.detail : "The reminder could not be sent.");
        return;
      }
      const result = (await response.json()) as ReminderResult;
      const skip = result.skipped[0]?.reason;
      if (skip === "cooldown") setError(`${member.display_name} was reminded recently, so no reminder was sent.`);
      else if (skip) setError(`${member.display_name} is no longer an active member.`);
      else setMessage(`Check-in reminder queued for ${member.display_name}.`);
      await loadDirectory();
    } catch {
      setError("Reminders are temporarily unavailable.");
    } finally {
      setBusyAction("");
    }
  };

  const cooldownLabel = cooldownHours % 24 === 0 ? `${cooldownHours / 24} day${cooldownHours === 24 ? "" : "s"}` : `${cooldownHours} hour${cooldownHours === 1 ? "" : "s"}`;

  // Helper text under Access, for every member regardless of status.
  const lastSignedIn = (member: Member) => {
    if (!member.last_signed_in_at) return <small className={styles.lastSignedIn}>Never signed in</small>;
    const signedIn = new Date(member.last_signed_in_at);
    return <small className={styles.lastSignedIn} title={reminderDate.format(signedIn)}>Last signed in {signedInAgo(signedIn)}</small>;
  };

  const reminderButton = (member: Member) => {
    const state = reminders[member.id];
    const coolingUntil = state?.cooldown_until ? new Date(state.cooldown_until) : null;
    const lastSeen = state?.last_signed_in_at ? `Last signed in ${reminderDate.format(new Date(state.last_signed_in_at))}` : "Never signed in";
    const label = coolingUntil
      ? `Reminded recently. ${member.display_name} can be reminded again after ${reminderDate.format(coolingUntil)}.`
      : `Send ${member.display_name} a check-in reminder. ${lastSeen}.`;
    return <button type="button" aria-label={label} title={label} onClick={() => setConfirmation({ title: `Remind ${member.display_name} to check in?`, description: `They will get an email asking them to sign in to ${session?.tenant.name ?? "TRANSPIRE"}. ${lastSeen}.${cooldownHours ? ` They can't be reminded again for ${cooldownLabel}.` : ""}`, confirmLabel: "Send reminder", busyLabel: "Sending", run: () => remind(member) })} disabled={Boolean(busyAction) || Boolean(coolingUntil) || !state}><BellRing aria-hidden="true" size={15} /></button>;
  };

  const confirmAction = async () => {
    if (!confirmation) return;
    setConfirming(true);
    try {
      await confirmation.run();
      setConfirmation(null);
    } finally {
      setConfirming(false);
    }
  };

  const normalizedSearch = searchQuery.trim().toLocaleLowerCase();
  const stateOf = (member: Member) => invitations.find((item) => item.email === member.email)?.status ?? member.status;
  const filterCounts = { all: members.length, active: 0, invited: 0, inactive: 0 };
  members.forEach((member) => { filterCounts[filterOf(stateOf(member))] += 1; });
  const visibleMembers = members.filter((member) => (filter === "all" || filterOf(stateOf(member)) === filter)
    && (!normalizedSearch || [member.display_name, member.email, member.status, ...member.roles].some((value) => value.toLocaleLowerCase().includes(normalizedSearch))));

  if (loading || !session) return <main className={styles.loading}>Loading administration</main>;

  return (
    <AdminShell
      session={session}
      active="people"
      title="People"
      description="Everyone with access to this organisation's workspace, and the invitations still open."
      actions={<button type="button" className={styles.primary} onClick={() => setInviteOpen(true)}><MailPlus aria-hidden="true" size={16} />Invite people</button>}
    >
      {message || error ? <div className={styles.notices}>
        {message ? <DismissibleNotice onDismiss={() => setMessage("")}>{message}</DismissibleNotice> : null}
        {error ? <DismissibleNotice tone="error" onDismiss={() => setError("")}>{error}</DismissibleNotice> : null}
      </div> : null}
      <section className={register.surface} aria-label="Organisation directory">
        <div className={register.toolbar}>
          <SearchField id="people-search" label="Search people" value={searchQuery} onChange={setSearchQuery} placeholder="Search name, email, status, or role" resultCount={visibleMembers.length} />
          <div className={register.segmented} role="group" aria-label="Filter by status">
            {(["all", "active", "invited", "inactive"] as const).map((key) => <button key={key} type="button" aria-pressed={filter === key} onClick={() => setFilter(key)}>{{ all: "All", active: "Active", invited: "Invited", inactive: "Inactive" }[key]}<span>{filterCounts[key]}</span></button>)}
          </div>
        </div>
          {members.length ? (
            <div className={styles.tableWrap}>
              <table className={register.table}>
                <thead><tr><th>Person</th><th>Access</th><th>Status</th><th>Actions</th></tr></thead>
                <tbody>{visibleMembers.map((member) => {
                  const invitation = invitations.find((item) => item.email === member.email);
                  return <tr key={member.id}><td><div className={styles.person}><span className={styles.avatar} aria-hidden="true">{initials(member.display_name, member.email)}</span><span><strong>{member.display_name}</strong><small>{member.email}</small></span></div></td><td><span className={styles.access}>{roleNames(member.roles)}</span>{lastSignedIn(member)}</td><td><AccountStatus state={invitation?.status ?? member.status} invitation={Boolean(invitation)} /></td><td><div className={register.actions}>{!member.can_manage ? <span className={styles.muted}>{member.email === session.user.email ? "You" : "Managed by a Workspace Owner"}</span> : invitation ? <><button type="button" onClick={() => void invitationAction(invitation, "resend")} disabled={Boolean(busyAction)}><RefreshCw aria-hidden="true" size={15} /> Resend</button>{invitation.status !== "revoked" ? <button type="button" data-tone="danger" onClick={() => setConfirmation({ title: "Revoke this invitation?", description: `The invitation for ${invitation.email} will stop working immediately. You can send a new invitation later.`, confirmLabel: "Revoke invitation", busyLabel: "Revoking", run: () => invitationAction(invitation, "revoke") })} disabled={Boolean(busyAction)}><Ban aria-hidden="true" size={15} /> Revoke</button> : null}</> : member.status === "active" ? <>{reminderButton(member)}<button type="button" onClick={() => openRoleChange(member)} disabled={Boolean(busyAction)}><ShieldCheck aria-hidden="true" size={15} /> Change role</button><button type="button" data-tone="danger" onClick={() => setConfirmation({ title: `Deactivate ${member.display_name}?`, description: "Their active sessions will end immediately and they will be unable to sign in until reactivated.", confirmLabel: "Deactivate member", busyLabel: "Deactivating", run: () => memberAction(member, "inactive") })} disabled={Boolean(busyAction)}><UserX aria-hidden="true" size={15} /> Deactivate</button></> : <button type="button" onClick={() => void memberAction(member, "active")} disabled={Boolean(busyAction)}><UserCheck aria-hidden="true" size={15} /> Reactivate</button>}</div></td></tr>;
                })}</tbody>
              </table>
              {visibleMembers.length === 0 ? <p className={styles.noResults}>No people match these filters.</p> : null}
            </div>
          ) : <div className={styles.empty}><Users aria-hidden="true" size={24} /><p>No members are visible in this workspace yet.</p></div>}
      </section>

      <SidePanel open={inviteOpen} onClose={() => setInviteOpen(false)} title="Invite people" description={`They will join ${session.tenant.name}. Choose Contributor for standard access.`}>
          <form className={styles.form} onSubmit={invite}>
            <div className={styles.field}><label htmlFor="invite-name">Full name</label><input id="invite-name" name="display_name" required minLength={2} autoComplete="name" /></div>
            <div className={styles.field}><label htmlFor="invite-email">Work email</label><input id="invite-email" name="email" type="email" required autoComplete="email" /></div>
            <SelectField id="invite-role" name="role_key" label="Access role" value={roleKey} onChange={setRoleKey} disabled={submitting || grantableRoles.length === 0} options={grantableRoles.map((role) => ({ value: role.key, label: role.name, description: role.description }))} />
            <button className={styles.primary} type="submit" disabled={submitting || grantableRoles.length === 0}><MailPlus aria-hidden="true" size={16} /> {submitting ? "Sending" : "Send invitation"}</button>
          </form>
      </SidePanel>
      <SidePanel open={Boolean(roleTarget)} onClose={() => setRoleTarget(null)} title="Change role" description={roleTarget ? `${roleTarget.display_name} is currently a ${roleNames(roleTarget.roles)}. The change takes effect immediately and is recorded in the audit log.` : ""}>
          <div className={styles.form}>
            <SelectField id="change-role" name="role_key" label="New role" value={nextRole} onChange={setNextRole} disabled={Boolean(busyAction)} options={grantableRoles.map((role) => ({ value: role.key, label: role.name, description: role.description }))} />
            <button className={styles.primary} type="button" onClick={() => void changeRole()} disabled={Boolean(busyAction) || !roleTarget || roleTarget.roles.includes(nextRole)}><ShieldCheck aria-hidden="true" size={16} /> {busyAction.startsWith("role:") ? "Saving" : "Save role"}</button>
          </div>
      </SidePanel>
      <ConfirmDialog open={Boolean(confirmation)} title={confirmation?.title ?? "Confirm action"} description={confirmation?.description ?? ""} confirmLabel={confirmation?.confirmLabel ?? "Confirm"} busyLabel={confirmation?.busyLabel} busy={confirming} onClose={() => setConfirmation(null)} onConfirm={confirmAction} />
    </AdminShell>
  );
}
