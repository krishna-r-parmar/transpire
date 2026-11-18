"use client";

import { BellRing, CheckCircle2, CircleSlash, Pencil, Plus, Search, ShieldCheck, UsersRound, X } from "lucide-react";
import { FormEvent, useCallback, useEffect, useState } from "react";
import { AdminShell } from "@/components/admin/admin-shell";
import { SidePanel } from "@/components/admin/side-panel";
import { DismissibleNotice } from "@/components/ui/dismissible-notice";
import { StatusPill } from "@/components/ui/workspace";
import register from "@/components/admin/admin-register.module.css";
import { apiRequest } from "@/lib/api";
import { useAdminSession } from "@/lib/use-admin-session";
import { useTenantRouter as useRouter } from "@/lib/use-tenant-router";
import shared from "../admin.module.css";
import styles from "./groups.module.css";

export type GroupMember = { membership_id: string; display_name: string; email: string; status: "active" | "pending" | "unavailable" };
export type GroupPurpose = "approval" | "notification";
export type ApproverGroup = { id: string; name: string; purpose: GroupPurpose; description: string; is_active: boolean; members: GroupMember[]; used_by_published_workflow: boolean };
type Assignee = { membership_id: string; display_name: string; email: string; status: "active" | "pending" };
type Draft = { id: string | null; name: string; purpose: GroupPurpose; description: string; members: string[]; is_active: boolean };

const emptyDraft: Draft = { id: null, name: "", purpose: "approval", description: "", members: [], is_active: true };

export const purposeLabels: Record<GroupPurpose, { title: string; detail: string }> = {
  approval: { title: "For approval", detail: "Approves fixed workflow steps. Can also be asked for comments." },
  notification: { title: "For notification only", detail: "Emailed when a step starts and asked for comments. Never approves." },
};

async function errorText(response: Response, fallback: string) {
  const payload = await response.json().catch(() => null) as { detail?: string | Array<{ msg: string }> } | null;
  return Array.isArray(payload?.detail) ? payload.detail[0]?.msg ?? fallback : payload?.detail ?? fallback;
}

export function UserGroupsConsole() {
  const router = useRouter();
  const { session, loading } = useAdminSession();
  const [groups, setGroups] = useState<ApproverGroup[]>([]);
  const [results, setResults] = useState<Assignee[]>([]);
  const [searching, setSearching] = useState(false);
  // Names for the chips of everyone currently picked, whichever search found them.
  const [known, setKnown] = useState<Record<string, { display_name: string; email: string }>>({});
  const [loaded, setLoaded] = useState(false);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [search, setSearch] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    try {
      const groupResponse = await apiRequest("/admin/configuration/approver-groups");
      if (groupResponse.status === 403) return router.replace("/home");
      if (groupResponse.ok) setGroups(await groupResponse.json() as ApproverGroup[]);
    } catch {
      setError("Approver groups could not be loaded. Retry in a moment.");
    } finally {
      setLoaded(true);
    }
  }, [router]);

  useEffect(() => {
    if (!session) return;
    const timer = window.setTimeout(() => void load(), 0);
    return () => window.clearTimeout(timer);
  }, [load, session]);

  // Search only: nothing is listed until two characters are typed, and the server returns
  // at most 20 matches, so this stays fast however large the organisation is.
  useEffect(() => {
    const term = search.trim();
    if (term.length < 2) { const reset = window.setTimeout(() => { setResults([]); setSearching(false); }, 0); return () => window.clearTimeout(reset); }
    const timer = window.setTimeout(async () => {
      setSearching(true);
      const response = await apiRequest(`/admin/configuration/workflows/assignees?query=${encodeURIComponent(term)}`).catch(() => null);
      if (response?.ok) setResults(await response.json() as Assignee[]);
      setSearching(false);
    }, 250);
    return () => window.clearTimeout(timer);
  }, [search]);

  const openDraft = (next: Draft, group?: ApproverGroup) => {
    setSearch(""); setResults([]);
    setKnown(Object.fromEntries((group?.members ?? []).filter((member) => member.status !== "unavailable").map((member) => [member.membership_id, { display_name: member.display_name, email: member.email }])));
    setDraft(next);
  };

  const save = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!draft) return;
    setBusy(true); setError(""); setMessage("");
    try {
      const response = await apiRequest(`/admin/configuration/approver-groups${draft.id ? `/${draft.id}` : ""}`, {
        method: draft.id ? "PUT" : "POST",
        body: JSON.stringify({ name: draft.name, purpose: draft.purpose, description: draft.description, member_membership_ids: draft.members, is_active: draft.is_active }),
      });
      if (!response.ok) { setError(await errorText(response, "The group could not be saved.")); return; }
      setMessage(draft.id ? `${draft.name} updated. Pending approvals follow the change at the next routing check.` : draft.purpose === "approval" ? `${draft.name} created. Use it in a fixed step of the approval workflow.` : `${draft.name} created. Choose it under “Also notify for comments” on a workflow step.`);
      setDraft(null);
      await load();
    } catch {
      setError("Approver groups are temporarily unavailable.");
    } finally {
      setBusy(false);
    }
  };

  const addMember = (person: Assignee) => {
    setKnown((current) => ({ ...current, [person.membership_id]: { display_name: person.display_name, email: person.email } }));
    setDraft((current) => current && !current.members.includes(person.membership_id) ? { ...current, members: [...current.members, person.membership_id] } : current);
    setSearch(""); setResults([]);
  };
  const removeMember = (membershipId: string) => setDraft((current) => current && ({ ...current, members: current.members.filter((id) => id !== membershipId) }));

  if (loading || !session) return <main className={shared.loading}>Loading administration</main>;

  return (
    <AdminShell
      session={session}
      active="approver_groups"
      eyebrow="Governance"
      title="User groups"
      description="Named groups of people. Approval groups (such as Finance Head) approve fixed workflow steps; notification groups are emailed and asked for comments. Changing members never needs a new workflow version."
      actions={<button type="button" className={shared.primary} onClick={() => openDraft({ ...emptyDraft })}><Plus aria-hidden="true" size={16} />New group</button>}
    >
      {message || error ? <div className={shared.notices}>
        {message ? <DismissibleNotice onDismiss={() => setMessage("")}>{message}</DismissibleNotice> : null}
        {error ? <DismissibleNotice tone="error" onDismiss={() => setError("")}>{error}</DismissibleNotice> : null}
      </div> : null}
      <section className={register.surface} aria-label="User groups">
        {!loaded ? <p className={styles.empty}>Loading groups</p> : groups.length ? (
          <div className={shared.tableWrap}>
            <table className={register.table}>
              <thead><tr><th>Group</th><th>Purpose</th><th>Members</th><th>Status</th><th><span className={styles.srOnly}>Actions</span></th></tr></thead>
              <tbody>{groups.map((group) => <tr key={group.id} data-inactive={!group.is_active}>
                <td><strong>{group.name}</strong>{group.description ? <small className={styles.description}>{group.description}</small> : null}</td>
                <td>{group.purpose === "approval" ? <StatusPill tone="info" icon={<ShieldCheck aria-hidden="true" size={14} />}>Approval</StatusPill> : <StatusPill icon={<BellRing aria-hidden="true" size={14} />}>Notification</StatusPill>}</td>
                <td><ul className={styles.chips}>{group.members.map((member) => <li key={member.membership_id} data-status={member.status} title={member.email || undefined}>{member.display_name}</li>)}</ul></td>
                <td><div className={styles.badges}>{group.is_active ? <StatusPill tone="success" icon={<CheckCircle2 aria-hidden="true" size={14} />}>Active</StatusPill> : <StatusPill icon={<CircleSlash aria-hidden="true" size={14} />}>Inactive</StatusPill>}{group.used_by_published_workflow ? <StatusPill tone="info">In live workflow</StatusPill> : null}</div></td>
                <td><div className={register.actions}><button type="button" onClick={() => openDraft({ id: group.id, name: group.name, purpose: group.purpose, description: group.description, members: group.members.filter((member) => member.status !== "unavailable").map((member) => member.membership_id), is_active: group.is_active }, group)}><Pencil aria-hidden="true" size={15} /> Edit</button></div></td>
              </tr>)}</tbody>
            </table>
          </div>
        ) : <div className={styles.emptyState}><UsersRound aria-hidden="true" size={26} /><h3>No user groups yet</h3><p>Create approval groups such as OE Head and Finance Head, or notification groups of people who should comment on ideas.</p></div>}
      </section>

      <SidePanel open={Boolean(draft)} onClose={() => setDraft(null)} title={draft?.id ? "Edit user group" : "New user group"} description="Contributors and above can be added. Viewers can neither approve nor comment.">
        {draft ? <form className={shared.form} onSubmit={(event) => void save(event)}>
          <div className={shared.field}><label htmlFor="group-name">Group name</label><input id="group-name" required minLength={2} maxLength={160} value={draft.name} onChange={(event) => setDraft({ ...draft, name: event.target.value })} placeholder="Finance Head" /></div>
          <fieldset className={styles.purpose}>
            <legend>What is this group for?</legend>
            {(Object.keys(purposeLabels) as GroupPurpose[]).map((key) => <label key={key} data-checked={draft.purpose === key}>
              <input type="radio" name="purpose" checked={draft.purpose === key} onChange={() => setDraft({ ...draft, purpose: key })} />
              {key === "approval" ? <ShieldCheck aria-hidden="true" size={17} /> : <BellRing aria-hidden="true" size={17} />}
              <span><strong>{purposeLabels[key].title}</strong><small>{purposeLabels[key].detail}</small></span>
            </label>)}
          </fieldset>
          <div className={shared.field}><label htmlFor="group-description">Description (optional)</label><input id="group-description" maxLength={500} value={draft.description} onChange={(event) => setDraft({ ...draft, description: event.target.value })} placeholder="Signs off the financial case of every idea" /></div>
          <fieldset className={styles.memberPicker}>
            <legend>Members <span>{draft.members.length} selected</span></legend>
            {draft.members.length ? <ul className={styles.picked} aria-label="Selected members">{draft.members.map((id) => <li key={id}>
              <span><strong>{known[id]?.display_name ?? "Selected person"}</strong>{known[id]?.email ? <small>{known[id].email}</small> : null}</span>
              <button type="button" onClick={() => removeMember(id)} aria-label={`Remove ${known[id]?.display_name ?? "person"}`}><X size={14} aria-hidden="true" /></button>
            </li>)}</ul> : null}
            <div className={styles.searchWrap}>
              <label className={styles.search}><Search aria-hidden="true" size={15} /><span className={styles.srOnly}>Add a person</span><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Type a name or email to add someone" autoComplete="off" /></label>
              {search.trim().length >= 2 ? <ul className={styles.results} role="listbox" aria-label="Matching people">
                {results.filter((person) => !draft.members.includes(person.membership_id)).map((person) => <li key={person.membership_id}><button type="button" role="option" aria-selected={false} onClick={() => addMember(person)}>
                  <strong>{person.display_name}</strong><small>{person.email}{person.status === "pending" ? " · invitation pending" : ""}</small>
                </button></li>)}
                {!searching && !results.filter((person) => !draft.members.includes(person.membership_id)).length ? <li className={styles.empty}>No one else matches. Viewers can&apos;t be added.</li> : null}
                {results.length === 20 ? <li className={styles.empty}>Showing the first 20 matches. Keep typing to narrow down.</li> : null}
              </ul> : <p className={styles.hint}>Type at least two letters of a name or email.</p>}
            </div>
          </fieldset>
          {draft.id ? <label className={styles.toggle}><input type="checkbox" checked={draft.is_active} onChange={(event) => setDraft({ ...draft, is_active: event.target.checked })} /> Group is active</label> : null}
          <button className={shared.primary} type="submit" disabled={busy || draft.members.length === 0}>{busy ? "Saving" : draft.id ? "Save group" : "Create group"}</button>
        </form> : null}
      </SidePanel>
    </AdminShell>
  );
}
