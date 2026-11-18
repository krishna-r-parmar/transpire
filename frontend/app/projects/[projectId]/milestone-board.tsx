"use client";

import { ArrowDown, ArrowUp, CalendarRange, Check, ClipboardList, Flag, List, Plus, Trash2, Undo2, X } from "lucide-react";
import { useCallback, useEffect, useId, useMemo, useState, type ReactNode } from "react";
import { SidePanel } from "@/components/admin/side-panel";
import { apiRequest } from "@/lib/api";
import styles from "./milestone-board.module.css";

type Task = { id: string; title: string; owner_name: string; owner_user_id: string | null; due_date: string | null; status: string };
export type BoardMilestone = {
  id: string; position: number; title: string; owner_name: string; owner_user_id: string | null;
  planned_start: string | null; planned_end: string | null; actual_start: string | null; actual_end: string | null;
  weight: string; progress: string; status: string; completion_criteria: string; evidence: string; actions: Task[];
  baseline_planned_end?: string | null; baseline_weight?: string | null; benefits_start?: boolean; variance_days?: number | null;
};
type Person = { user_id: string; display_name: string };
export type BoardProject = {
  id: string; progress: string; start_date: string | null; target_completion_date: string | null; baseline_version: number;
  milestones: BoardMilestone[]; can_manage_plan: boolean; owner_candidates: Person[];
};
type Toast = { text: string; undo?: () => Promise<void> };

const statuses = [
  { value: "not_started", label: "Not started" }, { value: "in_progress", label: "In progress" },
  { value: "blocked", label: "Blocked" }, { value: "complete", label: "Complete" },
];

/** Milestones as compact rows. Every change saves on its own; details open in a side panel. */
export function MilestoneBoard<P extends BoardProject>({ project, onChange }: { project: P; onChange: (project: P) => void }) {
  const [view, setView] = useState<"list" | "timeline">("list");
  const [openId, setOpenId] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);
  const [completing, setCompleting] = useState<BoardMilestone | null>(null);
  const [toast, setToast] = useState<Toast | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const editable = project.can_manage_plan;
  const open = project.milestones.find((milestone) => milestone.id === openId) ?? null;

  useEffect(() => { if (!toast) return; const timer = window.setTimeout(() => setToast(null), 6000); return () => window.clearTimeout(timer); }, [toast]);

  /** Send one change; on success the whole project comes back so totals stay right. */
  const send = useCallback(async (method: string, path: string, body?: unknown): Promise<boolean> => {
    setBusy(true); setError("");
    try {
      const response = await apiRequest(`/projects/${project.id}${path}`, { method, body: body === undefined ? undefined : JSON.stringify(body) });
      const payload = await response.json().catch(() => null) as P | { detail?: unknown } | null;
      if (!response.ok) throw new Error(typeof (payload as { detail?: unknown } | null)?.detail === "string" ? (payload as { detail: string }).detail : "That change didn't save. Try again.");
      onChange(payload as P);
      return true;
    } catch (caught) { setError(caught instanceof Error ? caught.message : "That change didn't save. Try again."); return false; }
    finally { setBusy(false); }
  }, [onChange, project.id]);

  const patch = useCallback((milestone: BoardMilestone, changes: Record<string, unknown>, label?: string) => {
    const before = Object.fromEntries(Object.keys(changes).map((key) => [key, (milestone as unknown as Record<string, unknown>)[key]]));
    // Status changes also fill progress and dates; Undo puts those back too.
    if ("status" in changes || "progress" in changes) Object.assign(before, { status: milestone.status, progress: Number(milestone.progress), actual_start: milestone.actual_start, actual_end: milestone.actual_end });
    return send("PATCH", `/milestones/${milestone.id}`, changes).then((ok) => {
      if (ok && label) setToast({ text: label, undo: async () => { await send("PATCH", `/milestones/${milestone.id}`, before); setToast({ text: "Change undone" }); } });
      return ok;
    });
  }, [send]);

  const setStatus = (milestone: BoardMilestone, status: string) => {
    if (status === milestone.status) return;
    if (status === "complete") { setCompleting(milestone); return; }
    void patch(milestone, { status }, `"${milestone.title}" is now ${statuses.find((item) => item.value === status)?.label.toLowerCase()}`);
  };

  const completeCount = project.milestones.filter((milestone) => milestone.status === "complete").length;

  return <section className={styles.board} aria-labelledby="milestones-heading">
    <header className={styles.head}>
      <div><h2 id="milestones-heading">Milestones</h2><p>{project.milestones.length ? `${Math.round(Number(project.progress))}% complete · ${completeCount} of ${project.milestones.length} milestones done` : "No milestones yet"}</p></div>
      <div className={styles.headActions}>
        <div className={styles.toggle} role="group" aria-label="View">
          <button type="button" aria-pressed={view === "list"} onClick={() => setView("list")}><List size={15} aria-hidden="true" />List</button>
          <button type="button" aria-pressed={view === "timeline"} onClick={() => setView("timeline")}><CalendarRange size={15} aria-hidden="true" />Timeline</button>
        </div>
        {editable ? <button type="button" className={styles.primary} onClick={() => setAdding(true)}><Plus size={16} aria-hidden="true" />Add milestone</button> : null}
      </div>
    </header>

    {error ? <p className={styles.error} role="alert">{error}<button type="button" aria-label="Dismiss" onClick={() => setError("")}><X size={14} /></button></p> : null}

    {!project.milestones.length ? <div className={styles.empty}><ClipboardList size={22} aria-hidden="true" /><p>{editable ? "Add the first milestone to start tracking delivery." : "The project lead hasn't added milestones yet."}</p></div>
      : view === "list" ? <ol className={styles.list}>
        {project.milestones.map((milestone) => <MilestoneRow key={milestone.id} milestone={milestone} editable={editable} busy={busy} onOpen={() => setOpenId(milestone.id)} onStatus={(status) => setStatus(milestone, status)} />)}
      </ol>
      : <Timeline project={project} onOpen={setOpenId} />}

    {open ? <MilestonePanel key={open.id} milestone={open} project={project} editable={editable} busy={busy} onClose={() => setOpenId(null)} onPatch={patch} onSend={send} onStatus={(status) => setStatus(open, status)} /> : null}
    {adding ? <AddMilestonePanel project={project} busy={busy} onClose={() => setAdding(false)} onAdd={async (body) => { if (await send("POST", "/milestones", body)) { setAdding(false); setToast({ text: `Added "${body.title}"` }); } }} /> : null}
    {completing ? <CompleteDialog milestone={completing} busy={busy} onClose={() => setCompleting(null)} onConfirm={async (evidence) => { const ok = await patch(completing, { status: "complete", ...(evidence.trim() ? { evidence } : {}) }, `"${completing.title}" is complete`); if (ok) setCompleting(null); }} /> : null}

    <div className={styles.toastSlot} aria-live="polite">{toast ? <div className={styles.toast}><Check size={16} aria-hidden="true" /><span>{toast.text}</span>{toast.undo ? <button type="button" onClick={() => { const undo = toast.undo; setToast(null); void undo?.(); }}><Undo2 size={14} aria-hidden="true" />Undo</button> : null}</div> : null}</div>
  </section>;
}

function MilestoneRow({ milestone, editable, busy, onOpen, onStatus }: { milestone: BoardMilestone; editable: boolean; busy: boolean; onOpen: () => void; onStatus: (status: string) => void }) {
  const progress = Math.round(Number(milestone.progress));
  const done = milestone.actions.filter((task) => task.status === "complete").length;
  return <li className={styles.row} data-status={milestone.status}>
    <button type="button" className={styles.rowMain} onClick={onOpen} aria-label={`Open ${milestone.title}`}>
      <span className={styles.position} aria-hidden="true">{milestone.status === "complete" ? <Check size={14} /> : milestone.position}</span>
      <span className={styles.rowText}>
        <strong>{milestone.title}</strong>
        <span className={styles.meta}>
          {milestone.owner_name ? <span>{milestone.owner_name}</span> : <span className={styles.muted}>Unassigned</span>}
          {milestone.planned_end ? <span>Due {formatDate(milestone.planned_end)}</span> : null}
          {milestone.actions.length ? <span>{done} of {milestone.actions.length} tasks</span> : null}
          {milestone.benefits_start ? <span className={styles.badge} data-tone="success">Benefits start</span> : null}
          <Variance days={milestone.variance_days} />
        </span>
        <span className={styles.progress}><span className={styles.bar} aria-hidden="true"><i style={{ width: `${progress}%` }} /></span><span>{progress}%</span></span>
      </span>
    </button>
    <div className={styles.rowStatus}>
      {editable ? <StatusSelect value={milestone.status} disabled={busy} label={`Status of ${milestone.title}`} onChange={onStatus} /> : <span className={styles.statusPill} data-status={milestone.status}>{statuses.find((item) => item.value === milestone.status)?.label ?? milestone.status}</span>}
    </div>
  </li>;
}

function StatusSelect({ value, label, disabled, onChange }: { value: string; label: string; disabled: boolean; onChange: (value: string) => void }) {
  return <select className={styles.statusSelect} data-status={value} aria-label={label} value={value} disabled={disabled} onChange={(event) => onChange(event.target.value)}>
    {statuses.map((status) => <option key={status.value} value={status.value}>{status.label}</option>)}
  </select>;
}

function Variance({ days }: { days?: number | null }) {
  if (!days) return null;
  return <span className={styles.badge} data-tone={days > 0 ? "warning" : "success"} title="Compared with the submitted charter">{days > 0 ? `${days} days later than charter` : `${Math.abs(days)} days earlier than charter`}</span>;
}

/* ---------- Side panel for one milestone ---------- */

function MilestonePanel({ milestone, project, editable, busy, onClose, onPatch, onSend, onStatus }: {
  milestone: BoardMilestone; project: BoardProject; editable: boolean; busy: boolean; onClose: () => void;
  onPatch: (milestone: BoardMilestone, changes: Record<string, unknown>, label?: string) => Promise<boolean>;
  onSend: (method: string, path: string, body?: unknown) => Promise<boolean>; onStatus: (status: string) => void;
}) {
  const baselined = Boolean(milestone.baseline_planned_end);
  const [plan, setPlan] = useState({ title: milestone.title, planned_end: milestone.planned_end ?? "", weight: String(Number(milestone.weight)) });
  const [reason, setReason] = useState("");
  const [removing, setRemoving] = useState(false);
  const [newTask, setNewTask] = useState("");
  const planChanged = plan.title.trim() !== milestone.title || (plan.planned_end || null) !== milestone.planned_end || Number(plan.weight) !== Number(milestone.weight);
  const progress = Math.round(Number(milestone.progress));
  const reasonId = useId();

  const savePlan = async () => {
    const changes: Record<string, unknown> = {};
    if (plan.title.trim() !== milestone.title) changes.title = plan.title.trim();
    if ((plan.planned_end || null) !== milestone.planned_end) changes.planned_end = plan.planned_end || null;
    if (Number(plan.weight) !== Number(milestone.weight)) changes.weight = Number(plan.weight);
    if (await onPatch(milestone, { ...changes, reason }, baselined ? "Plan change recorded" : "Saved")) setReason("");
  };
  const saveField = (field: string, value: unknown, current: unknown) => { if ((value ?? null) !== (current ?? null)) void onPatch(milestone, { [field]: value }, "Saved"); };

  return <SidePanel open title={milestone.title} description={baselined ? `Charter baseline: due ${formatDate(milestone.baseline_planned_end ?? null)} · ${Number(milestone.baseline_weight ?? milestone.weight)}% weight` : "Added after the charter was submitted"} onClose={onClose}>
    <div className={styles.panel}>
      <PanelSection title="Progress">
        <div className={styles.quickRow}>
          {editable ? <StatusSelect value={milestone.status} disabled={busy} label="Status" onChange={onStatus} /> : null}
          <div className={styles.quick} role="group" aria-label="Progress">
            {[0, 25, 50, 75, 100].map((value) => <button key={value} type="button" disabled={!editable || busy} aria-pressed={progress === value} onClick={() => void onPatch(milestone, { progress: value }, `Progress set to ${value}%`)}>{value}%</button>)}
          </div>
        </div>
        <span className={styles.progress}><span className={styles.bar} aria-hidden="true"><i style={{ width: `${progress}%` }} /></span><span>{progress}%</span></span>
      </PanelSection>

      <PanelSection title="Tasks" hint={milestone.actions.length ? `${milestone.actions.filter((task) => task.status === "complete").length} of ${milestone.actions.length} done` : undefined}>
        <ul className={styles.tasks}>
          {milestone.actions.map((task) => <li key={task.id} data-done={task.status === "complete"}>
            <label><input type="checkbox" checked={task.status === "complete"} disabled={!editable || busy} onChange={(event) => void onSend("PATCH", `/milestones/${milestone.id}/tasks/${task.id}`, { status: event.target.checked ? "complete" : "not_started" })} /><span>{task.title}</span></label>
            {task.owner_name || task.due_date ? <small>{[task.owner_name, task.due_date ? `due ${formatDate(task.due_date)}` : ""].filter(Boolean).join(" · ")}</small> : null}
            {editable ? <button type="button" aria-label={`Delete task ${task.title}`} disabled={busy} onClick={() => void onSend("DELETE", `/milestones/${milestone.id}/tasks/${task.id}`)}><X size={14} /></button> : null}
          </li>)}
        </ul>
        {editable ? <form className={styles.addTask} onSubmit={(event) => { event.preventDefault(); if (!newTask.trim()) return; void onSend("POST", `/milestones/${milestone.id}/tasks`, { title: newTask.trim() }).then((ok) => { if (ok) setNewTask(""); }); }}>
          <input value={newTask} maxLength={500} placeholder="Add a task and press Enter" aria-label="New task" onChange={(event) => setNewTask(event.target.value)} />
          <button type="submit" disabled={busy || !newTask.trim()}><Plus size={15} aria-hidden="true" />Add</button>
        </form> : milestone.actions.length ? null : <p className={styles.muted}>No tasks yet.</p>}
      </PanelSection>

      <PanelSection title="Plan" hint={baselined ? "Changes here are compared with the charter. Say why they changed." : undefined}>
        <label className={styles.field}><span>Milestone</span><input value={plan.title} disabled={!editable} maxLength={200} onChange={(event) => setPlan({ ...plan, title: event.target.value })} /></label>
        <div className={styles.two}>
          <label className={styles.field}><span>Due date</span><input type="date" value={plan.planned_end} disabled={!editable} onChange={(event) => setPlan({ ...plan, planned_end: event.target.value })} /></label>
          <label className={styles.field}><span>Weight (%)</span><input type="number" min="0" max="100" step="5" value={plan.weight} disabled={!editable} onChange={(event) => setPlan({ ...plan, weight: event.target.value })} /></label>
        </div>
        {planChanged ? <div className={styles.reason}>
          {baselined ? <label className={styles.field} htmlFor={reasonId}><span>Why is the plan changing?</span><textarea id={reasonId} rows={2} maxLength={500} value={reason} placeholder="Supplier delivery moved by two weeks." onChange={(event) => setReason(event.target.value)} /></label> : null}
          <div><button type="button" className={styles.primary} disabled={busy || !plan.title.trim() || (baselined && !reason.trim())} onClick={() => void savePlan()}>Save plan change</button><button type="button" className={styles.secondary} onClick={() => { setPlan({ title: milestone.title, planned_end: milestone.planned_end ?? "", weight: String(Number(milestone.weight)) }); setReason(""); }}>Cancel</button></div>
        </div> : null}
        <label className={styles.field}><span>Owner</span>
          <select value={milestone.owner_user_id ?? ""} disabled={!editable || busy} onChange={(event) => void onPatch(milestone, { owner_user_id: event.target.value || null }, "Owner updated")}>
            <option value="">Unassigned</option>
            {project.owner_candidates.map((person) => <option key={person.user_id} value={person.user_id}>{person.display_name}</option>)}
          </select>
        </label>
        <label className={styles.check}><input type="checkbox" checked={Boolean(milestone.benefits_start)} disabled={!editable || busy} onChange={(event) => void onPatch(milestone, { benefits_start: event.target.checked }, event.target.checked ? "Benefits now start after this milestone" : "Saved")} />Benefits start after this milestone</label>
      </PanelSection>

      <PanelSection title="Dates and evidence">
        <div className={styles.two}>
          <label className={styles.field}><span>Started</span><input type="date" defaultValue={milestone.actual_start ?? ""} disabled={!editable} onBlur={(event) => saveField("actual_start", event.target.value || null, milestone.actual_start)} /></label>
          <label className={styles.field}><span>Finished</span><input type="date" defaultValue={milestone.actual_end ?? ""} disabled={!editable} onBlur={(event) => saveField("actual_end", event.target.value || null, milestone.actual_end)} /></label>
        </div>
        <label className={styles.field}><span>Done when</span><textarea rows={2} defaultValue={milestone.completion_criteria} disabled={!editable} maxLength={2000} placeholder="Pre-heater runs at target temperature for two weeks." onBlur={(event) => saveField("completion_criteria", event.target.value, milestone.completion_criteria)} /></label>
        <label className={styles.field}><span>Evidence</span><textarea rows={2} defaultValue={milestone.evidence} disabled={!editable} maxLength={4000} placeholder="Trial log, photos, or a document reference." onBlur={(event) => saveField("evidence", event.target.value, milestone.evidence)} /></label>
        {editable ? <p className={styles.muted}>Dates and text save when you leave the field.</p> : null}
      </PanelSection>

      {editable ? <PanelSection title="Arrange">
        <div className={styles.arrange}>
          <button type="button" className={styles.secondary} disabled={busy || milestone.position === 1} onClick={() => void onSend("POST", `/milestones/${milestone.id}/move`, { direction: "up" })}><ArrowUp size={15} aria-hidden="true" />Move up</button>
          <button type="button" className={styles.secondary} disabled={busy || milestone.position === project.milestones.length} onClick={() => void onSend("POST", `/milestones/${milestone.id}/move`, { direction: "down" })}><ArrowDown size={15} aria-hidden="true" />Move down</button>
          <button type="button" className={styles.danger} disabled={busy} onClick={() => setRemoving(true)}><Trash2 size={15} aria-hidden="true" />Remove</button>
        </div>
        {removing ? <RemoveConfirm baselined={baselined} busy={busy} onCancel={() => setRemoving(false)} onConfirm={async (why) => { if (await onSend("DELETE", `/milestones/${milestone.id}?reason=${encodeURIComponent(why)}`)) onClose(); }} /> : null}
      </PanelSection> : null}
    </div>
  </SidePanel>;
}

function RemoveConfirm({ baselined, busy, onCancel, onConfirm }: { baselined: boolean; busy: boolean; onCancel: () => void; onConfirm: (reason: string) => void }) {
  const [why, setWhy] = useState("");
  return <div className={styles.reason}>
    <p>{baselined ? "This milestone is part of the submitted charter. Removing it is recorded with your reason." : "Remove this milestone and its tasks?"}</p>
    {baselined ? <label className={styles.field}><span>Why remove it?</span><textarea rows={2} maxLength={500} value={why} onChange={(event) => setWhy(event.target.value)} /></label> : null}
    <div><button type="button" className={styles.danger} disabled={busy || (baselined && !why.trim())} onClick={() => onConfirm(why.trim())}>Remove milestone</button><button type="button" className={styles.secondary} onClick={onCancel}>Keep it</button></div>
  </div>;
}

function AddMilestonePanel({ project, busy, onClose, onAdd }: { project: BoardProject; busy: boolean; onClose: () => void; onAdd: (body: { title: string; owner_user_id: string | null; planned_end: string | null; weight: number; reason: string }) => void }) {
  const [form, setForm] = useState({ title: "", owner_user_id: "", planned_end: "", weight: "0", reason: "" });
  const afterBaseline = project.baseline_version >= 1;
  const total = project.milestones.reduce((sum, milestone) => sum + Number(milestone.weight), 0);
  return <SidePanel open title="Add a milestone" description={afterBaseline ? "The charter is locked, so this is recorded as a plan change." : undefined} onClose={onClose}>
    <form className={styles.panel} onSubmit={(event) => { event.preventDefault(); onAdd({ title: form.title.trim(), owner_user_id: form.owner_user_id || null, planned_end: form.planned_end || null, weight: Number(form.weight || 0), reason: form.reason.trim() }); }}>
      <label className={styles.field}><span>Milestone</span><input value={form.title} maxLength={200} required placeholder="What will be true when this is done?" onChange={(event) => setForm({ ...form, title: event.target.value })} /></label>
      <label className={styles.field}><span>Owner</span><select value={form.owner_user_id} onChange={(event) => setForm({ ...form, owner_user_id: event.target.value })}><option value="">Unassigned</option>{project.owner_candidates.map((person) => <option key={person.user_id} value={person.user_id}>{person.display_name}</option>)}</select></label>
      <div className={styles.two}>
        <label className={styles.field}><span>Due date</span><input type="date" value={form.planned_end} onChange={(event) => setForm({ ...form, planned_end: event.target.value })} /></label>
        <label className={styles.field}><span>Weight (%)</span><input type="number" min="0" max={100 - total} step="5" value={form.weight} onChange={(event) => setForm({ ...form, weight: event.target.value })} /><small className={styles.muted}>{100 - total}% of the plan is unweighted.</small></label>
      </div>
      {afterBaseline ? <label className={styles.field}><span>Why add it?</span><textarea rows={2} maxLength={500} required value={form.reason} placeholder="Commissioning needs a separate safety sign-off." onChange={(event) => setForm({ ...form, reason: event.target.value })} /></label> : null}
      <div className={styles.arrange}><button type="submit" className={styles.primary} disabled={busy || !form.title.trim() || (afterBaseline && !form.reason.trim())}><Plus size={16} aria-hidden="true" />Add milestone</button><button type="button" className={styles.secondary} onClick={onClose}>Cancel</button></div>
    </form>
  </SidePanel>;
}

function CompleteDialog({ milestone, busy, onClose, onConfirm }: { milestone: BoardMilestone; busy: boolean; onClose: () => void; onConfirm: (evidence: string) => void }) {
  const [evidence, setEvidence] = useState(milestone.evidence);
  return <SidePanel open title={`Complete "${milestone.title}"`} description="Progress will be set to 100% and today recorded as the finish date." onClose={onClose}>
    <form className={styles.panel} onSubmit={(event) => { event.preventDefault(); onConfirm(evidence); }}>
      <label className={styles.field}><span>Evidence <em className={styles.muted}>Optional</em></span><textarea rows={3} maxLength={4000} value={evidence} placeholder="Trial log, photos, or a document reference." onChange={(event) => setEvidence(event.target.value)} /></label>
      <div className={styles.arrange}><button type="submit" className={styles.primary} disabled={busy}><Check size={16} aria-hidden="true" />Mark complete</button><button type="button" className={styles.secondary} onClick={onClose}>Cancel</button></div>
    </form>
  </SidePanel>;
}

function PanelSection({ title, hint, children }: { title: string; hint?: string; children: ReactNode }) {
  return <section className={styles.panelSection}><header><h3>{title}</h3>{hint ? <span>{hint}</span> : null}</header>{children}</section>;
}

/* ---------- Timeline ---------- */

function Timeline({ project, onOpen }: { project: BoardProject; onOpen: (id: string) => void }) {
  const range = useMemo(() => {
    const days = project.milestones.flatMap((milestone) => [milestone.planned_start, milestone.planned_end, milestone.baseline_planned_end, milestone.actual_end]).filter(Boolean).map((value) => day(value as string));
    const start = project.start_date ? day(project.start_date) : Math.min(...days);
    const end = Math.max(project.target_completion_date ? day(project.target_completion_date) : 0, ...days);
    return { start, span: Math.max(1, end - start) };
  }, [project]);
  const at = (value: string | null | undefined) => value ? Math.min(100, Math.max(0, ((day(value) - range.start) / range.span) * 100)) : null;
  const today = at(new Date().toISOString().slice(0, 10));
  return <div className={styles.timeline}>
    {today !== null && today > 0 && today < 100 ? <span className={styles.today} style={{ left: `calc(12rem + (100% - 12rem) * ${today / 100})` }}><em>Today</em></span> : null}
    {project.milestones.map((milestone, index) => {
      const startAt = at(milestone.planned_start ?? project.milestones[index - 1]?.planned_end ?? project.start_date) ?? 0;
      const endAt = at(milestone.planned_end) ?? startAt;
      const baselineAt = at(milestone.baseline_planned_end);
      return <button key={milestone.id} type="button" className={styles.timelineRow} onClick={() => onOpen(milestone.id)}>
        <span className={styles.timelineLabel}><strong>{milestone.title}</strong><small>{milestone.planned_end ? formatDate(milestone.planned_end) : "No due date"}</small></span>
        <span className={styles.track}>
          <i className={styles.span} data-status={milestone.status} style={{ left: `${startAt}%`, width: `${Math.max(1.5, endAt - startAt)}%` }} />
          {baselineAt !== null && baselineAt !== endAt ? <i className={styles.baseline} style={{ left: `${baselineAt}%` }} title={`Charter due ${formatDate(milestone.baseline_planned_end ?? null)}`} /> : null}
          {milestone.benefits_start ? <Flag className={styles.flag} size={13} style={{ left: `${endAt}%` }} aria-label="Benefits start" /> : null}
        </span>
      </button>;
    })}
    <p className={styles.legend}><i className={styles.legendBar} />Planned<i className={styles.legendBaseline} />Charter due date<Flag size={12} aria-hidden="true" />Benefits start</p>
  </div>;
}

function day(value: string) { return Math.floor(new Date(`${value.slice(0, 10)}T00:00:00`).getTime() / 864e5); }
function formatDate(value: string | null) { return value ? new Intl.DateTimeFormat("en-IN", { day: "numeric", month: "short", year: "numeric" }).format(new Date(`${value.slice(0, 10)}T00:00:00`)) : "Not set"; }
