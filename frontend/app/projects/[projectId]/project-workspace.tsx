"use client";

import {
  Activity,
  ArrowDown,
  ArrowLeft,
  ArrowUp,
  BarChart3,
  CheckCircle2,
  ClipboardList,
  FileClock,
  Flag,
  FolderKanban,
  Plus,
  RefreshCw,
  ShieldCheck,
  Save,
  Target,
  Trash2,
  Users,
} from "lucide-react";
import { TenantLink as Link } from "@/components/app/tenant-link";
import { useTenantRouter as useRouter } from "@/lib/use-tenant-router";
import { useCallback, useEffect, useState } from "react";
import { AdminShell } from "@/components/admin/admin-shell";
import { SelectField } from "@/components/ui/select-field";
import { apiRequest } from "@/lib/api";
import { useSession } from "@/lib/use-session";
import { formatLakhs } from "../projects-portfolio-utils";
import styles from "./project-workspace.module.css";

type ActionRecord = {
  id: string; title: string; owner_name: string; due_date: string | null;
  owner_user_id: string | null; completed_at: string | null; status: string; notes: string;
};
type MilestoneRecord = {
  id: string; position: number; title: string; outcome: string; owner_name: string;
  owner_user_id: string | null;
  planned_start: string | null; planned_end: string | null; actual_start: string | null;
  actual_end: string | null; weight: string; progress: string; status: string;
  completion_criteria: string; actions: ActionRecord[];
  evidence: string; dependency_ids: string[];
};
type BenefitPeriod = {
  month: string; plan: string; achieved: string; line_of_sight: string;
  kpi_actual: string | null; status: string; finance_approved: boolean;
};
type ProjectWorkspaceRecord = {
  id: string; idea_id: string; reference: string; idea_reference: string; title: string;
  idea_type: string; project_category: string | null; project_subtype: string | null;
  status: string; health: string; lead_name: string; site: string | null;
  department: string | null; start_date: string | null; target_completion_date: string | null;
  baseline_version: number; progress: string; target: string; achieved: string;
  validated: string; line_of_sight: string; projected_outcome: string; updated_at: string;
  charter: {
    sponsor: string; leader: string; start_date: string | null; target_completion_date: string | null;
    team_members: string[]; in_scope: string; out_of_scope: string; objective: string;
    benefit_type: string; kpi_name: string; budget_approved: string | null;
    impact_areas: string[]; belt_level: string | null;
    action_items: Array<Record<string, unknown>>;
  };
  benefit_periods: BenefitPeriod[];
  milestones: MilestoneRecord[];
  team: Array<{ id: string; name: string; email: string; status: string; invited_at: string; responded_at: string | null }>;
  baselines: Array<{ id: string; version: number; reason: string; created_by_name: string; published_at: string; is_active: boolean }>;
  activity: Array<{ id: string; event_type: string; summary: string; actor_name: string | null; created_at: string }>;
  can_manage_plan: boolean;
  owner_candidates: Array<{ membership_id: string; user_id: string; display_name: string; email: string }>;
};

type Section = "overview" | "milestones" | "benefits" | "charter" | "team" | "activity";

const tabs: Array<{ id: Section; label: string; icon: typeof FolderKanban }> = [
  { id: "overview", label: "Overview", icon: FolderKanban },
  { id: "milestones", label: "Milestones & actions", icon: Flag },
  { id: "benefits", label: "Benefits & LOS", icon: BarChart3 },
  { id: "charter", label: "Charter & revisions", icon: FileClock },
  { id: "team", label: "Team", icon: Users },
  { id: "activity", label: "Activity", icon: Activity },
];

const projectStatuses: Record<string, string> = {
  ready_to_start: "Ready to start", in_progress: "In progress", on_hold: "On hold",
  completion_review: "Completion review", oe_verified: "OE verified",
  finance_validation: "Finance validation", success: "Success", cancelled: "Cancelled",
  unsuccessful: "Closed unsuccessful",
};

export function ProjectWorkspace({ projectId }: { projectId: string }) {
  const router = useRouter();
  const { session, loading: sessionLoading } = useSession();
  const [project, setProject] = useState<ProjectWorkspaceRecord | null>(null);
  const [section, setSection] = useState<Section>(() => {
    if (typeof window === "undefined") return "overview";
    const requested = new URLSearchParams(window.location.search).get("section");
    return tabs.some((tab) => tab.id === requested) ? requested as Section : "overview";
  });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const loadProject = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const response = await apiRequest(`/projects/${projectId}`);
      if (response.status === 401) {
        router.replace("/sign-in");
        return;
      }
      const body = await response.json().catch(() => null) as ProjectWorkspaceRecord | { detail?: string } | null;
      if (!response.ok) throw new Error(body && "detail" in body ? body.detail : "Project could not be loaded.");
      setProject(body as ProjectWorkspaceRecord);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Project could not be loaded.");
    } finally {
      setLoading(false);
    }
  }, [projectId, router]);

  useEffect(() => {
    if (!session) return;
    const timer = window.setTimeout(() => void loadProject(), 0);
    return () => window.clearTimeout(timer);
  }, [loadProject, session]);

  const selectSection = (next: Section) => {
    setSection(next);
    window.history.replaceState(null, "", `?section=${next}`);
  };

  if (sessionLoading || !session) {
    return <main className={styles.loading}>Opening project workspace</main>;
  }

  return (
    <AdminShell
      session={session}
      active="projects"
      eyebrow="Project execution"
      title={project?.reference ?? "Project workspace"}
      description={project?.title ?? "Review the execution baseline and current delivery record."}
    >
      {loading ? <WorkspaceSkeleton /> : null}
      {error ? (
        <section className={styles.error} role="alert">
          <FolderKanban aria-hidden="true" />
          <h2>{error}</h2>
          <p>The project may no longer be available in this tenant, or the service may be temporarily unavailable.</p>
          <div>
            <Link href="/projects"><ArrowLeft aria-hidden="true" size={15} />Projects portfolio</Link>
            <button type="button" onClick={() => void loadProject()}><RefreshCw aria-hidden="true" size={15} />Retry</button>
          </div>
        </section>
      ) : null}

      {!loading && project ? (
        <>
          <div className={styles.workspaceLead}>
            <Link href="/projects"><ArrowLeft aria-hidden="true" size={15} />Projects portfolio</Link>
            <div>
              <span className={styles.status} data-status={project.status}>
                {projectStatuses[project.status] ?? project.status}
              </span>
              <span>{healthLabel(project.health)}</span>
              <span>Baseline v{project.baseline_version}</span>
              <Link href={`/ideas/${project.idea_id}`}>{project.idea_reference}</Link>
            </div>
          </div>

          <nav className={styles.tabs} aria-label="Project workspace sections">
            {tabs.map((tab) => {
              const Icon = tab.icon;
              return (
                <button
                  key={tab.id}
                  type="button"
                  role="tab"
                  aria-selected={section === tab.id}
                  onClick={() => selectSection(tab.id)}
                >
                  <Icon aria-hidden="true" size={15} />{tab.label}
                </button>
              );
            })}
          </nav>

          <div className={styles.panel} role="tabpanel">
            {section === "overview" ? <Overview project={project} /> : null}
            {section === "milestones" ? <Milestones key={project.updated_at} project={project} onSaved={setProject} /> : null}
            {section === "benefits" ? <Benefits project={project} /> : null}
            {section === "charter" ? <Charter project={project} /> : null}
            {section === "team" ? <Team project={project} /> : null}
            {section === "activity" ? <ActivityPanel project={project} /> : null}
          </div>
        </>
      ) : null}
    </AdminShell>
  );
}

function Overview({ project }: { project: ProjectWorkspaceRecord }) {
  return (
    <div className={styles.overview}>
      <section className={styles.deliveryLedger} aria-label="Delivery summary">
        <Ledger label="Progress" value={`${Number(project.progress).toFixed(0)}%`} detail={`${project.milestones.length} milestones`} />
        <Ledger label="Target" value={formatLakhs(project.target)} detail="Forecast plan" />
        <Ledger label="Achieved" value={formatLakhs(project.achieved)} detail={`${formatLakhs(project.validated)} validated`} />
        <Ledger label="LOS" value={formatLakhs(project.line_of_sight)} detail={`Projected ${formatLakhs(project.projected_outcome)}`} />
      </section>
      <div className={styles.overviewGrid}>
        <section className={styles.brief}>
          <SectionHeading icon={Target} eyebrow="Execution brief" title="Objective and scope" description="The active charter baseline defines what this project is accountable for delivering." />
          <ReadOnly label="SMART objective" value={project.charter.objective} />
          <div className={styles.scopeGrid}>
            <ReadOnly label="In scope" value={project.charter.in_scope} />
            <ReadOnly label="Out of scope" value={project.charter.out_of_scope} />
          </div>
        </section>
        <aside className={styles.facts} aria-label="Project facts">
          <h2>Project facts</h2>
          <dl>
            <Fact label="Project lead" value={project.lead_name} />
            <Fact label="Sponsor" value={project.charter.sponsor} />
            <Fact label="Site" value={project.site} />
            <Fact label="Department" value={project.department} />
            <Fact label="Start" value={formatDate(project.start_date)} />
            <Fact label="Target completion" value={formatDate(project.target_completion_date)} />
            <Fact label="Benefit type" value={labelize(project.charter.benefit_type)} />
            <Fact label="KPI" value={project.charter.kpi_name} />
          </dl>
        </aside>
      </div>
    </div>
  );
}

function Milestones({ project, onSaved }: { project: ProjectWorkspaceRecord; onSaved: (project: ProjectWorkspaceRecord) => void }) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<MilestoneRecord[]>(() => structuredClone(project.milestones));
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");
  const totalWeight = draft.reduce((total, milestone) => total + Number(milestone.weight || 0), 0);

  const updateMilestone = (index: number, field: keyof MilestoneRecord, value: unknown) => {
    setDraft((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, [field]: value } : item));
  };
  const addMilestone = () => setDraft((current) => [...current, {
    id: crypto.randomUUID(), position: current.length + 1, title: "", outcome: "", owner_name: "",
    owner_user_id: null, planned_start: null, planned_end: null, actual_start: null, actual_end: null,
    weight: "0", progress: "0", status: "not_started", completion_criteria: "", evidence: "",
    dependency_ids: [], actions: [],
  }]);
  const removeMilestone = (index: number) => setDraft((current) => {
    const removedId = current[index].id;
    return current.filter((_, itemIndex) => itemIndex !== index).map((item, itemIndex) => ({
      ...item, position: itemIndex + 1, dependency_ids: item.dependency_ids.filter((id) => id !== removedId),
    }));
  });
  const moveMilestone = (index: number, direction: -1 | 1) => setDraft((current) => {
    const target = index + direction;
    if (target < 0 || target >= current.length) return current;
    const next = [...current];
    [next[index], next[target]] = [next[target], next[index]];
    return next.map((item, itemIndex) => ({ ...item, position: itemIndex + 1 }));
  });
  const addAction = (milestoneIndex: number) => setDraft((current) => current.map((item, index) => index === milestoneIndex ? {
    ...item, actions: [...item.actions, { id: crypto.randomUUID(), title: "", owner_name: "", owner_user_id: null, due_date: null, completed_at: null, status: "not_started", notes: "" }],
  } : item));
  const updateAction = (milestoneIndex: number, actionIndex: number, field: keyof ActionRecord, value: unknown) => setDraft((current) => current.map((item, index) => index === milestoneIndex ? {
    ...item, actions: item.actions.map((action, index) => index === actionIndex ? { ...action, [field]: value } : action),
  } : item));
  const savePlan = async () => {
    setMessage("");
    if (totalWeight > 100) { setMessage("Milestone weights cannot total more than 100%."); return; }
    if (draft.some((milestone) => !milestone.title.trim())) { setMessage("Give every milestone a title before saving."); return; }
    setSaving(true);
    try {
      const response = await apiRequest(`/projects/${project.id}/milestones`, {
        method: "PUT",
        body: JSON.stringify({ milestones: draft.map((milestone) => ({ ...milestone, actions: milestone.actions.map((action) => ({ id: action.id, title: action.title, owner_name: action.owner_name, owner_user_id: action.owner_user_id, due_date: action.due_date, status: action.status, notes: action.notes })) })) }),
      });
      const body = await response.json().catch(() => null) as ProjectWorkspaceRecord | { detail?: string } | null;
      if (!response.ok) throw new Error(body && "detail" in body ? body.detail : "The milestone plan could not be saved.");
      onSaved(body as ProjectWorkspaceRecord);
      setEditing(false);
    } catch (caught) { setMessage(caught instanceof Error ? caught.message : "The milestone plan could not be saved."); }
    finally { setSaving(false); }
  };

  return (
    <section>
      <div className={styles.plannerHeading}><SectionHeading icon={Flag} eyebrow="Delivery plan" title="Milestones and nested actions" description="Progress is weighted across outcome-based milestones. Actions sit inside the milestone they support." />{project.can_manage_plan && !editing ? <button type="button" onClick={() => setEditing(true)}>Edit milestone plan</button> : null}</div>
      {message ? <div className={styles.planMessage} role="alert">{message}</div> : null}
      {editing ? <div className={styles.planToolbar}><span>Total weight <strong data-invalid={totalWeight > 100}>{totalWeight}%</strong></span><div><button type="button" onClick={() => { setDraft(structuredClone(project.milestones)); setEditing(false); setMessage(""); }}>Cancel</button><button type="button" onClick={() => void savePlan()} disabled={saving || totalWeight > 100}><Save aria-hidden="true" size={14} />{saving ? "Saving plan" : "Save plan"}</button></div></div> : null}
      {(editing ? draft.length : project.milestones.length) ? (
        <div className={styles.milestones}>
          {(editing ? draft : project.milestones).map((milestone, index) => (
            <article key={milestone.id}>
              <header>
                <span>{String(milestone.position).padStart(2, "0")}</span>
                <div><p>{labelize(milestone.status)}</p>{editing ? <input className={styles.titleInput} aria-label={`Milestone ${index + 1} title`} value={milestone.title} onChange={(event) => updateMilestone(index, "title", event.target.value)} placeholder="Milestone title" /> : <h3>{milestone.title}</h3>}</div>
                <strong>{Number(milestone.progress).toFixed(0)}%</strong>
              </header>
              {editing ? <div className={styles.orderActions}><button type="button" disabled={index === 0} onClick={() => moveMilestone(index, -1)} aria-label={`Move ${milestone.title || `milestone ${index + 1}`} up`}><ArrowUp size={14} /></button><button type="button" disabled={index === draft.length - 1} onClick={() => moveMilestone(index, 1)} aria-label={`Move ${milestone.title || `milestone ${index + 1}`} down`}><ArrowDown size={14} /></button><button type="button" onClick={() => removeMilestone(index)}><Trash2 size={14} />Remove</button></div> : null}
              <div className={styles.progressTrack}><span style={{ width: `${milestone.progress}%` }} /></div>
              {editing ? <MilestoneFields milestone={milestone} index={index} milestones={draft} candidates={project.owner_candidates} onChange={updateMilestone} /> : <dl className={styles.milestoneFacts}>
                <Fact label="Owner" value={milestone.owner_name} />
                <Fact label="Weight" value={`${Number(milestone.weight).toFixed(0)}%`} />
                <Fact label="Planned" value={dateRange(milestone.planned_start, milestone.planned_end)} />
                <Fact label="Outcome" value={milestone.outcome} />
              </dl>}
              {!editing ? <><ReadOnly label="Completion criteria" value={milestone.completion_criteria} />{milestone.evidence ? <ReadOnly label="Evidence" value={milestone.evidence} /> : null}</> : null}
              {editing ? <ActionEditor milestone={milestone} milestoneIndex={index} candidates={project.owner_candidates} onAdd={addAction} onChange={updateAction} onRemove={(actionIndex) => updateMilestone(index, "actions", milestone.actions.filter((_, itemIndex) => itemIndex !== actionIndex))} /> : milestone.actions.length ? <ActionTable actions={milestone.actions} /> : <p className={styles.inlineEmpty}>No actions have been added to this milestone.</p>}
            </article>
          ))}
        </div>
      ) : (
        editing ? <div className={styles.emptyPlan}><p>Add the first outcome-based milestone. Weights across the plan can total up to 100%.</p></div> : <EmptyState icon={ClipboardList} title="The milestone plan has not been created yet." text={`${project.charter.action_items.length} charter action${project.charter.action_items.length === 1 ? " is" : "s are"} preserved in Baseline v${project.baseline_version}. Milestone planning will organise that work into weighted outcomes.`} />
      )}
      {editing ? <button className={styles.addMilestone} type="button" onClick={addMilestone}><Plus aria-hidden="true" size={15} />Add milestone</button> : null}
    </section>
  );
}

function MilestoneFields({ milestone, index, milestones, candidates, onChange }: { milestone: MilestoneRecord; index: number; milestones: MilestoneRecord[]; candidates: ProjectWorkspaceRecord["owner_candidates"]; onChange: (index: number, field: keyof MilestoneRecord, value: unknown) => void }) {
  const setOwner = (value: string) => { const owner = candidates.find((candidate) => candidate.user_id === value); onChange(index, "owner_user_id", value || null); onChange(index, "owner_name", owner?.display_name ?? ""); };
  return <div className={styles.milestoneEditor}><label>Outcome<textarea rows={2} value={milestone.outcome} onChange={(event) => onChange(index, "outcome", event.target.value)} /></label><SelectField id={`milestone-owner-${milestone.id}`} name="owner" label="Owner" value={milestone.owner_user_id ?? ""} onChange={setOwner} options={[{ value: "", label: "Not assigned", description: "Choose from the project team" }, ...candidates.map((candidate) => ({ value: candidate.user_id, label: candidate.display_name, description: candidate.email }))]} /><label>Weight (%)<input type="number" min="0" max="100" value={milestone.weight} onChange={(event) => onChange(index, "weight", event.target.value)} /></label><label>Progress (%)<input type="number" min="0" max="100" value={milestone.progress} onChange={(event) => onChange(index, "progress", event.target.value)} /></label><label>Planned start<input type="date" value={milestone.planned_start ?? ""} onChange={(event) => onChange(index, "planned_start", event.target.value || null)} /></label><label>Planned end<input type="date" value={milestone.planned_end ?? ""} onChange={(event) => onChange(index, "planned_end", event.target.value || null)} /></label><SelectField id={`milestone-status-${milestone.id}`} name="status" label="Status" value={milestone.status} onChange={(value) => onChange(index, "status", value)} options={["not_started", "in_progress", "blocked", "complete"].map((value) => ({ value, label: labelize(value), description: "Delivery state" }))} /><label className={styles.wideField}>Completion criteria<textarea rows={2} value={milestone.completion_criteria} onChange={(event) => onChange(index, "completion_criteria", event.target.value)} /></label><label className={styles.wideField}>Evidence or reference<textarea rows={2} value={milestone.evidence} onChange={(event) => onChange(index, "evidence", event.target.value)} placeholder="Evidence summary, document reference, or approved location" /></label><fieldset className={styles.dependencies}><legend>Dependencies</legend>{milestones.filter((candidate) => candidate.id !== milestone.id).length ? milestones.filter((candidate) => candidate.id !== milestone.id).map((candidate) => <label key={candidate.id}><input type="checkbox" checked={milestone.dependency_ids.includes(candidate.id)} onChange={() => onChange(index, "dependency_ids", milestone.dependency_ids.includes(candidate.id) ? milestone.dependency_ids.filter((id) => id !== candidate.id) : [...milestone.dependency_ids, candidate.id])} />{candidate.title || `Milestone ${candidate.position}`}</label>) : <p>No other milestones available.</p>}</fieldset></div>;
}

function ActionEditor({ milestone, milestoneIndex, candidates, onAdd, onChange, onRemove }: { milestone: MilestoneRecord; milestoneIndex: number; candidates: ProjectWorkspaceRecord["owner_candidates"]; onAdd: (index: number) => void; onChange: (milestoneIndex: number, actionIndex: number, field: keyof ActionRecord, value: unknown) => void; onRemove: (index: number) => void }) {
  return <div className={styles.actionEditor}><header><h4>Nested actions</h4><button type="button" onClick={() => onAdd(milestoneIndex)}><Plus size={14} />Add action</button></header>{milestone.actions.map((action, actionIndex) => <div key={action.id} className={styles.actionRow}><label>Action<input value={action.title} onChange={(event) => onChange(milestoneIndex, actionIndex, "title", event.target.value)} /></label><SelectField id={`action-owner-${action.id}`} name="action_owner" label="Owner" value={action.owner_user_id ?? ""} onChange={(value) => { const owner = candidates.find((candidate) => candidate.user_id === value); onChange(milestoneIndex, actionIndex, "owner_user_id", value || null); onChange(milestoneIndex, actionIndex, "owner_name", owner?.display_name ?? ""); }} options={[{ value: "", label: "Not assigned", description: "Choose from the project team" }, ...candidates.map((candidate) => ({ value: candidate.user_id, label: candidate.display_name, description: candidate.email }))]} /><label>Due date<input type="date" value={action.due_date ?? ""} onChange={(event) => onChange(milestoneIndex, actionIndex, "due_date", event.target.value || null)} /></label><SelectField id={`action-status-${action.id}`} name="action_status" label="Status" value={action.status} onChange={(value) => onChange(milestoneIndex, actionIndex, "status", value)} options={["not_started", "in_progress", "blocked", "complete"].map((value) => ({ value, label: labelize(value), description: "Action state" }))} /><button type="button" onClick={() => onRemove(actionIndex)} aria-label={`Remove action ${actionIndex + 1}`}><Trash2 size={14} /></button></div>)}</div>;
}

function Benefits({ project }: { project: ProjectWorkspaceRecord }) {
  return (
    <section>
      <SectionHeading icon={BarChart3} eyebrow="Benefit forecast" title="Benefits and line of sight" description="Target, achieved, Finance-validated value, and remaining line of sight stay separate throughout delivery." />
      <section className={styles.financeLedger} aria-label="Financial benefit summary">
        <Ledger label="Target" value={formatLakhs(project.target)} detail="Published plan" />
        <Ledger label="Achieved" value={formatLakhs(project.achieved)} detail="Reported to date" />
        <Ledger label="Finance validated" value={formatLakhs(project.validated)} detail="Approved evidence" />
        <Ledger label="LOS" value={formatLakhs(project.line_of_sight)} detail="Expected to materialise" />
      </section>
      {project.benefit_periods.length ? (
        <div className={styles.tableWrap}>
          <table>
            <thead><tr><th>Period</th><th>Plan</th><th>Achieved</th><th>LOS</th><th>KPI actual</th><th>Delivery</th><th>Finance</th></tr></thead>
            <tbody>{project.benefit_periods.map((period) => <tr key={period.month}><th scope="row">{period.month}</th><td>{formatLakhs(period.plan)}</td><td>{formatLakhs(period.achieved)}</td><td>{formatLakhs(period.line_of_sight)}</td><td>{period.kpi_actual ?? "Not recorded"}</td><td>{period.status ? labelize(period.status) : "Not assessed"}</td><td><span className={styles.financeState} data-approved={period.finance_approved}>{period.finance_approved ? "Validated" : "Pending"}</span></td></tr>)}</tbody>
          </table>
        </div>
      ) : <EmptyState icon={BarChart3} title="No benefit periods are recorded." text="Monthly plan, actual, LOS, KPI, and Finance state will appear here when benefit tracking begins." />}
    </section>
  );
}

function Charter({ project }: { project: ProjectWorkspaceRecord }) {
  return (
    <section>
      <SectionHeading icon={FileClock} eyebrow="Governed baseline" title="Charter and revisions" description="The active baseline remains the execution reference. Every future OE revision will retain its reason and author." />
      <div className={styles.charterGrid}>
        <div className={styles.baselines}>
          <h3>Published baselines</h3>
          {project.baselines.map((baseline) => <article key={baseline.id} data-active={baseline.is_active}><span>v{baseline.version}</span><div><strong>{baseline.reason}</strong><p>{baseline.created_by_name} · {formatDateTime(baseline.published_at)}</p></div>{baseline.is_active ? <i><ShieldCheck aria-hidden="true" size={13} />Active</i> : null}</article>)}
        </div>
        <div className={styles.charterRecord}>
          <h3>Baseline v{project.baseline_version}</h3>
          <dl>
            <Fact label="Leader" value={project.charter.leader} />
            <Fact label="Sponsor" value={project.charter.sponsor} />
            <Fact label="Approved budget" value={project.charter.budget_approved ? `₹${Number(project.charter.budget_approved).toLocaleString("en-IN")}` : null} />
            <Fact label="Belt level" value={project.charter.belt_level} />
            <Fact label="Impact areas" value={project.charter.impact_areas.map(labelize).join(", ")} />
            <Fact label="Additional team" value={project.charter.team_members.join(", ")} />
          </dl>
          <ReadOnly label="Objective" value={project.charter.objective} />
          <div className={styles.scopeGrid}><ReadOnly label="In scope" value={project.charter.in_scope} /><ReadOnly label="Out of scope" value={project.charter.out_of_scope} /></div>
        </div>
      </div>
    </section>
  );
}

function Team({ project }: { project: ProjectWorkspaceRecord }) {
  return (
    <section>
      <SectionHeading icon={Users} eyebrow="People and ownership" title="Project team" description="The Project Lead and assigned team can contribute to delivery. Invitation responses remain visible without blocking the project." />
      <div className={styles.teamLead}><Users aria-hidden="true" /><div><p>Project lead</p><h3>{project.lead_name || "Not recorded"}</h3><span>{[project.department, project.site].filter(Boolean).join(" · ") || "Organisation assignment not recorded"}</span></div></div>
      {project.team.length ? <div className={styles.teamList}>{project.team.map((member) => <article key={member.id}><span aria-hidden="true">{initials(member.name)}</span><div><strong>{member.name}</strong><p>{member.email}</p></div><i data-status={member.status}>{labelize(member.status)}</i></article>)}</div> : <EmptyState icon={Users} title="No TRANSPIRE members were assigned." text="Additional names from the published charter remain visible in Charter & revisions." />}
    </section>
  );
}

function ActivityPanel({ project }: { project: ProjectWorkspaceRecord }) {
  return (
    <section>
      <SectionHeading icon={Activity} eyebrow="Traceable history" title="Project activity" description="Submission, approval, charter, and future execution events are retained in chronological order." />
      {project.activity.length ? <ol className={styles.activityList}>{project.activity.map((event) => <li key={event.id}><span><CheckCircle2 aria-hidden="true" size={14} /></span><div><strong>{event.summary}</strong><p>{event.actor_name ?? "System"} · {formatDateTime(event.created_at)}</p></div><i>{labelize(event.event_type.replace(".", " "))}</i></li>)}</ol> : <EmptyState icon={Activity} title="No activity has been recorded." text="Governed project events will appear here as the execution lifecycle advances." />}
    </section>
  );
}

function ActionTable({ actions }: { actions: ActionRecord[] }) {
  return <div className={styles.actionTable}><table><thead><tr><th>Action</th><th>Owner</th><th>Due</th><th>Status</th></tr></thead><tbody>{actions.map((action) => <tr key={action.id}><td>{action.title}</td><td>{action.owner_name || "Not assigned"}</td><td>{formatDate(action.due_date)}</td><td>{labelize(action.status)}</td></tr>)}</tbody></table></div>;
}

function WorkspaceSkeleton() { return <div className={styles.skeleton} aria-label="Loading project"><span /><span /><span /></div>; }
function Ledger({ label, value, detail }: { label: string; value: string; detail: string }) { return <div><span>{label}</span><strong>{value}</strong><small>{detail}</small></div>; }
function Fact({ label, value }: { label: string; value: string | null | undefined }) { return <div><dt>{label}</dt><dd>{value || "Not provided"}</dd></div>; }
function ReadOnly({ label, value }: { label: string; value: string | null | undefined }) { return <div className={styles.readOnly}><span>{label}</span><p>{value || "Not provided"}</p></div>; }
function SectionHeading({ icon: Icon, eyebrow, title, description }: { icon: typeof Target; eyebrow: string; title: string; description: string }) { return <header className={styles.sectionHeading}><Icon aria-hidden="true" /><div><p>{eyebrow}</p><h2>{title}</h2><span>{description}</span></div></header>; }
function EmptyState({ icon: Icon, title, text }: { icon: typeof Target; title: string; text: string }) { return <div className={styles.empty}><Icon aria-hidden="true" /><h3>{title}</h3><p>{text}</p></div>; }
function formatDate(value: string | null) { return value ? new Intl.DateTimeFormat("en-IN", { day: "2-digit", month: "short", year: "numeric", timeZone: "UTC" }).format(new Date(`${value}T00:00:00Z`)) : "Not recorded"; }
function formatDateTime(value: string) { return new Intl.DateTimeFormat("en-IN", { day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" }).format(new Date(value)); }
function dateRange(start: string | null, end: string | null) { return start || end ? `${formatDate(start)} to ${formatDate(end)}` : "Not planned"; }
function labelize(value: string) { return value.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase()); }
function healthLabel(value: string) { return ({ not_set: "Health not assessed", on_track: "On track", at_risk: "At risk", blocked: "Blocked" } as Record<string, string>)[value] ?? labelize(value); }
function initials(name: string) { return name.split(/\s+/).filter(Boolean).slice(0, 2).map((part) => part[0]?.toUpperCase()).join("") || "?"; }
