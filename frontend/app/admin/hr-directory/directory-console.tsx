"use client";

import { AlertTriangle, CheckCircle2, CircleSlash, Copy, FileUp, Search, Settings2, Upload } from "lucide-react";
import { ChangeEvent, FormEvent, useCallback, useEffect, useState } from "react";
import { AdminShell } from "@/components/admin/admin-shell";
import { SidePanel } from "@/components/admin/side-panel";
import { DismissibleNotice } from "@/components/ui/dismissible-notice";
import { StatusPill } from "@/components/ui/workspace";
import register from "@/components/admin/admin-register.module.css";
import { apiRequest } from "@/lib/api";
import { useAdminSession } from "@/lib/use-admin-session";
import { useTenantRouter as useRouter } from "@/lib/use-tenant-router";
import shared from "../admin.module.css";
import { isWorkspaceOwner } from "@/lib/roles";
import styles from "./directory.module.css";
import { SftpCard } from "./sftp-card";

type DirectorySettings = { invite_new_employees: boolean; allowed_email_domains: string[]; max_drop_percent: number };
type Overview = { settings: DirectorySettings; inbox_folder: string; inbox_waiting: string[]; employees_active: number; employees_missing: number; employees_left: number; employees_with_account: number; last_applied_at: string | null };
type Person = { employee_id: string; name: string; reason?: string; fields?: string[] };
type Run = { id: string; file_name: string; source: string; status: "previewed" | "applied" | "rejected" | "duplicate" | "failed"; created_at: string; summary: Record<string, number | null>; report: { message?: string; issues?: { line: number; employee_id: string | null; severity: string; message: string }[]; new?: Person[]; changed?: Person[]; missing?: Person[]; leaving?: Person[]; invited?: Person[]; deactivated?: Person[]; review?: Person[]; email_changes?: { name: string; from: string; to: string }[]; reroutes?: string[] } };
type Employee = { employee_id: string; display_name: string; email: string | null; location: string; department: string; sub_department: string; manager_name: string | null; hod_name: string | null; status: string; has_account: boolean };

const dateTime = new Intl.DateTimeFormat("en-IN", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" });

function RunStatus({ status }: { status: Run["status"] }) {
  if (status === "applied") return <StatusPill tone="success" icon={<CheckCircle2 size={14} aria-hidden="true" />}>Applied</StatusPill>;
  if (status === "previewed") return <StatusPill tone="info">Preview</StatusPill>;
  if (status === "duplicate") return <StatusPill icon={<Copy size={14} aria-hidden="true" />}>Already applied</StatusPill>;
  return <StatusPill tone="danger" icon={<AlertTriangle size={14} aria-hidden="true" />}>{status === "rejected" ? "Rejected" : "Failed"}</StatusPill>;
}

export function DirectoryConsole() {
  const router = useRouter();
  const { session, loading } = useAdminSession();
  const [overview, setOverview] = useState<Overview | null>(null);
  const [runs, setRuns] = useState<Run[]>([]);
  const [employees, setEmployees] = useState<Employee[]>([]);
  const [query, setQuery] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<Run | null>(null);
  const [openRun, setOpenRun] = useState<Run | null>(null);
  const [settingsDraft, setSettingsDraft] = useState<(DirectorySettings & { domainsText: string }) | null>(null);
  const [busy, setBusy] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    try {
      const [overviewResponse, runsResponse] = await Promise.all([apiRequest("/admin/directory"), apiRequest("/admin/directory/runs")]);
      if (overviewResponse.status === 403) return router.replace("/home");
      if (overviewResponse.ok) setOverview(await overviewResponse.json() as Overview);
      if (runsResponse.ok) setRuns(await runsResponse.json() as Run[]);
    } catch {
      setError("The HR directory could not be loaded.");
    }
  }, [router]);

  useEffect(() => {
    if (!session) return;
    const timer = window.setTimeout(() => void load(), 0);
    return () => window.clearTimeout(timer);
  }, [load, session]);

  useEffect(() => {
    if (!session) return;
    const timer = window.setTimeout(async () => {
      const response = await apiRequest(`/admin/directory/employees?query=${encodeURIComponent(query)}`).catch(() => null);
      if (response?.ok) setEmployees(await response.json() as Employee[]);
    }, 200);
    return () => window.clearTimeout(timer);
  }, [query, session, runs]);

  const send = async (mode: "preview" | "apply", force = false) => {
    if (!file) return;
    setBusy(mode); setError(""); setMessage("");
    try {
      const response = await apiRequest(`/admin/directory/upload?file_name=${encodeURIComponent(file.name)}&mode=${mode}&force=${force}`, {
        method: "POST",
        body: await file.arrayBuffer(),
        headers: { "Content-Type": "application/octet-stream" },
      });
      if (!response.ok) { setError("The file could not be processed."); return; }
      const run = await response.json() as Run;
      if (mode === "preview" || run.status !== "applied") setPreview(run);
      if (run.status === "applied") {
        setMessage(`${file.name} applied: ${run.summary.new ?? 0} new, ${run.summary.changed ?? 0} changed, ${run.summary.invited ?? 0} invited, ${run.summary.deactivated ?? 0} deactivated.`);
        setPreview(null); setFile(null);
      } else if (run.status === "duplicate") {
        setMessage("This exact file was already applied. Nothing changed.");
        setPreview(null);
      }
      await load();
    } catch {
      setError("Uploading is temporarily unavailable.");
    } finally { setBusy(""); }
  };

  const processInbox = async () => {
    setBusy("inbox"); setError(""); setMessage("");
    try {
      const response = await apiRequest("/admin/directory/inbox/process", { method: "POST" });
      if (!response.ok) { setError("The inbox could not be processed."); return; }
      const processed = await response.json() as Run[];
      setMessage(processed.length ? `Processed ${processed.length} file${processed.length === 1 ? "" : "s"} from the inbox.` : "No settled files in the inbox. Files are picked up a minute after they finish arriving.");
      await load();
    } catch {
      setError("The inbox is temporarily unavailable.");
    } finally { setBusy(""); }
  };

  const saveSettings = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!settingsDraft) return;
    setBusy("settings");
    try {
      const response = await apiRequest("/admin/directory/settings", {
        method: "PUT",
        body: JSON.stringify({ invite_new_employees: settingsDraft.invite_new_employees, max_drop_percent: settingsDraft.max_drop_percent, allowed_email_domains: settingsDraft.domainsText.split(/[\s,]+/).filter(Boolean) }),
      });
      if (!response.ok) { setError("Settings could not be saved."); return; }
      setSettingsDraft(null); setMessage("HR directory settings saved. They apply from the next file.");
      await load();
    } finally { setBusy(""); }
  };

  if (loading || !session) return <main className={shared.loading}>Loading administration</main>;

  return (
    <AdminShell
      session={session}
      active="hr_directory"
      eyebrow="Access"
      title="HR directory"
      description="Employees as reported by the HR system. Reporting managers and heads of department from here drive dynamic approval steps."
      actions={overview ? <button type="button" className={styles.secondary} onClick={() => setSettingsDraft({ ...overview.settings, domainsText: overview.settings.allowed_email_domains.join(", ") })}><Settings2 size={16} aria-hidden="true" />Settings</button> : null}
    >
      {message || error ? <div className={shared.notices}>
        {message ? <DismissibleNotice onDismiss={() => setMessage("")}>{message}</DismissibleNotice> : null}
        {error ? <DismissibleNotice tone="error" onDismiss={() => setError("")}>{error}</DismissibleNotice> : null}
      </div> : null}

      {overview ? <dl className={styles.stats}>
        <div><dt>Active employees</dt><dd>{overview.employees_active}</dd></div>
        <div><dt>With a TRANSPIRE account</dt><dd>{overview.employees_with_account}</dd></div>
        <div><dt>Missing from last file</dt><dd>{overview.employees_missing}</dd></div>
        <div><dt>Left</dt><dd>{overview.employees_left}</dd></div>
        <div><dt>Last applied</dt><dd className={styles.small}>{overview.last_applied_at ? dateTime.format(new Date(overview.last_applied_at)) : "Never"}</dd></div>
      </dl> : null}

      <div className={styles.sources}>
        <SftpCard isOwner={isWorkspaceOwner(session.roles)} onRun={load} />
        <section className={styles.card} aria-labelledby="upload-title">
          <h2 id="upload-title"><FileUp size={17} aria-hidden="true" />Upload a file</h2>
          <p>Same report format (.xlsx or .csv). You always see what will change before anything is applied.</p>
          <p className={styles.small}>Files dropped into <code>{overview?.inbox_folder ?? "the inbox folder"}</code> on the server are applied by the scheduled job too.{overview?.inbox_waiting.length ? ` Waiting: ${overview.inbox_waiting.join(", ")}.` : ""} <button type="button" className={styles.inlineLink} onClick={() => void processInbox()} disabled={busy !== ""}>{busy === "inbox" ? "Checking" : "Check inbox now"}</button></p>
          <label className={styles.drop}>
            <Upload size={18} aria-hidden="true" />
            <span>{file ? file.name : "Choose the HR report"}</span>
            <input type="file" accept=".xlsx,.csv" onChange={(event: ChangeEvent<HTMLInputElement>) => { setFile(event.target.files?.[0] ?? null); setPreview(null); }} />
          </label>
          <button type="button" className={shared.primary} disabled={!file || busy !== ""} onClick={() => void send("preview")}>{busy === "preview" ? "Checking" : "Preview changes"}</button>
        </section>
      </div>

      {preview ? <section className={styles.previewCard} aria-labelledby="preview-title" data-status={preview.status}>
        <header><h2 id="preview-title">{preview.status === "previewed" ? `What ${preview.file_name} will change` : `${preview.file_name} was not applied`}</h2><RunStatus status={preview.status} /></header>
        {preview.report.message ? <p className={styles.blocked}><AlertTriangle size={16} aria-hidden="true" />{preview.report.message}</p> : null}
        <RunReport run={preview} />
        <div className={styles.previewActions}>
          {preview.status === "previewed" ? <button type="button" className={shared.primary} onClick={() => void send("apply")} disabled={busy !== ""}>{busy === "apply" ? "Applying" : "Apply these changes"}</button> : null}
          {preview.status === "rejected" && preview.summary.rows ? <button type="button" className={styles.danger} onClick={() => void send("apply", true)} disabled={busy !== ""}>Apply anyway</button> : null}
          <button type="button" className={styles.secondary} onClick={() => { setPreview(null); setFile(null); }}>Cancel</button>
        </div>
      </section> : null}

      <section className={register.surface} aria-labelledby="runs-title">
        <div className={register.toolbar}><h2 id="runs-title" className={styles.sectionTitle}>Recent files</h2></div>
        {runs.length ? <div className={shared.tableWrap}><table className={register.table}>
          <thead><tr><th>File</th><th>Source</th><th>Result</th><th>Changes</th><th>When</th><th><span className={styles.srOnly}>Details</span></th></tr></thead>
          <tbody>{runs.map((run) => <tr key={run.id}>
            <td><strong>{run.file_name}</strong></td>
            <td>{run.source === "sftp" ? "SFTP" : run.source === "inbox" ? "Inbox folder" : "Upload"}</td>
            <td><RunStatus status={run.status} /></td>
            <td className={styles.changes}>{run.status === "applied" || run.status === "previewed" ? `${run.summary.new ?? 0} new · ${run.summary.changed ?? 0} changed · ${run.summary.leaving ?? 0} left${run.summary.rerouted ? ` · ${run.summary.rerouted} re-routed` : ""}` : run.report.message ?? ""}</td>
            <td>{dateTime.format(new Date(run.created_at))}</td>
            <td><div className={register.actions}><button type="button" onClick={() => setOpenRun(run)}>Details</button></div></td>
          </tr>)}</tbody>
        </table></div> : <p className={styles.empty}>No HR files have been processed yet.</p>}
      </section>

      <section className={`${register.surface} ${styles.employees}`} aria-labelledby="employees-title">
        <div className={register.toolbar}>
          <h2 id="employees-title" className={styles.sectionTitle}>Employees</h2>
          <label className={styles.searchBox}><Search size={15} aria-hidden="true" /><span className={styles.srOnly}>Search employees</span><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Name, ID, email or department" /></label>
        </div>
        {employees.length ? <div className={shared.tableWrap}><table className={register.table}>
          <thead><tr><th>Employee</th><th>Department</th><th>Reporting manager</th><th>Head of department</th><th>Status</th></tr></thead>
          <tbody>{employees.map((employee) => <tr key={employee.employee_id} data-inactive={employee.status !== "active"}>
            <td><strong>{employee.display_name}</strong><small className={styles.sub}>{employee.employee_id}{employee.email ? ` · ${employee.email}` : " · no email"}</small></td>
            <td>{employee.department || "—"}<small className={styles.sub}>{[employee.location, employee.sub_department].filter(Boolean).join(" · ")}</small></td>
            <td>{employee.manager_name ?? "—"}</td>
            <td>{employee.hod_name ?? "—"}</td>
            <td><div className={styles.statusCell}>{employee.status === "active" ? <StatusPill tone="success">Active</StatusPill> : employee.status === "missing" ? <StatusPill tone="warning">Missing once</StatusPill> : <StatusPill icon={<CircleSlash size={14} aria-hidden="true" />}>Left</StatusPill>}{employee.has_account ? <StatusPill tone="info">Has account</StatusPill> : null}</div></td>
          </tr>)}</tbody>
        </table></div> : <p className={styles.empty}>{query ? "No employees match this search." : "The directory is empty until the first HR file is applied."}</p>}
      </section>

      <SidePanel open={Boolean(openRun)} onClose={() => setOpenRun(null)} title={openRun?.file_name ?? "Run"} description={openRun ? `${openRun.source === "sftp" ? "SFTP" : openRun.source === "inbox" ? "Inbox folder" : "Upload"} · ${dateTime.format(new Date(openRun.created_at))}` : undefined}>
        {openRun ? <div className={styles.runDetail}><RunStatus status={openRun.status} />{openRun.report.message ? <p className={styles.blocked}>{openRun.report.message}</p> : null}<RunReport run={openRun} /></div> : null}
      </SidePanel>

      <SidePanel open={Boolean(settingsDraft)} onClose={() => setSettingsDraft(null)} title="HR directory settings" description="These apply to every HR file from now on.">
        {settingsDraft ? <form className={shared.form} onSubmit={(event) => void saveSettings(event)}>
          <label className={styles.toggle}><input type="checkbox" checked={settingsDraft.invite_new_employees} onChange={(event) => setSettingsDraft({ ...settingsDraft, invite_new_employees: event.target.checked })} /><span><strong>Invite every employee in the file</strong><small>Off: only reporting managers and heads of department are invited, because approvals depend on them. Turn on when you are ready for a full rollout.</small></span></label>
          <div className={shared.field}><label htmlFor="domains">Company email domains</label><input id="domains" value={settingsDraft.domainsText} onChange={(event) => setSettingsDraft({ ...settingsDraft, domainsText: event.target.value })} placeholder="dishmangroup.com, imdcal.com" /><small className={styles.sub}>Only these domains get accounts. Leave empty to allow any domain.</small></div>
          <div className={shared.field}><label htmlFor="drop">Block a file if more than this % of employees disappear</label><input id="drop" type="number" min={1} max={100} value={settingsDraft.max_drop_percent} onChange={(event) => setSettingsDraft({ ...settingsDraft, max_drop_percent: Number(event.target.value) })} /><small className={styles.sub}>Protects against a truncated export deactivating people. Blocked files can still be applied by hand.</small></div>
          <button type="submit" className={shared.primary} disabled={busy !== ""}>Save settings</button>
        </form> : null}
      </SidePanel>
    </AdminShell>
  );
}

function PeopleList({ title, people, detail }: { title: string; people?: Person[]; detail?: (person: Person) => string | undefined }) {
  if (!people?.length) return null;
  return <details className={styles.group} open={people.length <= 8}>
    <summary>{title} <span>{people.length}</span></summary>
    <ul>{people.map((person) => <li key={`${title}-${person.employee_id}`}><strong>{person.name}</strong><small>{person.employee_id}{detail?.(person) ? ` · ${detail(person)}` : ""}</small></li>)}</ul>
  </details>;
}

function RunReport({ run }: { run: Run }) {
  const report = run.report;
  const nothing = !report.new?.length && !report.changed?.length && !report.missing?.length && !report.leaving?.length && !report.issues?.length && !report.invited?.length && !report.reroutes?.length && !report.review?.length;
  return <div className={styles.report}>
    {run.summary.rows !== undefined ? <p className={styles.counts}>{run.summary.rows} rows · {run.summary.unchanged ?? 0} unchanged · {run.summary.new ?? 0} new · {run.summary.changed ?? 0} changed · {run.summary.returning ?? 0} returning · {run.summary.missing ?? 0} missing · {run.summary.leaving ?? 0} leaving</p> : null}
    <PeopleList title="New employees" people={report.new} />
    <PeopleList title="Changed" people={report.changed} detail={(person) => person.fields?.join(", ")} />
    <PeopleList title="Missing for the first time (no action yet)" people={report.missing} />
    <PeopleList title="Left: access removed" people={report.leaving} />
    <PeopleList title="Invited" people={report.invited} detail={(person) => person.reason === "approver" ? "approver" : undefined} />
    <PeopleList title="Deactivated" people={report.deactivated} />
    <PeopleList title="Needs your review" people={report.review} detail={(person) => person.reason} />
    {report.email_changes?.length ? <details className={styles.group} open><summary>Email changed for an existing account <span>{report.email_changes.length}</span></summary><ul>{report.email_changes.map((change) => <li key={change.name}><strong>{change.name}</strong><small>{change.from} → {change.to}. The account keeps signing in with the old address.</small></li>)}</ul></details> : null}
    {report.reroutes?.length ? <details className={styles.group} open><summary>Approvals re-routed <span>{report.reroutes.length}</span></summary><ul>{report.reroutes.map((note) => <li key={note}><small>{note}</small></li>)}</ul></details> : null}
    {report.issues?.length ? <details className={styles.group}><summary>Rows with issues <span>{report.issues.length}</span></summary><ul>{report.issues.map((issue, index) => <li key={`${issue.line}-${index}`} data-severity={issue.severity}><strong>Row {issue.line}{issue.employee_id ? ` · ${issue.employee_id}` : ""}</strong><small>{issue.message}</small></li>)}</ul></details> : null}
    {nothing && run.status === "previewed" ? <p className={styles.counts}>Nothing would change.</p> : null}
  </div>;
}
