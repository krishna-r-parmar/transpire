"use client";

import { Archive, CheckCircle2, FilePenLine, GitBranch, Pencil, Plus, Rocket, Trash2, TriangleAlert } from "lucide-react";
import { FormEvent, useCallback, useEffect, useState } from "react";
import { AdminShell } from "@/components/admin/admin-shell";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { DismissibleNotice } from "@/components/ui/dismissible-notice";
import { SearchableSelectField } from "@/components/ui/searchable-select-field";
import { SectionCard, StatusPill } from "@/components/ui/workspace";
import { apiRequest } from "@/lib/api";
import { useAdminSession } from "@/lib/use-admin-session";
import { useTenantRouter as useRouter } from "@/lib/use-tenant-router";
import shared from "../admin.module.css";
import styles from "../configuration.module.css";
import register from "@/components/admin/admin-register.module.css";

type Stage = { key: string; name: string; approver_role: string; assignee_membership_id: string | null; assignee_name: string | null; assignee_email: string | null; assignee_status: "active" | "pending" | null; sla_hours: number; required: boolean };
type WorkflowAssignee = { membership_id: string; display_name: string; email: string; status: "active" | "pending" };
type Version = { id: string; version: number; status: "draft" | "published" | "retired"; stages: Stage[]; published_at: string | null; created_at: string };
type Workflow = { id: string; key: string; name: string; description: string; is_active: boolean; versions: Version[] };
type Confirmation = { title: string; description: string; confirmLabel: string; run: () => Promise<void> };
const emptyStage = (): Stage => ({ key: "", name: "", approver_role: "assigned_member", assignee_membership_id: "", assignee_name: null, assignee_email: null, assignee_status: null, sla_hours: 48, required: true });
const slugify = (value: string) => value.toLocaleLowerCase().trim().replace(/[^a-z0-9]+/g, "_").replace(/^_|_$/g, "");

export function WorkflowConsole() {
  const router = useRouter();
  const { session, loading } = useAdminSession();
  const [loaded, setLoaded] = useState(false);
  const [workflows, setWorkflows] = useState<Workflow[]>([]);
  const [workflowAssignees, setWorkflowAssignees] = useState<WorkflowAssignee[]>([]);
  const [stages, setStages] = useState<Stage[]>([emptyStage()]);
  const [sourceVersion, setSourceVersion] = useState<number | null>(null);
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
        apiRequest("/admin/configuration/workflows/contracts"),
        apiRequest("/admin/configuration/workflows/assignees"),
      ]);
      if (responses.some((response) => response.status === 401)) return router.replace("/sign-in");
      if (responses.some((response) => response.status === 403)) return router.replace("/home");
      if (responses[0].ok) setWorkflows(await responses[0].json() as Workflow[]);
      if (responses[1].ok) setWorkflowAssignees(await responses[1].json() as WorkflowAssignee[]);
      if (responses.some((response) => !response.ok)) setError("Some settings could not be loaded. Retry in a moment.");
    } catch { setError("TRANSPIRE could not reach the configuration service. Check the connection, then retry."); }
    finally { setLoaded(true); }
  }, [router]);

  useEffect(() => {
    if (!session) return;
    const timer = window.setTimeout(() => void loadConfiguration(), 0);
    return () => window.clearTimeout(timer);
  }, [loadConfiguration, session]);

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
  const editPublishedVersion = (version: Version) => {
    setStages(version.stages.map((stage) => ({ ...stage })));
    setSourceVersion(version.version);
    window.requestAnimationFrame(() => document.getElementById("workflow-builder")?.scrollIntoView({ behavior: "smooth", block: "start" }));
    flash(`Version ${version.version} copied into the builder. Saving creates a new draft version.`);
  };

  if (loading || !session) return <main className={shared.loading}>Loading administration</main>;

  return (
    <AdminShell session={session} active="workflow" title="Approval workflow" description="The approval route new ideas follow. Published versions are kept for audit and for ideas already in review.">
      {message || error ? <div className={register.notices}>
        {message ? <DismissibleNotice onDismiss={() => setMessage("")}>{message}</DismissibleNotice> : null}
        {error ? <DismissibleNotice tone="error" onDismiss={() => setError("")}>{error}</DismissibleNotice> : null}
      </div> : null}
      {loaded ? <WorkflowRegister workflows={workflows} assignees={workflowAssignees} stages={stages} setStages={setStages} sourceVersion={sourceVersion} busy={busy} onCreate={createVersion} onEdit={editPublishedVersion} onPublish={(workflow, version) => setConfirmation({ title: `Publish version ${version.version}?`, description: "This version becomes the default contract for new ideas. The current published version will be retained as retired history.", confirmLabel: "Publish version", run: () => publishVersion(workflow, version) })} /> : <p className={register.empty}>Loading approval workflow</p>}
      <ConfirmDialog open={Boolean(confirmation)} title={confirmation?.title ?? "Confirm action"} description={confirmation?.description ?? ""} confirmLabel={confirmation?.confirmLabel ?? "Confirm"} busyLabel="Working" busy={Boolean(busy)} onClose={() => setConfirmation(null)} onConfirm={() => void confirmAction()} />
    </AdminShell>
  );
}

function VersionStatus({ status }: { status: Version["status"] }) {
  if (status === "published") return <StatusPill tone="success" icon={<CheckCircle2 aria-hidden="true" size={14} />}>Published</StatusPill>;
  if (status === "draft") return <StatusPill tone="warning" icon={<FilePenLine aria-hidden="true" size={14} />}>Draft</StatusPill>;
  return <StatusPill icon={<Archive aria-hidden="true" size={14} />}>Retired</StatusPill>;
}


function WorkflowRegister({ workflows, assignees, stages, setStages, sourceVersion, busy, onCreate, onEdit, onPublish }: { workflows: Workflow[]; assignees: WorkflowAssignee[]; stages: Stage[]; setStages: (stages: Stage[]) => void; sourceVersion: number | null; busy: string; onCreate: (event: FormEvent<HTMLFormElement>) => Promise<void>; onEdit: (version: Version) => void; onPublish: (workflow: Workflow, version: Version) => void }) {
  const update = (index: number, field: keyof Stage, value: string | number | boolean) => setStages(stages.map((stage, position) => position === index ? { ...stage, [field]: value } : stage));
  const updateName = (index: number, value: string) => setStages(stages.map((stage, position) => position === index ? { ...stage, name: value, key: !stage.key || stage.key === slugify(stage.name) ? slugify(value) : stage.key } : stage));
  return <div className={styles.workflowGrid}>
    <SectionCard icon={<GitBranch size={17} />} title="Idea approval" description="Published versions are retained for audit and in-flight work." meta="Versioned contract">
      {workflows.map((workflow) => <div key={workflow.id} className={styles.timeline}>{workflow.versions.map((version) => <article key={version.id} data-state={version.status}><div className={styles.versionLine}><strong>Version {version.version}</strong><VersionStatus status={version.status} /><time>{new Date(version.published_at ?? version.created_at).toLocaleDateString()}</time></div><ol>{version.stages.map((stage, index) => <li key={stage.key}><span className={styles.stageIndex} aria-hidden="true">{index + 1}</span><div><strong>{stage.name}</strong><small>{stage.assignee_name ? `${stage.assignee_name} · ${stage.assignee_email} · ${stage.assignee_status}` : `${stage.approver_role.replaceAll("_", " ")} · legacy assignment`} · {stage.sla_hours}h SLA</small></div></li>)}</ol><div className={styles.versionActions}>{version.status === "draft" ? <button type="button" onClick={() => onPublish(workflow, version)} disabled={busy !== ""}><Rocket size={15} />Publish version</button> : null}{version.status === "published" ? <button type="button" onClick={() => onEdit(version)} disabled={busy !== ""}><Pencil size={15} />Edit as new version</button> : null}</div></article>)}</div>)}
    </SectionCard>
    <div className={styles.builderAnchor} id="workflow-builder"><SectionCard className={styles.builder} icon={<Plus size={17} />} title={sourceVersion ? `Editing from version ${sourceVersion}` : "Create the next draft"} description={sourceVersion ? "Changes will be saved as a new draft. The published contract and ideas already using it remain unchanged." : "Assign an accountable person at every stage. Active members and pending invitees are available."} meta="Contract builder">
      {!assignees.length ? <p className={styles.assigneeEmpty}><TriangleAlert aria-hidden="true" size={16} />Invite or activate at least one person before building a workflow.</p> : null}
      <form onSubmit={(event) => void onCreate(event)}>{stages.map((stage, index) => <fieldset key={index}><legend>Stage {index + 1}</legend><div className={shared.field}><label htmlFor={`stage-name-${index}`}>Stage name</label><input id={`stage-name-${index}`} value={stage.name} required minLength={2} onChange={(event) => updateName(index, event.target.value)} /></div><div className={shared.field}><label htmlFor={`stage-key-${index}`}>Stable key</label><input id={`stage-key-${index}`} value={stage.key} required pattern="[a-z0-9]+(?:_[a-z0-9]+)*" onChange={(event) => update(index, "key", event.target.value)} /></div><div className={shared.field}><label htmlFor={`stage-sla-${index}`}>SLA hours</label><input id={`stage-sla-${index}`} type="number" min={1} max={8760} value={stage.sla_hours} required onChange={(event) => update(index, "sla_hours", Number(event.target.value))} /></div><SearchableSelectField id={`stage-assignee-${index}`} name={`stage-assignee-${index}`} label="Approver" value={stage.assignee_membership_id ?? ""} onChange={(value) => update(index, "assignee_membership_id", value)} disabled={!assignees.length} placeholder="Select an approver" searchPlaceholder="Search name, email, or status" emptyMessage="No active members or pending invitees match." options={assignees.map((assignee) => ({ value: assignee.membership_id, label: assignee.display_name, description: assignee.email, status: assignee.status }))} />{stages.length > 1 ? <button className={styles.removeStage} type="button" onClick={() => setStages(stages.filter((_, position) => position !== index))}><Trash2 size={14} />Remove</button> : null}</fieldset>)}<div className={styles.builderActions}><button type="button" onClick={() => setStages([...stages, emptyStage()])}><Plus size={15} />Add stage</button><button className={shared.primary} type="submit" disabled={busy !== "" || !assignees.length || stages.some((stage) => !stage.assignee_membership_id)}><GitBranch size={16} />Create draft version</button></div></form>
    </SectionCard></div>
  </div>;
}
