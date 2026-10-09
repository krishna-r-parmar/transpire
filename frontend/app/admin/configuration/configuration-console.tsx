"use client";

import { Building2, Eye, GitBranch, Layers3, Pencil, Plus, Power, Rocket, Save, ShieldCheck, Trash2 } from "lucide-react";
import { useTenantRouter as useRouter } from "@/lib/use-tenant-router";
import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { AdminShell } from "@/components/admin/admin-shell";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { DismissibleNotice } from "@/components/ui/dismissible-notice";
import { SearchField } from "@/components/ui/search-field";
import { SearchableSelectField } from "@/components/ui/searchable-select-field";
import { SelectField } from "@/components/ui/select-field";
import { apiRequest, apiUrl } from "@/lib/api";
import { useSession } from "@/lib/use-session";
import shared from "../admin.module.css";
import styles from "./configuration.module.css";

type Kind = "site" | "department" | "category" | "subcategory" | "process_area";
type Item = { id: string; kind: Kind; code: string; name: string; parent_id: string | null; site_ids: string[]; applies_to_all_sites: boolean; is_active: boolean; sort_order: number };
type Stage = { key: string; name: string; approver_role: string; assignee_membership_id: string | null; assignee_name: string | null; assignee_email: string | null; assignee_status: "active" | "pending" | null; sla_hours: number; required: boolean };
type WorkflowAssignee = { membership_id: string; display_name: string; email: string; status: "active" | "pending" };
type Version = { id: string; version: number; status: "draft" | "published" | "retired"; stages: Stage[]; published_at: string | null; created_at: string };
type Workflow = { id: string; key: string; name: string; description: string; is_active: boolean; versions: Version[] };
type Tab = "organisation" | "classification" | "workflow" | "idea_bank" | "authentication";
type IdeaBankPolicy = { detail_level: "headline" | "operational" | "full"; show_contributor: boolean; show_financials: boolean };
type SSOMember = { membership_id: string; email: string; display_name: string; status: string; linked: boolean; ready: boolean; reason: string | null };
type SSOConfiguration = { status: "not_configured" | "configured" | "validated" | "active"; entra_directory_id: string | null; client_id_configured: boolean; validated_at: string | null; activated_at: string | null; active_user_count: number; ready_user_count: number; notification_count: number; members: SSOMember[] };
type Confirmation = { title: string; description: string; confirmLabel: string; run: () => Promise<void> };

const labels: Record<Kind, { singular: string; plural: string; parent?: Kind }> = {
  site: { singular: "Site", plural: "Sites" },
  department: { singular: "Department", plural: "Departments" },
  category: { singular: "Category", plural: "Categories" },
  subcategory: { singular: "Subcategory", plural: "Subcategories", parent: "category" },
  process_area: { singular: "Process area", plural: "Process areas" },
};

const emptyStage = (): Stage => ({ key: "", name: "", approver_role: "assigned_member", assignee_membership_id: "", assignee_name: null, assignee_email: null, assignee_status: null, sla_hours: 48, required: true });
const slugify = (value: string) => value.toLocaleLowerCase().trim().replace(/[^a-z0-9]+/g, "_").replace(/^_|_$/g, "");

export function ConfigurationConsole({ returnedFromSSOValidation = false }: { returnedFromSSOValidation?: boolean }) {
  const router = useRouter();
  const { session, loading } = useSession();
  const [tab, setTab] = useState<Tab>(returnedFromSSOValidation ? "authentication" : "organisation");
  const [items, setItems] = useState<Record<Kind, Item[]>>({ site: [], department: [], category: [], subcategory: [], process_area: [] });
  const [workflows, setWorkflows] = useState<Workflow[]>([]);
  const [workflowAssignees, setWorkflowAssignees] = useState<WorkflowAssignee[]>([]);
  const [ideaBankPolicy, setIdeaBankPolicy] = useState<IdeaBankPolicy>({ detail_level: "operational", show_contributor: true, show_financials: false });
  const [sso, setSSO] = useState<SSOConfiguration | null>(null);
  const [stages, setStages] = useState<Stage[]>([emptyStage()]);
  const [sourceVersion, setSourceVersion] = useState<number | null>(null);
  const [search, setSearch] = useState<Record<Kind, string>>({ site: "", department: "", category: "", subcategory: "", process_area: "" });
  const [message, setMessage] = useState(returnedFromSSOValidation ? "Microsoft sign-in was validated with your tenant administrator account." : "");
  const [error, setError] = useState("");
  const [loadError, setLoadError] = useState("");
  const [loadingData, setLoadingData] = useState(true);
  const [busy, setBusy] = useState("");
  const [confirmation, setConfirmation] = useState<Confirmation | null>(null);

  const loadConfiguration = useCallback(async () => {
    const kinds: Kind[] = ["site", "department", "category", "subcategory", "process_area"];
    setLoadingData(true);
    try {
      const responses = await Promise.all([
        ...kinds.map((kind) => apiRequest(`/admin/configuration/master-data/${kind}`)),
        apiRequest("/admin/configuration/workflows/contracts"),
        apiRequest("/admin/configuration/idea-bank-policy"),
        apiRequest("/admin/configuration/workflows/assignees"),
        apiRequest("/admin/sso"),
      ]);
      if (responses.some((response) => response.status === 403)) return router.replace("/home");
      if (responses.some((response) => response.status === 401)) return router.replace("/sign-in");
      const loaded = { site: [], department: [], category: [], subcategory: [], process_area: [] } as Record<Kind, Item[]>;
      await Promise.all(kinds.map(async (kind, index) => { if (responses[index].ok) loaded[kind] = await responses[index].json() as Item[]; }));
      setItems(loaded);
      if (responses[5].ok) setWorkflows(await responses[5].json() as Workflow[]);
      if (responses[6].ok) setIdeaBankPolicy(await responses[6].json() as IdeaBankPolicy);
      if (responses[7].ok) setWorkflowAssignees(await responses[7].json() as WorkflowAssignee[]);
      if (responses[8].ok) setSSO(await responses[8].json() as SSOConfiguration);
      if (responses.some((response) => !response.ok)) setLoadError("Some configuration records could not be loaded. Retry after confirming the backend is up to date.");
      else setLoadError("");
    } catch {
      setLoadError("TRANSPIRE could not reach the configuration service. Check that the backend is running, then retry.");
    } finally {
      setLoadingData(false);
    }
  }, [router]);

  useEffect(() => {
    if (session?.roles.includes("tenant_admin")) {
      const timer = window.setTimeout(() => void loadConfiguration(), 0);
      return () => window.clearTimeout(timer);
    }
    else if (session) router.replace("/home");
  }, [loadConfiguration, router, session]);

  const flash = (text: string, isError = false) => { setMessage(isError ? "" : text); setError(isError ? text : ""); };

  const createItem = async (kind: Kind, event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(form);
    setBusy(`create:${kind}`); flash("");
    try {
      const response = await apiRequest(`/admin/configuration/master-data/${kind}`, { method: "POST", body: JSON.stringify({ name: data.get("name"), code: data.get("code"), parent_id: data.get("parent_id") || null, site_ids: data.getAll("site_ids"), applies_to_all_sites: data.get("applies_to_all_sites") === "true" }) });
      if (!response.ok) { const payload = await response.json().catch(() => null) as { detail?: string } | null; return flash(payload?.detail ?? `${labels[kind].singular} could not be created.`, true); }
      form.reset(); flash(`${labels[kind].singular} added.`); await loadConfiguration();
    } catch { flash("Configuration is temporarily unavailable.", true); }
    finally { setBusy(""); }
  };

  const toggleItem = async (item: Item) => {
    setBusy(`toggle:${item.id}`); flash("");
    try {
      const response = await apiRequest(`/admin/configuration/master-data/${item.kind}/${item.id}`, { method: "PATCH", body: JSON.stringify({ is_active: !item.is_active }) });
      if (!response.ok) { const payload = await response.json().catch(() => null) as { detail?: string } | null; return flash(payload?.detail ?? "Status could not be changed.", true); }
      flash(`${labels[item.kind].singular} ${item.is_active ? "deactivated" : "reactivated"}.`); await loadConfiguration();
    } catch {
      flash("Configuration is temporarily unavailable.", true);
    } finally { setBusy(""); }
  };

  const createVersion = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const workflow = workflows[0];
    if (!workflow) return;
    setBusy("draft"); flash("");
    try {
      const response = await apiRequest(`/admin/configuration/workflows/${workflow.id}/versions`, { method: "POST", body: JSON.stringify({ stages: stages.map(({ key, name, assignee_membership_id, sla_hours, required }) => ({ key, name, assignee_membership_id, sla_hours, required })) }) });
      if (!response.ok) { const payload = await response.json().catch(() => null) as { detail?: string | Array<{ msg: string }> } | null; const detail = Array.isArray(payload?.detail) ? payload.detail[0]?.msg : payload?.detail; return flash(detail ?? "Draft version could not be created.", true); }
      setStages([emptyStage()]); setSourceVersion(null); flash("Draft workflow version created. Review it before publishing."); await loadConfiguration();
    } catch {
      flash("Workflow configuration is temporarily unavailable.", true);
    } finally { setBusy(""); }
  };

  const publishVersion = async (workflow: Workflow, version: Version) => {
    setBusy(`publish:${version.id}`); flash("");
    try {
      const response = await apiRequest(`/admin/configuration/workflows/${workflow.id}/versions/${version.id}/publish`, { method: "POST" });
      if (!response.ok) { const payload = await response.json().catch(() => null) as { detail?: string } | null; return flash(payload?.detail ?? "Version could not be published.", true); }
      flash(`Version ${version.version} is now the approval contract.`); await loadConfiguration();
    } catch {
      flash("Workflow publishing is temporarily unavailable.", true);
    } finally { setBusy(""); }
  };

  const confirmAction = async () => {
    if (!confirmation) return;
    await confirmation.run();
    setConfirmation(null);
  };

  const editPublishedVersion = (version: Version) => {
    setStages(version.stages.map((stage) => ({ ...stage })));
    setSourceVersion(version.version);
    window.requestAnimationFrame(() => document.getElementById("workflow-builder")?.scrollIntoView({ behavior: "smooth", block: "start" }));
    flash(`Version ${version.version} copied into the builder. Saving creates a new draft version.`);
  };

  const saveIdeaBankPolicy = async () => {
    setBusy("policy"); flash("");
    try {
      const response = await apiRequest("/admin/configuration/idea-bank-policy", { method: "PUT", body: JSON.stringify(ideaBankPolicy) });
      if (!response.ok) { const payload = await response.json().catch(() => null) as { detail?: string } | null; return flash(payload?.detail ?? "The Idea Bank policy could not be saved.", true); }
      setIdeaBankPolicy(await response.json() as IdeaBankPolicy); flash("Idea Bank visibility policy saved.");
    } catch { flash("The visibility service is temporarily unavailable.", true); }
    finally { setBusy(""); }
  };

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

  if (loading || !session) return <main className={shared.loading}>Loading configuration</main>;

  const groups: Kind[][] = tab === "organisation" ? [["site", "department"]] : [["category", "subcategory", "process_area"]];
  return (
    <AdminShell session={session} active="configuration" eyebrow="Tenant Administration" title="Shape how ideas move through the organisation." description="Maintain shared reference data and publish controlled approval contracts without changing ideas already in flight.">
      <nav className={styles.tabs} aria-label="Configuration areas">
        <button type="button" data-active={tab === "organisation"} onClick={() => setTab("organisation")}><Building2 size={17} />Organisation</button>
        <button type="button" data-active={tab === "classification"} onClick={() => setTab("classification")}><Layers3 size={17} />Classification</button>
        <button type="button" data-active={tab === "workflow"} onClick={() => setTab("workflow")}><GitBranch size={17} />Approval workflow</button>
        <button type="button" data-active={tab === "idea_bank"} onClick={() => setTab("idea_bank")}><Eye size={17} />Idea Bank visibility</button>
        <button type="button" data-active={tab === "authentication"} onClick={() => setTab("authentication")}><ShieldCheck size={17} />Authentication</button>
      </nav>
      {message ? <DismissibleNotice onDismiss={() => setMessage("")}>{message}</DismissibleNotice> : null}
      {error ? <DismissibleNotice tone="error" onDismiss={() => setError("")}>{error}</DismissibleNotice> : null}
      {loadError ? <div className={styles.loadError} role="alert"><p>{loadError}</p><div><button type="button" onClick={() => void loadConfiguration()} disabled={loadingData}>{loadingData ? "Retrying" : "Retry"}</button><button type="button" onClick={() => setLoadError("")} aria-label="Dismiss configuration error">×</button></div></div> : null}
      {tab === "organisation" || tab === "classification" ? <div className={styles.registerGrid}>{groups[0].map((kind) => <MasterDataRegister key={kind} kind={kind} items={items[kind]} allItems={items} query={search[kind]} onQuery={(value) => setSearch((current) => ({ ...current, [kind]: value }))} busy={busy} onCreate={createItem} onToggle={(item) => item.is_active ? setConfirmation({ title: `Deactivate ${item.name}?`, description: "It will remain on historical records but will no longer be available for new ideas.", confirmLabel: "Deactivate", run: () => toggleItem(item) }) : void toggleItem(item)} />)}</div> : null}
      {tab === "workflow" ? <WorkflowRegister workflows={workflows} assignees={workflowAssignees} stages={stages} setStages={setStages} sourceVersion={sourceVersion} busy={busy} onCreate={createVersion} onEdit={editPublishedVersion} onPublish={(workflow, version) => setConfirmation({ title: `Publish version ${version.version}?`, description: "This version becomes the default contract for new ideas. The current published version will be retained as retired history.", confirmLabel: "Publish version", run: () => publishVersion(workflow, version) })} /> : null}
      {tab === "idea_bank" ? <IdeaBankPolicyEditor policy={ideaBankPolicy} onChange={setIdeaBankPolicy} onSave={() => void saveIdeaBankPolicy()} busy={busy === "policy"} /> : null}
      {tab === "authentication" ? <SSOEditor key={sso?.entra_directory_id ?? "new"} configuration={sso} busy={busy} onSave={saveSSO} onValidate={validateSSO} onActivate={() => setConfirmation({ title: "Move this organisation to Microsoft SSO?", description: `Password sign-in will stop for new sessions. ${sso?.active_user_count ?? 0} active users will be notified, while existing sessions and all TRANSPIRE data remain unchanged.`, confirmLabel: "Move to Microsoft SSO", run: activateSSO })} /> : null}
      <ConfirmDialog open={Boolean(confirmation)} title={confirmation?.title ?? "Confirm action"} description={confirmation?.description ?? ""} confirmLabel={confirmation?.confirmLabel ?? "Confirm"} busyLabel="Working" busy={Boolean(busy)} onClose={() => setConfirmation(null)} onConfirm={() => void confirmAction()} />
    </AdminShell>
  );
}

function SSOEditor({ configuration, busy, onSave, onValidate, onActivate }: { configuration: SSOConfiguration | null; busy: string; onSave: (directoryId: string) => Promise<void>; onValidate: () => void; onActivate: () => void }) {
  const [directoryId, setDirectoryId] = useState(configuration?.entra_directory_id ?? "");
  if (!configuration) return <section className={styles.ssoPanel}><p>Loading Microsoft SSO readiness</p></section>;
  const ready = configuration.active_user_count > 0 && configuration.active_user_count === configuration.ready_user_count;
  const validated = Boolean(configuration.validated_at);
  const active = configuration.status === "active";
  return <div className={styles.ssoLayout}>
    <section className={styles.ssoPanel} aria-labelledby="sso-title">
      <header><div><p>Microsoft Entra ID</p><h2 id="sso-title">Move sign-in without moving user data.</h2><span>SSO links Microsoft identities to existing TRANSPIRE users, memberships, roles, ideas, projects, and history.</span></div><ShieldCheck size={22} /></header>
      <ol className={styles.ssoSteps}>
        <li data-complete={Boolean(configuration.entra_directory_id)}><span>1</span><div><strong>Connect the directory</strong><small>Use the Microsoft Entra tenant ID for this organisation.</small></div></li>
        <li data-complete={validated}><span>2</span><div><strong>Validate with an administrator</strong><small>A real Microsoft login must match your current tenant administrator.</small></div></li>
        <li data-complete={active}><span>3</span><div><strong>Move to SSO</strong><small>New sign-ins use Microsoft only. Existing sessions continue normally.</small></div></li>
      </ol>
      <div className={shared.field}><label htmlFor="entra-directory-id">Microsoft Entra tenant ID</label><input id="entra-directory-id" value={directoryId} onChange={(event) => setDirectoryId(event.target.value)} placeholder="00000000-0000-0000-0000-000000000000" disabled={active || busy !== ""} /></div>
      {!configuration.client_id_configured ? <div className={styles.ssoWarning} role="alert"><strong>Platform setup required</strong><span>The Microsoft application credentials must be configured before this directory can be tested.</span></div> : null}
      <div className={styles.ssoActions}>
        <button type="button" onClick={() => void onSave(directoryId)} disabled={active || busy !== "" || !directoryId || !configuration.client_id_configured}><Save size={16} />{busy === "sso:save" ? "Saving" : "Save directory"}</button>
        <button type="button" onClick={onValidate} disabled={active || busy !== "" || !configuration.entra_directory_id}><ShieldCheck size={16} />Test Microsoft sign-in</button>
      </div>
    </section>
    <section className={styles.ssoReadiness} aria-labelledby="sso-readiness-title">
      <header><div><p>Cutover readiness</p><h2 id="sso-readiness-title">{active ? "Microsoft SSO is active" : `${configuration.ready_user_count} of ${configuration.active_user_count} people ready`}</h2></div><span data-state={active ? "active" : ready && validated ? "ready" : "pending"}>{active ? "Active" : ready && validated ? "Ready" : "Pending"}</span></header>
      <dl><div><dt>Administrator test</dt><dd>{validated ? `Passed ${new Date(configuration.validated_at!).toLocaleString()}` : "Required"}</dd></div><div><dt>Existing sessions</dt><dd>Remain active until normal expiry</dd></div><div><dt>User notifications</dt><dd>{active ? `${configuration.notification_count} queued` : `${configuration.active_user_count} will be queued`}</dd></div></dl>
      <div className={styles.ssoPeople}>{configuration.members.map((member) => <div key={member.membership_id}><span><strong>{member.display_name}</strong><small>{member.email}</small></span><em data-ready={member.ready}>{member.linked ? "Linked" : member.ready ? "Ready" : "Action required"}</em></div>)}</div>
      {!active ? <button className={styles.activateSSO} type="button" onClick={onActivate} disabled={busy !== "" || !ready || !validated}><ShieldCheck size={17} />Move to Microsoft SSO</button> : <p className={styles.activeNote}>Password sign-in is disabled for this tenant. Platform-controlled recovery remains available for SSO repair.</p>}
    </section>
  </div>;
}

function IdeaBankPolicyEditor({ policy, onChange, onSave, busy }: { policy: IdeaBankPolicy; onChange: (policy: IdeaBankPolicy) => void; onSave: () => void; busy: boolean }) {
  const levels: Array<{ value: IdeaBankPolicy["detail_level"]; label: string; description: string }> = [
    { value: "headline", label: "Headline", description: "Reference, title, type, category, and submission date." },
    { value: "operational", label: "Operational", description: "Adds subcategory, process area, SQDCP, baseline, and target." },
    { value: "full", label: "Full context", description: "Also shares the problem statement and business case." },
  ];
  return <section className={styles.policy}><header><div><p>Tenant sharing policy</p><h2>Decide what the Idea Bank reveals.</h2><span>The backend applies this policy before idea data leaves the tenant boundary.</span></div><Eye size={20} /></header><fieldset><legend>Detail level</legend>{levels.map((level) => <button key={level.value} type="button" aria-pressed={policy.detail_level === level.value} onClick={() => onChange({ ...policy, detail_level: level.value })}><span><strong>{level.label}</strong><small>{level.description}</small></span>{policy.detail_level === level.value ? <span className={styles.selected}><CheckMark /></span> : null}</button>)}</fieldset><div className={styles.policyToggles}><button type="button" aria-pressed={policy.show_contributor} onClick={() => onChange({ ...policy, show_contributor: !policy.show_contributor })}><span><strong>Show contributor name</strong><small>Turn off to share ideas anonymously.</small></span><i data-on={policy.show_contributor}><b /></i></button><button type="button" aria-pressed={policy.show_financials} onClick={() => onChange({ ...policy, show_financials: !policy.show_financials })}><span><strong>Show financial estimates</strong><small>Annual saving, cost avoidance, and investment.</small></span><i data-on={policy.show_financials}><b /></i></button></div><button className={styles.policySave} type="button" onClick={onSave} disabled={busy}><Save size={16} />{busy ? "Saving policy" : "Save visibility policy"}</button></section>;
}

function CheckMark() { return <span aria-hidden="true">✓</span>; }

function MasterDataRegister({ kind, items, allItems, query, onQuery, busy, onCreate, onToggle }: { kind: Kind; items: Item[]; allItems: Record<Kind, Item[]>; query: string; onQuery: (value: string) => void; busy: string; onCreate: (kind: Kind, event: FormEvent<HTMLFormElement>) => Promise<void>; onToggle: (item: Item) => void }) {
  const parentKind = labels[kind].parent;
  const parents = parentKind ? allItems[parentKind].filter((item) => item.is_active) : [];
  const [parentId, setParentId] = useState("");
  const [selectedSiteIds, setSelectedSiteIds] = useState<string[]>([]);
  const [allSites, setAllSites] = useState(false);
  const visible = useMemo(() => { const term = query.trim().toLocaleLowerCase(); return term ? items.filter((item) => `${item.name} ${item.code} ${item.is_active ? "active" : "inactive"}`.toLocaleLowerCase().includes(term)) : items; }, [items, query]);
  return <section className={styles.register} aria-labelledby={`${kind}-title`}>
    <header><div><p>Reference data</p><h2 id={`${kind}-title`}>{labels[kind].plural}</h2><span>{items.length} configured</span></div><Plus size={20} /></header>
    <form onSubmit={(event) => { void onCreate(kind, event); setParentId(""); setSelectedSiteIds([]); setAllSites(false); }}>
      <div className={shared.field}><label htmlFor={`${kind}-name`}>{labels[kind].singular} name</label><input id={`${kind}-name`} name="name" required minLength={2} onBlur={(event) => { const code = event.currentTarget.form?.elements.namedItem("code") as HTMLInputElement | null; if (code && !code.value) code.value = slugify(event.currentTarget.value); }} /></div>
      <div className={shared.field}><label htmlFor={`${kind}-code`}>Stable code</label><input id={`${kind}-code`} name="code" required minLength={2} pattern="[a-z0-9]+(?:_[a-z0-9]+)*" placeholder="e.g. quality_assurance" /></div>
      {parentKind ? <SelectField id={`${kind}-parent`} name="parent_id" label={labels[parentKind].singular} value={parentId} onChange={setParentId} disabled={!parents.length} options={parents.length ? parents.map((parent) => ({ value: parent.id, label: parent.name, description: parent.code })) : [{ value: "", label: `Add a ${labels[parentKind].singular.toLowerCase()} first`, description: "A parent record is required" }]} /> : null}
      {kind === "department" ? <fieldset className={styles.siteScope}><legend>Available at</legend><label data-selected={allSites}><input type="checkbox" name="applies_to_all_sites" value="true" checked={allSites} onChange={(event) => { setAllSites(event.target.checked); if (event.target.checked) setSelectedSiteIds([]); }} /><span><strong>All sites</strong><small>Automatically includes current and future sites</small></span></label><div>{allItems.site.filter((site) => site.is_active).map((site) => <label key={site.id} data-selected={selectedSiteIds.includes(site.id)}><input type="checkbox" name="site_ids" value={site.id} checked={selectedSiteIds.includes(site.id)} disabled={allSites} onChange={(event) => setSelectedSiteIds((current) => event.target.checked ? [...current, site.id] : current.filter((id) => id !== site.id))} /><span><strong>{site.name}</strong><small>{site.code}</small></span></label>)}</div>{!allItems.site.some((site) => site.is_active) ? <p>Add an active site before creating a department.</p> : null}</fieldset> : null}
      <button className={shared.primary} type="submit" disabled={busy !== "" || Boolean(parentKind && !parentId) || (kind === "department" && !allSites && selectedSiteIds.length === 0)}><Plus size={16} />Add {labels[kind].singular.toLowerCase()}</button>
    </form>
    <SearchField id={`${kind}-search`} label={`Search ${labels[kind].plural.toLowerCase()}`} value={query} onChange={onQuery} placeholder={`Search ${labels[kind].plural.toLowerCase()}`} resultCount={visible.length} />
    <div className={styles.entries}>{visible.map((item) => <article key={item.id} data-inactive={!item.is_active}><div><strong>{item.name}</strong><span>{item.code}</span>{item.parent_id ? <small>{allItems[parentKind!].find((parent) => parent.id === item.parent_id)?.name}</small> : null}{item.kind === "department" ? <small>{item.applies_to_all_sites ? "All sites" : item.site_ids.map((siteId) => allItems.site.find((site) => site.id === siteId)?.name).filter(Boolean).join(", ") || "No site assigned"}</small> : null}</div><button type="button" onClick={() => onToggle(item)} disabled={busy !== ""} data-tone={item.is_active ? "danger" : "default"}><Power size={14} />{item.is_active ? "Deactivate" : "Reactivate"}</button></article>)}</div>
    {!visible.length ? <p className={styles.empty}>{items.length ? `No ${labels[kind].plural.toLowerCase()} match “${query}”.` : `Add the first ${labels[kind].singular.toLowerCase()} to establish this register.`}</p> : null}
  </section>;
}

function WorkflowRegister({ workflows, assignees, stages, setStages, sourceVersion, busy, onCreate, onEdit, onPublish }: { workflows: Workflow[]; assignees: WorkflowAssignee[]; stages: Stage[]; setStages: (stages: Stage[]) => void; sourceVersion: number | null; busy: string; onCreate: (event: FormEvent<HTMLFormElement>) => Promise<void>; onEdit: (version: Version) => void; onPublish: (workflow: Workflow, version: Version) => void }) {
  const update = (index: number, field: keyof Stage, value: string | number | boolean) => setStages(stages.map((stage, position) => position === index ? { ...stage, [field]: value } : stage));
  const updateName = (index: number, value: string) => setStages(stages.map((stage, position) => position === index ? { ...stage, name: value, key: !stage.key || stage.key === slugify(stage.name) ? slugify(value) : stage.key } : stage));
  return <div className={styles.workflowGrid}>
    <section className={styles.contract}><header><div><p>Versioned contract</p><h2>Idea approval</h2><span>Published versions are retained for audit and in-flight work.</span></div><GitBranch size={20} /></header>
      {workflows.map((workflow) => <div key={workflow.id} className={styles.timeline}>{workflow.versions.map((version) => <article key={version.id}><div className={styles.versionLine}><strong>Version {version.version}</strong><span data-state={version.status}>{version.status}</span><time>{new Date(version.published_at ?? version.created_at).toLocaleDateString()}</time></div><ol>{version.stages.map((stage) => <li key={stage.key}><span>{stage.name}</span><small>{stage.assignee_name ? `${stage.assignee_name} · ${stage.assignee_email} · ${stage.assignee_status}` : `${stage.approver_role.replaceAll("_", " ")} · legacy assignment`} · {stage.sla_hours}h SLA</small></li>)}</ol><div className={styles.versionActions}>{version.status === "draft" ? <button type="button" onClick={() => onPublish(workflow, version)} disabled={busy !== ""}><Rocket size={15} />Publish version</button> : null}{version.status === "published" ? <button type="button" onClick={() => onEdit(version)} disabled={busy !== ""}><Pencil size={15} />Edit as new version</button> : null}</div></article>)}</div>)}
    </section>
    <section className={styles.builder} id="workflow-builder"><header><div><p>Contract builder</p><h2>{sourceVersion ? `Editing from version ${sourceVersion}` : "Create the next draft"}</h2><span>{sourceVersion ? "Changes will be saved as a new draft. The published contract and ideas already using it remain unchanged." : "Assign an accountable person at every stage. Active members and pending invitees are available."}</span></div><Plus size={20} /></header>
      {!assignees.length ? <p className={styles.assigneeEmpty}>Invite or activate at least one person before building a workflow.</p> : null}
      <form onSubmit={(event) => void onCreate(event)}>{stages.map((stage, index) => <fieldset key={index}><legend>Stage {index + 1}</legend><div className={shared.field}><label htmlFor={`stage-name-${index}`}>Stage name</label><input id={`stage-name-${index}`} value={stage.name} required minLength={2} onChange={(event) => updateName(index, event.target.value)} /></div><div className={shared.field}><label htmlFor={`stage-key-${index}`}>Stable key</label><input id={`stage-key-${index}`} value={stage.key} required pattern="[a-z0-9]+(?:_[a-z0-9]+)*" onChange={(event) => update(index, "key", event.target.value)} /></div><div className={shared.field}><label htmlFor={`stage-sla-${index}`}>SLA hours</label><input id={`stage-sla-${index}`} type="number" min={1} max={8760} value={stage.sla_hours} required onChange={(event) => update(index, "sla_hours", Number(event.target.value))} /></div><SearchableSelectField id={`stage-assignee-${index}`} name={`stage-assignee-${index}`} label="Approver" value={stage.assignee_membership_id ?? ""} onChange={(value) => update(index, "assignee_membership_id", value)} disabled={!assignees.length} placeholder="Select an approver" searchPlaceholder="Search name, email, or status" emptyMessage="No active members or pending invitees match." options={assignees.map((assignee) => ({ value: assignee.membership_id, label: assignee.display_name, description: assignee.email, status: assignee.status }))} />{stages.length > 1 ? <button className={styles.removeStage} type="button" onClick={() => setStages(stages.filter((_, position) => position !== index))}><Trash2 size={14} />Remove</button> : null}</fieldset>)}<div className={styles.builderActions}><button type="button" onClick={() => setStages([...stages, emptyStage()])}><Plus size={15} />Add stage</button><button className={shared.primary} type="submit" disabled={busy !== "" || !assignees.length || stages.some((stage) => !stage.assignee_membership_id)}><GitBranch size={16} />Create draft version</button></div></form>
    </section>
  </div>;
}
