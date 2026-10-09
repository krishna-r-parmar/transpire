"use client";

import { Ban, Building2, ChevronDown, CirclePause, Play, Plus, RefreshCw, ShieldAlert, Trash2, UserCheck, UserX, Users } from "lucide-react";
import { useTenantRouter as useRouter } from "@/lib/use-tenant-router";
import { Fragment, FormEvent, useCallback, useEffect, useState } from "react";
import { AdminShell } from "@/components/admin/admin-shell";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { DismissibleNotice } from "@/components/ui/dismissible-notice";
import { SearchField } from "@/components/ui/search-field";
import { apiRequest } from "@/lib/api";
import { useSession } from "@/lib/use-session";
import styles from "../admin.module.css";

type Tenant = {
  id: string;
  slug: string;
  name: string;
  status: "pending" | "active" | "suspended" | "removed";
  created_at: string;
  invitation: {
    id: string;
    email: string;
    display_name: string;
    role_key: string;
    status: "pending" | "expired" | "revoked";
    expires_at: string;
    last_sent_at: string;
  } | null;
};

type TenantMember = {
  id: string;
  email: string;
  display_name: string;
  status: string;
  roles: string[];
};

type Confirmation = {
  title: string;
  description: string;
  confirmLabel: string;
  busyLabel: string;
  confirmationText?: string;
  run: () => Promise<void>;
};

export function TenantConsole() {
  const router = useRouter();
  const { session, loading } = useSession();
  const [tenants, setTenants] = useState<Tenant[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [busyAction, setBusyAction] = useState("");
  const [confirmation, setConfirmation] = useState<Confirmation | null>(null);
  const [confirming, setConfirming] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [expandedTenant, setExpandedTenant] = useState("");
  const [tenantMembers, setTenantMembers] = useState<Record<string, TenantMember[]>>({});
  const [memberSearch, setMemberSearch] = useState<Record<string, string>>({});
  const [loadingMembers, setLoadingMembers] = useState("");
  const [recoveryReference, setRecoveryReference] = useState<Record<string, string>>({});

  const loadTenants = useCallback(async () => {
    const response = await apiRequest("/platform/tenants");
    if (response.status === 403) {
      router.replace("/home");
      return;
    }
    if (response.ok) setTenants((await response.json()) as Tenant[]);
  }, [router]);

  useEffect(() => {
    if (session?.user.is_platform_admin) {
      const timer = window.setTimeout(() => void loadTenants(), 0);
      return () => window.clearTimeout(timer);
    }
    if (session && !session.user.is_platform_admin) router.replace("/home");
  }, [loadTenants, router, session]);

  const createTenant = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setSubmitting(true);
    setMessage("");
    setError("");
    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    try {
      const response = await apiRequest("/platform/tenants", {
        method: "POST",
        body: JSON.stringify({
          name: String(form.get("name") ?? "").trim(),
          slug: String(form.get("slug") ?? "").trim().toLowerCase(),
          first_admin_name: String(form.get("admin_name") ?? "").trim(),
          first_admin_email: String(form.get("admin_email") ?? "").trim(),
        }),
      });
      if (!response.ok) {
        const payload = (await response.json().catch(() => null)) as { detail?: string } | null;
        setError(payload?.detail ?? "Tenant provisioning could not be completed.");
        return;
      }
      formElement.reset();
      setMessage("Tenant created and the first administrator invitation was queued.");
      await loadTenants();
    } catch {
      setError("Tenant provisioning is temporarily unavailable.");
    } finally {
      setSubmitting(false);
    }
  };

  const changeStatus = async (tenantId: string, status: "pending" | "active" | "suspended") => {
    setBusyAction(`status:${tenantId}`);
    setError(""); setMessage("");
    try {
      const response = await apiRequest(`/platform/tenants/${tenantId}/status`, {
        method: "PATCH",
        body: JSON.stringify({ status }),
      });
      if (!response.ok) {
        const payload = (await response.json().catch(() => null)) as { detail?: string } | null;
        setError(payload?.detail ?? "Tenant status could not be changed.");
        return;
      }
      await loadTenants();
      setMessage(status === "active" ? "Tenant activated." : "Tenant suspended. Sign-in is now unavailable for its members.");
    } catch {
      setError("Tenant lifecycle controls are temporarily unavailable.");
    } finally {
      setBusyAction("");
    }
  };

  const invitationAction = async (tenant: Tenant, action: "resend" | "revoke") => {
    if (!tenant.invitation) return;
    setBusyAction(`${action}:${tenant.id}`); setError(""); setMessage("");
    try {
      const response = await apiRequest(`/platform/tenants/${tenant.id}/invitations/${tenant.invitation.id}${action === "resend" ? "/resend" : ""}`, { method: action === "resend" ? "POST" : "DELETE" });
      if (!response.ok) {
        const payload = (await response.json().catch(() => null)) as { detail?: string } | null;
        setError(payload?.detail ?? "Invitation lifecycle action failed.");
      } else {
        setMessage(action === "resend" ? "A fresh administrator invitation was queued." : "Administrator invitation revoked.");
        await loadTenants();
      }
    } catch {
      setError("Invitation controls are temporarily unavailable.");
    } finally {
      setBusyAction("");
    }
  };

  const removeTenant = async (tenant: Tenant) => {
    setBusyAction(`remove:${tenant.id}`); setError(""); setMessage("");
    try {
      const response = await apiRequest(`/platform/tenants/${tenant.id}`, { method: "DELETE" });
      if (!response.ok) {
        const payload = (await response.json().catch(() => null)) as { detail?: string } | null;
        setError(payload?.detail ?? "Tenant could not be removed.");
      } else {
        setMessage("Tenant removed. Its data is retained, but its workspace, sessions, and invitations are disabled.");
        await loadTenants();
      }
    } catch {
      setError("Tenant removal is temporarily unavailable.");
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

  const loadTenantMembers = async (tenantId: string) => {
    setLoadingMembers(tenantId);
    setError("");
    try {
      const response = await apiRequest(`/platform/tenants/${tenantId}/members`);
      if (!response.ok) {
        const payload = (await response.json().catch(() => null)) as { detail?: string } | null;
        setError(payload?.detail ?? "Tenant members could not be loaded.");
        return;
      }
      const members = (await response.json()) as TenantMember[];
      setTenantMembers((current) => ({ ...current, [tenantId]: members }));
    } catch {
      setError("Tenant members are temporarily unavailable.");
    } finally {
      setLoadingMembers("");
    }
  };

  const toggleTenant = async (tenantId: string) => {
    if (expandedTenant === tenantId) {
      setExpandedTenant("");
      return;
    }
    setExpandedTenant(tenantId);
    if (!tenantMembers[tenantId]) await loadTenantMembers(tenantId);
  };

  const memberAction = async (tenant: Tenant, member: TenantMember, status: "active" | "inactive") => {
    setBusyAction(`member:${member.id}`); setError(""); setMessage("");
    try {
      const response = await apiRequest(`/platform/tenants/${tenant.id}/members/${member.id}/status`, { method: "PATCH", body: JSON.stringify({ status }) });
      if (!response.ok) {
        const payload = (await response.json().catch(() => null)) as { detail?: string } | null;
        setError(payload?.detail ?? "Member status could not be changed.");
      } else {
        setMessage(status === "inactive" ? `${member.display_name} was deactivated and signed out.` : `${member.display_name} was reactivated.`);
        await loadTenantMembers(tenant.id);
      }
    } catch {
      setError("Member controls are temporarily unavailable.");
    } finally {
      setBusyAction("");
    }
  };

  const issueSSORecovery = async (tenant: Tenant, member: TenantMember) => {
    const incidentReference = (recoveryReference[tenant.id] ?? "").trim();
    if (!incidentReference) { setError("Enter a support incident reference before issuing recovery."); return; }
    setBusyAction(`recovery:${tenant.id}`); setError(""); setMessage("");
    try {
      const response = await apiRequest(`/platform/tenants/${tenant.id}/sso/recovery`, { method: "POST", body: JSON.stringify({ membership_id: member.id, incident_reference: incidentReference }) });
      if (!response.ok) {
        const payload = await response.json().catch(() => null) as { detail?: string } | null;
        setError(payload?.detail ?? "Restricted SSO recovery could not be issued.");
        return;
      }
      setMessage(`A single-use restricted recovery link was queued for ${member.display_name}.`);
      setRecoveryReference((current) => ({ ...current, [tenant.id]: "" }));
    } catch { setError("SSO recovery controls are temporarily unavailable."); }
    finally { setBusyAction(""); }
  };

  const normalizedSearch = searchQuery.trim().toLocaleLowerCase();
  const visibleTenants = normalizedSearch ? tenants.filter((tenant) => [tenant.name, tenant.slug, tenant.status, tenant.invitation?.email ?? ""].some((value) => value.toLocaleLowerCase().includes(normalizedSearch))) : tenants;

  if (loading || !session) return <main className={styles.loading}>Loading administration</main>;

  return (
    <AdminShell
      session={session}
      active="tenants"
      eyebrow="Super Admin Console"
      title="Tenant control, without tenant data access."
      description="Provision organisational workspaces, manage their lifecycle, and invite the first accountable administrator."
    >
      <div className={styles.workspace}>
        <section className={styles.section} aria-labelledby="create-tenant-title">
          <div className={styles.sectionHeader}>
            <div><h2 id="create-tenant-title">Provision a tenant</h2><p>Creates a shortname-based workspace and queues its first administrator invitation.</p></div>
            <Building2 aria-hidden="true" size={20} />
          </div>
          <form className={`${styles.form} ${styles.tenantForm}`} onSubmit={createTenant}>
            <div className={styles.field}><label htmlFor="tenant-name">Organisation name</label><input id="tenant-name" name="name" required minLength={2} /></div>
            <div className={styles.field}><label htmlFor="tenant-slug">Workspace shortname</label><input id="tenant-slug" name="slug" required pattern="[a-z0-9]+(?:-[a-z0-9]+)*" placeholder="example-industries" /><small>Used in /t/example-industries. It is independent of email domains.</small></div>
            <div className={styles.field}><label htmlFor="tenant-admin-name">First administrator</label><input id="tenant-admin-name" name="admin_name" required /></div>
            <div className={styles.field}><label htmlFor="tenant-admin-email">Administrator email</label><input id="tenant-admin-email" name="admin_email" type="email" required /></div>
            <div className={styles.formActions}><button className={styles.primary} type="submit" disabled={submitting}><Plus aria-hidden="true" size={16} /> {submitting ? "Provisioning" : "Create tenant"}</button></div>
          </form>
        </section>

        <section className={styles.section} aria-labelledby="tenant-list-title">
          <div className={styles.sectionHeader}><div><h2 id="tenant-list-title">Platform tenants</h2><p>{tenants.length} workspace{tenants.length === 1 ? "" : "s"} provisioned</p></div></div>
          {message ? <DismissibleNotice onDismiss={() => setMessage("")}>{message}</DismissibleNotice> : null}
          {error ? <DismissibleNotice tone="error" onDismiss={() => setError("")}>{error}</DismissibleNotice> : null}
          <div className={styles.listTools}><SearchField id="tenant-search" label="Search platform tenants" value={searchQuery} onChange={setSearchQuery} placeholder="Search organisation, shortname, status, or admin" resultCount={visibleTenants.length} /></div>
          {tenants.length ? (
            <div className={styles.tableWrap}>
              <table className={styles.table}>
                <thead><tr><th>Organisation</th><th>Workspace path</th><th>Status</th><th>Administrator invitation</th><th>Actions</th></tr></thead>
                <tbody>{visibleTenants.map((tenant) => {
                  const members = tenantMembers[tenant.id] ?? [];
                  const query = (memberSearch[tenant.id] ?? "").trim().toLocaleLowerCase();
                  const visibleMembers = query ? members.filter((member) => [member.display_name, member.email, member.status, ...member.roles].some((value) => value.toLocaleLowerCase().includes(query))) : members;
                  const isExpanded = expandedTenant === tenant.id;
                  return <Fragment key={tenant.id}>
                    <tr>
                      <td><button className={styles.tenantToggle} type="button" aria-expanded={isExpanded} aria-controls={`tenant-members-${tenant.id}`} onClick={() => void toggleTenant(tenant.id)}><ChevronDown aria-hidden="true" size={16} /><span><strong>{tenant.name}</strong><small>{tenant.slug}</small></span></button></td>
                      <td>/t/{tenant.slug}</td>
                      <td><span className={styles.status} data-state={tenant.status}>{tenant.status}</span></td>
                      <td>{tenant.invitation ? <><strong>{tenant.invitation.display_name}</strong><small>{tenant.invitation.email} · {tenant.invitation.status}</small></> : <small>No open invitation</small>}</td>
                      <td><div className={styles.rowActions}>{tenant.status !== "removed" ? <>{tenant.status === "active" ? <button type="button" onClick={() => setConfirmation({ title: `Suspend ${tenant.name}?`, description: "Members will be signed out and unable to access this workspace until it is activated again.", confirmLabel: "Suspend tenant", busyLabel: "Suspending", run: () => changeStatus(tenant.id, "suspended") })} disabled={Boolean(busyAction)}><CirclePause aria-hidden="true" size={14} /> Suspend</button> : <button type="button" onClick={() => void changeStatus(tenant.id, "active")} disabled={Boolean(busyAction)}><Play aria-hidden="true" size={14} /> Activate</button>}{tenant.invitation ? <><button type="button" onClick={() => void invitationAction(tenant, "resend")} disabled={Boolean(busyAction)}><RefreshCw aria-hidden="true" size={14} /> Resend</button>{tenant.invitation.status !== "revoked" ? <button type="button" data-tone="danger" onClick={() => setConfirmation({ title: "Revoke administrator invitation?", description: `The current invitation for ${tenant.invitation?.email} will stop working immediately.`, confirmLabel: "Revoke invitation", busyLabel: "Revoking", run: () => invitationAction(tenant, "revoke") })} disabled={Boolean(busyAction)}><Ban aria-hidden="true" size={14} /> Revoke</button> : null}</> : null}<button type="button" data-tone="danger" onClick={() => setConfirmation({ title: `Remove ${tenant.name}?`, description: "This disables the workspace, ends active sessions, and revokes open invitations. Organisational records are retained.", confirmLabel: "Remove tenant", busyLabel: "Removing", confirmationText: tenant.name, run: () => removeTenant(tenant) })} disabled={Boolean(busyAction)}><Trash2 aria-hidden="true" size={14} /> Remove</button></> : <small>Access disabled</small>}</div></td>
                    </tr>
                    {isExpanded ? <tr className={styles.accordionRow}><td colSpan={5}><div className={styles.accordionPanel} id={`tenant-members-${tenant.id}`}>
                      <div className={styles.memberHeader}><div><span><Users aria-hidden="true" size={16} /> Member access</span><p>{members.filter((member) => member.status === "active").length} active of {members.length} total</p></div><SearchField id={`member-search-${tenant.id}`} label={`Search members in ${tenant.name}`} value={memberSearch[tenant.id] ?? ""} onChange={(value) => setMemberSearch((current) => ({ ...current, [tenant.id]: value }))} placeholder="Search member, role, or status" resultCount={visibleMembers.length} /></div>
                      {loadingMembers === tenant.id ? <div className={styles.memberLoading}><span /><span /><span /></div> : members.length ? <div className={styles.memberList}>{visibleMembers.map((member) => <div className={styles.memberRow} key={member.id}><div><strong>{member.display_name}</strong><small>{member.email}</small></div><span className={styles.status} data-state={member.status}>{member.status}</span><p>{member.roles.map((role) => role === "idea_submitter" ? "Employee / Idea Submitter" : role.replaceAll("_", " ")).join(", ") || "No role assigned"}</p><div className={styles.rowActions}>{member.status === "active" ? <button type="button" data-tone="danger" disabled={Boolean(busyAction)} onClick={() => setConfirmation({ title: `Deactivate ${member.display_name}?`, description: `Their access to ${tenant.name} will stop immediately and active sessions will end.`, confirmLabel: "Deactivate member", busyLabel: "Deactivating", run: () => memberAction(tenant, member, "inactive") })}><UserX aria-hidden="true" size={14} /> Deactivate</button> : member.status === "inactive" ? <button type="button" disabled={Boolean(busyAction) || tenant.status !== "active"} onClick={() => void memberAction(tenant, member, "active")}><UserCheck aria-hidden="true" size={14} /> Reactivate</button> : <small>Awaiting acceptance</small>}</div></div>)}</div> : <p className={styles.noResults}>No members have joined this tenant yet.</p>}
                      {members.length > 0 && visibleMembers.length === 0 && loadingMembers !== tenant.id ? <p className={styles.noResults}>No members match this search.</p> : null}
                      {members.some((member) => member.status === "active" && member.roles.includes("tenant_admin")) ? <div className={styles.recoveryControl}><div><span><ShieldAlert aria-hidden="true" size={16} /> Restricted SSO recovery</span><p>Creates a single-use, short-lived session that can repair Microsoft sign-in only.</p></div><div className={styles.field}><label htmlFor={`incident-${tenant.id}`}>Support incident reference</label><input id={`incident-${tenant.id}`} value={recoveryReference[tenant.id] ?? ""} onChange={(event) => setRecoveryReference((current) => ({ ...current, [tenant.id]: event.target.value }))} placeholder="INC-2041" /></div><div className={styles.rowActions}>{members.filter((member) => member.status === "active" && member.roles.includes("tenant_admin")).map((member) => <button type="button" key={member.id} disabled={Boolean(busyAction) || !(recoveryReference[tenant.id] ?? "").trim()} onClick={() => setConfirmation({ title: `Issue restricted recovery to ${member.display_name}?`, description: `The link will allow SSO configuration repair for ${tenant.name} only. Reference: ${recoveryReference[tenant.id]}.`, confirmLabel: "Issue recovery", busyLabel: "Issuing", run: () => issueSSORecovery(tenant, member) })}><ShieldAlert aria-hidden="true" size={14} /> Recover via {member.display_name}</button>)}</div></div> : null}
                    </div></td></tr> : null}
                  </Fragment>;
                })}</tbody>
              </table>
              {visibleTenants.length === 0 ? <p className={styles.noResults}>No tenants match “{searchQuery}”. Try an organisation, shortname, status, or administrator email.</p> : null}
            </div>
          ) : <p className={styles.empty}>No tenants have been provisioned yet.</p>}
        </section>
      </div>
      <ConfirmDialog open={Boolean(confirmation)} title={confirmation?.title ?? "Confirm action"} description={confirmation?.description ?? ""} confirmLabel={confirmation?.confirmLabel ?? "Confirm"} busyLabel={confirmation?.busyLabel} confirmationText={confirmation?.confirmationText} busy={confirming} onClose={() => setConfirmation(null)} onConfirm={confirmAction} />
    </AdminShell>
  );
}
