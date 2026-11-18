"use client";

import { Archive, CheckCircle2, FilePenLine, FlaskConical, History, Rocket, Save, Search, X } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { AdminShell } from "@/components/admin/admin-shell";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { DismissibleNotice } from "@/components/ui/dismissible-notice";
import { StatusPill } from "@/components/ui/workspace";
import { apiRequest } from "@/lib/api";
import { useAdminSession } from "@/lib/use-admin-session";
import { useTenantRouter as useRouter } from "@/lib/use-tenant-router";
import shared from "../admin.module.css";
import { type BuilderStage, type DirectoryEmployee, type GroupOption, type Preview, type Version, type Workflow, fromStored, newStage, stageProblems, toPayload } from "./builder-types";
import styles from "./builder.module.css";
import { StepInspector } from "./step-inspector";
import { WorkflowCanvas } from "./workflow-canvas";

type Confirmation = { title: string; description: string; confirmLabel: string; run: () => Promise<void> };

async function errorText(response: Response, fallback: string) {
  const payload = await response.json().catch(() => null) as { detail?: string | Array<{ msg: string }> } | null;
  return Array.isArray(payload?.detail) ? payload.detail[0]?.msg?.replace(/^Value error, /, "") ?? fallback : payload?.detail ?? fallback;
}

const signature = (stages: BuilderStage[]) => JSON.stringify(toPayload(stages));

export function WorkflowConsole() {
  const router = useRouter();
  const { session, loading } = useAdminSession();
  const [workflow, setWorkflow] = useState<Workflow | null>(null);
  const [groups, setGroups] = useState<GroupOption[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [stages, setStages] = useState<BuilderStage[]>([]);
  const [base, setBase] = useState<Version | null>(null);
  const [baseSignature, setBaseSignature] = useState("");
  const [selected, setSelected] = useState<string | null>(null);
  const [busy, setBusy] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [confirmation, setConfirmation] = useState<Confirmation | null>(null);
  const [testOpen, setTestOpen] = useState(false);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [previewSignature, setPreviewSignature] = useState("");

  const flash = (text: string, isError = false) => { setMessage(isError ? "" : text); setError(isError ? text : ""); };

  const openVersion = useCallback((version: Version) => {
    const next = version.stages.map(fromStored);
    setStages(next);
    setBase(version);
    setBaseSignature(signature(next));
    setSelected(next[0]?.uid ?? null);
    setPreview(null);
  }, []);

  const load = useCallback(async (focusVersionId?: string) => {
    try {
      const [workflowResponse, groupResponse] = await Promise.all([
        apiRequest("/admin/configuration/workflows/contracts"),
        apiRequest("/admin/configuration/approver-groups"),
      ]);
      if (workflowResponse.status === 401) return router.replace("/sign-in");
      if (workflowResponse.status === 403) return router.replace("/home");
      if (groupResponse.ok) setGroups(await groupResponse.json() as GroupOption[]);
      if (!workflowResponse.ok) { setError("The approval workflow could not be loaded."); return; }
      const loadedWorkflow = (await workflowResponse.json() as Workflow[])[0] ?? null;
      setWorkflow(loadedWorkflow);
      if (loadedWorkflow) {
        const versions = loadedWorkflow.versions;
        const focus = versions.find((version) => version.id === focusVersionId)
          ?? versions.find((version) => version.status === "draft")
          ?? versions.find((version) => version.status === "published")
          ?? versions[0];
        if (focus) openVersion(focus);
      }
    } catch {
      setError("TRANSPIRE could not reach the configuration service. Check the connection, then retry.");
    } finally {
      setLoaded(true);
    }
  }, [openVersion, router]);

  useEffect(() => {
    if (!session) return;
    const timer = window.setTimeout(() => void load(), 0);
    return () => window.clearTimeout(timer);
  }, [load, session]);

  const currentSignature = useMemo(() => signature(stages), [stages]);
  const dirty = currentSignature !== baseSignature;
  const problems = stages.flatMap((stage, index) => stageProblems(stage).map((problem) => `Step ${index + 1}: ${problem}`));
  const selectedIndex = stages.findIndex((stage) => stage.uid === selected);
  const previewFresh = preview && previewSignature === currentSignature;

  const insert = (index: number, source: "dynamic" | "group") => {
    const stage = newStage(source);
    setStages((current) => [...current.slice(0, index), stage, ...current.slice(index)]);
    setSelected(stage.uid);
  };
  const updateStage = (next: BuilderStage) => setStages((current) => current.map((stage) => stage.uid === next.uid ? next : stage));
  const move = (direction: -1 | 1) => setStages((current) => {
    const index = current.findIndex((stage) => stage.uid === selected);
    const target = index + direction;
    if (index < 0 || target < 0 || target >= current.length) return current;
    const next = [...current];
    [next[index], next[target]] = [next[target], next[index]];
    return next;
  });
  const remove = () => setStages((current) => {
    const index = current.findIndex((stage) => stage.uid === selected);
    const next = current.filter((stage) => stage.uid !== selected);
    setSelected(next[Math.max(0, index - 1)]?.uid ?? null);
    return next;
  });

  const saveDraft = async () => {
    if (!workflow) return;
    setBusy("save"); flash("");
    try {
      const response = await apiRequest(`/admin/configuration/workflows/${workflow.id}/versions`, { method: "POST", body: JSON.stringify({ stages: toPayload(stages) }) });
      if (!response.ok) return flash(await errorText(response, "The draft could not be saved."), true);
      const created = await response.json() as Version;
      flash(`Saved as draft version ${created.version}. Test it, then publish when ready.`);
      await load(created.id);
    } catch {
      flash("Workflow configuration is temporarily unavailable.", true);
    } finally { setBusy(""); }
  };

  const publish = async (version: Version) => {
    if (!workflow) return;
    setBusy("publish"); flash("");
    try {
      const response = await apiRequest(`/admin/configuration/workflows/${workflow.id}/versions/${version.id}/publish`, { method: "POST" });
      if (!response.ok) return flash(await errorText(response, "The version could not be published."), true);
      flash(`Version ${version.version} is live. New ideas follow it; ideas already in review keep their version.`);
      await load(version.id);
    } catch {
      flash("Workflow publishing is temporarily unavailable.", true);
    } finally { setBusy(""); }
  };

  const runPreview = async (employee: DirectoryEmployee) => {
    setBusy("preview"); flash("");
    try {
      const response = await apiRequest("/admin/configuration/workflows/preview", { method: "POST", body: JSON.stringify({ stages: toPayload(stages), employee_id: employee.employee_id }) });
      if (!response.ok) return flash(await errorText(response, "The test could not run."), true);
      setPreview(await response.json() as Preview);
      setPreviewSignature(currentSignature);
    } catch {
      flash("Testing is temporarily unavailable.", true);
    } finally { setBusy(""); }
  };

  if (loading || !session) return <main className={shared.loading}>Loading administration</main>;

  const canPublish = base?.status === "draft" && !dirty && problems.length === 0;
  const status = !base ? null : dirty ? "unsaved" : base.status;

  return (
    <AdminShell session={session} active="workflow" eyebrow="Governance" title="Approval workflow" description="Draw the route every new idea follows. Dynamic steps come from the HR file; fixed steps go to approver groups.">
      {message || error ? <div className={shared.notices}>
        {message ? <DismissibleNotice onDismiss={() => setMessage("")}>{message}</DismissibleNotice> : null}
        {error ? <DismissibleNotice tone="error" onDismiss={() => setError("")}>{error}</DismissibleNotice> : null}
      </div> : null}
      {!loaded ? <p className={styles.loadingNote}>Loading the workflow</p> : !workflow ? <p className={styles.loadingNote}>No approval workflow exists for this workspace.</p> : <>
        <div className={styles.toolbar}>
          <div className={styles.toolbarState}>
            {base ? <strong>Version {base.version}</strong> : <strong>New workflow</strong>}
            {status === "unsaved" ? <StatusPill tone="warning" icon={<FilePenLine aria-hidden="true" size={14} />}>Unsaved changes</StatusPill> : status === "published" ? <StatusPill tone="success" icon={<CheckCircle2 aria-hidden="true" size={14} />}>Live</StatusPill> : status === "draft" ? <StatusPill tone="warning" icon={<FilePenLine aria-hidden="true" size={14} />}>Draft</StatusPill> : status === "retired" ? <StatusPill icon={<Archive aria-hidden="true" size={14} />}>Retired</StatusPill> : null}
            {problems.length ? <span className={styles.toolbarProblems}>{problems.length} thing{problems.length === 1 ? "" : "s"} to fix</span> : null}
          </div>
          <div className={styles.toolbarActions}>
            <button type="button" className={styles.secondary} aria-pressed={testOpen} onClick={() => setTestOpen((value) => !value)}><FlaskConical size={16} aria-hidden="true" />Test with an employee</button>
            <button type="button" className={styles.secondary} onClick={() => void saveDraft()} disabled={busy !== "" || !dirty || problems.length > 0}><Save size={16} aria-hidden="true" />{busy === "save" ? "Saving" : "Save as draft"}</button>
            <button type="button" className={shared.primary} disabled={busy !== "" || !canPublish} title={dirty ? "Save your changes as a draft first" : base?.status !== "draft" ? "Only a draft can be published" : undefined} onClick={() => base && setConfirmation({ title: `Publish version ${base.version}?`, description: "New ideas will follow this route. Ideas already in review keep the version they were submitted under.", confirmLabel: "Publish", run: () => publish(base) })}><Rocket size={16} aria-hidden="true" />Publish</button>
          </div>
        </div>

        {testOpen ? <TestPanel busy={busy === "preview"} preview={preview} fresh={Boolean(previewFresh)} disabled={problems.length > 0} onRun={(employee) => void runPreview(employee)} onClear={() => setPreview(null)} /> : null}

        <div className={styles.workspace}>
          <div className={styles.canvasWrap}>
            <WorkflowCanvas stages={stages} groups={groups} selected={selected} preview={previewFresh ? preview.steps : null} readOnly={false} onSelect={setSelected} onInsert={insert} />
          </div>
          <aside className={styles.inspectorWrap}>
            {selectedIndex >= 0
              ? <StepInspector stage={stages[selectedIndex]} index={selectedIndex} count={stages.length} groups={groups} readOnly={false} onChange={updateStage} onMove={move} onRemove={remove} />
              : <p className={styles.inspectorEmpty}>Select a step to change it, or use + to add one.</p>}
          </aside>
        </div>

        <section className={styles.versions} aria-labelledby="versions-title">
          <h2 id="versions-title"><History size={16} aria-hidden="true" />Versions</h2>
          <ol>{workflow.versions.map((version) => <li key={version.id} data-current={base?.id === version.id}>
            <span><strong>Version {version.version}</strong><small>{version.stages.map((stage) => stage.name).join(" → ")}</small></span>
            <span className={styles.versionMeta}>{version.status === "published" ? <StatusPill tone="success">Live</StatusPill> : version.status === "draft" ? <StatusPill tone="warning">Draft</StatusPill> : <StatusPill>Retired</StatusPill>}<time>{new Date(version.published_at ?? version.created_at).toLocaleDateString()}</time></span>
            <button type="button" className={styles.linkButton} disabled={base?.id === version.id && !dirty} onClick={() => dirty ? setConfirmation({ title: "Discard unsaved changes?", description: `Your changes to the builder will be lost when you open version ${version.version}.`, confirmLabel: "Discard and open", run: async () => openVersion(version) }) : openVersion(version)}>{base?.id === version.id ? "Open" : "Open in builder"}</button>
          </li>)}</ol>
        </section>
      </>}
      <ConfirmDialog open={Boolean(confirmation)} title={confirmation?.title ?? "Confirm"} description={confirmation?.description ?? ""} confirmLabel={confirmation?.confirmLabel ?? "Confirm"} busyLabel="Working" busy={busy !== ""} onClose={() => setConfirmation(null)} onConfirm={async () => { if (!confirmation) return; await confirmation.run(); setConfirmation(null); }} />
    </AdminShell>
  );
}

function TestPanel({ busy, preview, fresh, disabled, onRun, onClear }: { busy: boolean; preview: Preview | null; fresh: boolean; disabled: boolean; onRun: (employee: DirectoryEmployee) => void; onClear: () => void }) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<DirectoryEmployee[]>([]);
  const [chosen, setChosen] = useState<DirectoryEmployee | null>(null);
  const [searched, setSearched] = useState(false);

  useEffect(() => {
    if (chosen && query === chosen.display_name) return;
    const timer = window.setTimeout(async () => {
      const response = await apiRequest(`/admin/directory/employees?query=${encodeURIComponent(query)}`).catch(() => null);
      if (response?.ok) { setResults((await response.json() as DirectoryEmployee[]).filter((employee) => employee.status !== "left").slice(0, 8)); setSearched(true); }
    }, 200);
    return () => window.clearTimeout(timer);
  }, [chosen, query]);

  return <section className={styles.testPanel} aria-label="Test the workflow with an employee">
    <div className={styles.testSearch}>
      <label htmlFor="test-employee">Employee from the HR directory</label>
      <div className={styles.searchBox}>
        <Search size={15} aria-hidden="true" />
        <input id="test-employee" value={query} placeholder="Name, employee ID or department" onChange={(event) => { setQuery(event.target.value); setChosen(null); }} autoComplete="off" />
        {chosen ? <button type="button" aria-label="Clear employee" onClick={() => { setChosen(null); setQuery(""); onClear(); }}><X size={14} aria-hidden="true" /></button> : null}
      </div>
      {!chosen && results.length ? <ul className={styles.results} role="listbox" aria-label="Matching employees">{results.map((employee) => <li key={employee.employee_id}><button type="button" role="option" aria-selected={false} onClick={() => { setChosen(employee); setQuery(employee.display_name); onRun(employee); }}>
        <strong>{employee.display_name}</strong><small>{employee.employee_id} · {employee.department || "No department"}{employee.manager_name ? ` · RM ${employee.manager_name}` : ""}{employee.hod_name ? ` · HoD ${employee.hod_name}` : ""}</small>
      </button></li>)}</ul> : null}
      {!chosen && searched && !results.length ? <p className={styles.testHint}>No employees found. Load the HR file under Administration → HR directory first.</p> : null}
    </div>
    <div className={styles.testStatus} aria-live="polite">
      {busy ? "Working out the route" : disabled ? "Fix the highlighted steps to test." : preview && fresh ? <>Showing the route for <strong>{preview.employee_name}</strong> on each step.</> : preview ? <><span>The route changed since the last test.</span>{chosen ? <button type="button" className={styles.linkButton} onClick={() => onRun(chosen)}>Test again</button> : null}</> : chosen ? <><span>Ready to test <strong>{chosen.display_name}</strong>.</span><button type="button" className={styles.linkButton} onClick={() => onRun(chosen)}>Test again</button></> : "Pick an employee to see who approves each step."}
    </div>
  </section>;
}
