"use client";

import { Ban, MailPlus, RefreshCw, UserCheck, UserX, Users } from "lucide-react";
import { useTenantRouter as useRouter } from "@/lib/use-tenant-router";
import { FormEvent, useCallback, useEffect, useState } from "react";
import { AdminShell } from "@/components/admin/admin-shell";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { DismissibleNotice } from "@/components/ui/dismissible-notice";
import { SearchField } from "@/components/ui/search-field";
import { SelectField } from "@/components/ui/select-field";
import { apiRequest } from "@/lib/api";
import { useSession } from "@/lib/use-session";
import styles from "../admin.module.css";

type Member = {
  id: string;
  email: string;
  display_name: string;
  status: string;
  roles: string[];
};

type Role = { key: string; name: string };
type Invitation = {
  id: string;
  email: string;
  display_name: string;
  role_key: string;
  status: "pending" | "expired" | "revoked";
  expires_at: string;
  last_sent_at: string;
};

type Confirmation = {
  title: string;
  description: string;
  confirmLabel: string;
  busyLabel: string;
  run: () => Promise<void>;
};

export function PeopleConsole() {
  const router = useRouter();
  const { session, loading } = useSession();
  const [members, setMembers] = useState<Member[]>([]);
  const [roles, setRoles] = useState<Role[]>([]);
  const [invitations, setInvitations] = useState<Invitation[]>([]);
  const [roleKey, setRoleKey] = useState("idea_submitter");
  const [confirmation, setConfirmation] = useState<Confirmation | null>(null);
  const [confirming, setConfirming] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [busyAction, setBusyAction] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  const loadDirectory = useCallback(async () => {
    const [membersResponse, rolesResponse, invitationsResponse] = await Promise.all([
      apiRequest("/admin/members"),
      apiRequest("/admin/roles"),
      apiRequest("/admin/invitations"),
    ]);
    if (membersResponse.status === 403 || rolesResponse.status === 403) {
      router.replace("/home");
      return;
    }
    if (membersResponse.ok) setMembers((await membersResponse.json()) as Member[]);
    if (rolesResponse.ok) {
      const availableRoles = (await rolesResponse.json()) as Role[];
      setRoles(availableRoles);
      setRoleKey((current) => availableRoles.some((role) => role.key === current) ? current : availableRoles[0]?.key ?? "");
    }
    if (invitationsResponse.ok) setInvitations((await invitationsResponse.json()) as Invitation[]);
  }, [router]);

  useEffect(() => {
    if (session?.roles.includes("tenant_admin")) {
      const timer = window.setTimeout(() => void loadDirectory(), 0);
      return () => window.clearTimeout(timer);
    }
    if (session && !session.roles.includes("tenant_admin")) router.replace("/home");
  }, [loadDirectory, router, session]);

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
  const visibleMembers = normalizedSearch ? members.filter((member) => [member.display_name, member.email, member.status, ...member.roles].some((value) => value.toLocaleLowerCase().includes(normalizedSearch))) : members;

  if (loading || !session) return <main className={styles.loading}>Loading administration</main>;

  return (
    <AdminShell
      session={session}
      active="people"
      eyebrow="Admin Console"
      title="Build the community behind improvement."
      description="Invite colleagues, assign the right starting access, and keep your organisational directory visible."
    >
      <div className={styles.workspace}>
        <section className={styles.section} aria-labelledby="invite-person-title">
          <div className={styles.sectionHeader}>
            <div><h2 id="invite-person-title">Invite a person</h2><p>They will join {session.tenant.name}. Choose Employee / Idea Submitter for standard access.</p></div>
            <MailPlus aria-hidden="true" size={20} />
          </div>
          <form className={`${styles.form} ${styles.inviteForm}`} onSubmit={invite}>
            <div className={styles.field}><label htmlFor="invite-name">Full name</label><input id="invite-name" name="display_name" required minLength={2} autoComplete="name" /></div>
            <div className={styles.field}><label htmlFor="invite-email">Work email</label><input id="invite-email" name="email" type="email" required autoComplete="email" /></div>
            <SelectField id="invite-role" name="role_key" label="Access role" value={roleKey} onChange={setRoleKey} disabled={submitting || roles.length === 0} options={roles.map((role) => ({ value: role.key, label: role.key === "idea_submitter" ? "Employee / Idea Submitter" : role.name, description: role.key === "tenant_admin" ? "Manage people and workspace settings" : "Standard access to submit and follow ideas" }))} />
            <button className={styles.primary} type="submit" disabled={submitting || roles.length === 0}><MailPlus aria-hidden="true" size={16} /> {submitting ? "Sending" : "Send invitation"}</button>
          </form>
          {message ? <DismissibleNotice onDismiss={() => setMessage("")}>{message}</DismissibleNotice> : null}
          {error ? <DismissibleNotice tone="error" onDismiss={() => setError("")}>{error}</DismissibleNotice> : null}
        </section>

        <section className={styles.section} aria-labelledby="directory-title">
          <div className={styles.sectionHeader}><div><h2 id="directory-title">Organisation directory</h2><p>{members.length} active or invited member{members.length === 1 ? "" : "s"}</p></div><Users aria-hidden="true" size={20} /></div>
          <div className={styles.listTools}><SearchField id="people-search" label="Search organisation directory" value={searchQuery} onChange={setSearchQuery} placeholder="Search name, email, status, or role" resultCount={visibleMembers.length} /></div>
          {members.length ? (
            <div className={styles.tableWrap}>
              <table className={styles.table}>
                <thead><tr><th>Person</th><th>Status</th><th>Access</th><th>Actions</th></tr></thead>
                <tbody>{visibleMembers.map((member) => {
                  const invitation = invitations.find((item) => item.email === member.email);
                  return <tr key={member.id}><td><strong>{member.display_name}</strong><small>{member.email}</small></td><td><span className={styles.status} data-state={invitation?.status ?? member.status}>{invitation?.status ?? member.status}</span></td><td>{member.roles.map((role) => role.replaceAll("_", " ")).join(", ") || "No role assigned"}</td><td><div className={styles.rowActions}>{invitation ? <><button type="button" onClick={() => void invitationAction(invitation, "resend")} disabled={Boolean(busyAction)}><RefreshCw aria-hidden="true" size={14} /> Resend</button>{invitation.status !== "revoked" ? <button type="button" data-tone="danger" onClick={() => setConfirmation({ title: "Revoke this invitation?", description: `The invitation for ${invitation.email} will stop working immediately. You can send a new invitation later.`, confirmLabel: "Revoke invitation", busyLabel: "Revoking", run: () => invitationAction(invitation, "revoke") })} disabled={Boolean(busyAction)}><Ban aria-hidden="true" size={14} /> Revoke</button> : null}</> : member.status === "active" ? <button type="button" data-tone="danger" onClick={() => setConfirmation({ title: `Deactivate ${member.display_name}?`, description: "Their active sessions will end immediately and they will be unable to sign in until reactivated.", confirmLabel: "Deactivate member", busyLabel: "Deactivating", run: () => memberAction(member, "inactive") })} disabled={Boolean(busyAction)}><UserX aria-hidden="true" size={14} /> Deactivate</button> : <button type="button" onClick={() => void memberAction(member, "active")} disabled={Boolean(busyAction)}><UserCheck aria-hidden="true" size={14} /> Reactivate</button>}</div></td></tr>;
                })}</tbody>
              </table>
              {visibleMembers.length === 0 ? <p className={styles.noResults}>No people match “{searchQuery}”. Try a name, email, role, or status.</p> : null}
            </div>
          ) : <p className={styles.empty}>No members are visible in this workspace yet.</p>}
        </section>
      </div>
      <ConfirmDialog open={Boolean(confirmation)} title={confirmation?.title ?? "Confirm action"} description={confirmation?.description ?? ""} confirmLabel={confirmation?.confirmLabel ?? "Confirm"} busyLabel={confirmation?.busyLabel} busy={confirming} onClose={() => setConfirmation(null)} onConfirm={confirmAction} />
    </AdminShell>
  );
}
