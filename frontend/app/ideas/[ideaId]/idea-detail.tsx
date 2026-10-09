"use client";

import { ArrowLeft, ArrowRight, Check, CheckCircle2, Circle, Clock3, FilePenLine, LockKeyhole, Pencil, Plus, RefreshCw, RotateCcw, Send, ShieldCheck, Trash2, UserPlus, X, XCircle } from "lucide-react";
import { TenantLink as Link } from "@/components/app/tenant-link";
import { useTenantRouter as useRouter } from "@/lib/use-tenant-router";
import { useCallback, useEffect, useMemo, useState } from "react";
import { AdminShell } from "@/components/admin/admin-shell";
import { DismissibleNotice } from "@/components/ui/dismissible-notice";
import { SearchableSelectField } from "@/components/ui/searchable-select-field";
import { SelectField } from "@/components/ui/select-field";
import { apiRequest } from "@/lib/api";
import { useSession } from "@/lib/use-session";
import styles from "./idea-detail.module.css";

type ApprovalStage = { id: string; round_number: number; stage_order: number; stage_key: string; stage_name: string; assignee_name: string; assignee_email: string; sla_hours: number; status: string; decision_comment: string | null; due_at: string | null; actioned_at: string | null; is_actionable: boolean };
type ActionDraft = { action: string; plan_start: string; plan_end: string; actual_start: string; actual_end: string; owner: string; status: string; phase: number | null };
type MonthDraft = { month: string; ftm_plan: string; ftm_actual: string; line_of_sight: string; kpi_actual: string; status: string; finance_approved?: boolean };
type Charter = { id: string; sponsor: string; leader: string; department_id: string | null; site_id: string | null; start_date: string | null; target_completion_date: string | null; team_members: string[]; team_membership_ids: string[]; in_scope: string; out_of_scope: string; objective: string; benefit_type: string; kpi_name: string; budget_approved: string | null; impact_areas: string[]; belt_level: string | null; action_items: ActionDraft[]; monthly_tracking: MonthDraft[]; status: string; updated_at: string; submitted_at: string | null; team_invitations_queued?: number; team_invitations_skipped?: number };
type Idea = { id: string; reference: string; status: string; idea_type: string; project_category: string | null; project_subtype: string | null; title: string; submitter_name: string; submitter_email: string; submitted_at: string | null; updated_at: string; site_id: string | null; site: string | null; department_id: string | null; department: string | null; category: string | null; subcategory: string | null; process_area: string | null; problem_statement: string; business_case: string; current_state: string; baseline_uom: string; target_state: string; target_uom: string; impacts: string[]; estimated_annual_saving: string | null; cost_avoidance: string | null; investment_required: string | null; estimated_annual_saving_usd: string | null; cost_avoidance_usd: string | null; investment_required_usd: string | null; usd_exchange_rate: string | null; fx_rate_date: string | null; approval_stages: ApprovalStage[]; charter_available: boolean; charter: Charter | null; can_edit_charter: boolean; can_edit_idea: boolean; correction_reason: string | null };
type CatalogItem = { id: string; name: string; site_ids: string[]; applies_to_all_sites: boolean };
type Catalog = { sites: CatalogItem[]; departments: CatalogItem[] };
type TeamCandidate = { membership_id: string; display_name: string; email: string };
type Section = "overview" | "approval" | "project-charter";
type CharterDraft = { sponsor: string; leader: string; department_id: string; site_id: string; start_date: string; target_completion_date: string; team_members: string; team_membership_ids: string[]; in_scope: string; out_of_scope: string; objective: string; benefit_type: string; kpi_name: string; budget_approved: string; impact_areas: string[]; belt_level: string; action_items: ActionDraft[]; monthly_tracking: MonthDraft[] };

const months = ["Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec", "Jan", "Feb", "Mar"];
const emptyCharter: CharterDraft = { sponsor: "", leader: "", department_id: "", site_id: "", start_date: "", target_completion_date: "", team_members: "", team_membership_ids: [], in_scope: "", out_of_scope: "", objective: "", benefit_type: "cost_saving", kpi_name: "", budget_approved: "", impact_areas: [], belt_level: "", action_items: [], monthly_tracking: months.map((month) => ({ month, ftm_plan: "", ftm_actual: "", line_of_sight: "", kpi_actual: "", status: "" })) };
const impacts = [{ value: "safety", label: "Safety" }, { value: "quality", label: "Quality" }, { value: "delivery", label: "Delivery / OTIF" }, { value: "cost", label: "Cost" }, { value: "productivity", label: "Productivity / People" }];

export function IdeaDetail({ ideaId }: { ideaId: string }) {
  const router = useRouter();
  const { session, loading: sessionLoading } = useSession();
  const [idea, setIdea] = useState<Idea | null>(null);
  const [catalog, setCatalog] = useState<Catalog>({ sites: [], departments: [] });
  const [teamCandidates, setTeamCandidates] = useState<TeamCandidate[]>([]);
  const [section, setSection] = useState<Section>(() => {
    if (typeof window === "undefined") return "overview";
    const requested = new URLSearchParams(window.location.search).get("section");
    return ["overview", "approval", "project-charter"].includes(requested ?? "") ? requested as Section : "overview";
  });
  const [charter, setCharter] = useState<CharterDraft>(emptyCharter);
  const [decision, setDecision] = useState("");
  const [comment, setComment] = useState("");
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const loadIdea = useCallback(async () => {
    setError("");
    try {
      const response = await apiRequest(`/ideas/${ideaId}`);
      if (response.status === 401) { router.replace("/sign-in"); return; }
      if (!response.ok) { const body = await response.json().catch(() => null) as { detail?: string } | null; throw new Error(body?.detail ?? "The idea could not be loaded."); }
      const next = (await response.json()) as Idea;
      if (next.can_edit_idea) {
        router.replace(`/ideas/new/v2?resume=${next.id}`);
        return;
      }
      setIdea(next);
      setCharter(toDraft(next));
    } catch (caught) { setError(caught instanceof Error ? caught.message : "The idea could not be loaded."); }
  }, [ideaId, router]);

  useEffect(() => { if (!session) return; const timer = window.setTimeout(() => void loadIdea(), 0); return () => window.clearTimeout(timer); }, [loadIdea, session]);
  useEffect(() => { if (!session || !idea?.charter_available) return; Promise.all([apiRequest("/ideas/submission-catalog"), apiRequest("/projects/team-candidates")]).then(async ([catalogResponse, teamResponse]) => { if (catalogResponse.ok) setCatalog(await catalogResponse.json() as Catalog); if (teamResponse.ok) setTeamCandidates(await teamResponse.json() as TeamCandidate[]); }).catch(() => undefined); }, [idea?.charter_available, session]);

  const visibleDepartments = useMemo(() => catalog.departments.filter((department) => !charter.site_id || department.applies_to_all_sites || department.site_ids.includes(charter.site_id)), [catalog.departments, charter.site_id]);
  const actionable = idea?.approval_stages.find((stage) => stage.is_actionable) ?? null;

  const actOnApproval = async () => {
    if (!idea || !actionable || !decision) return;
    setBusy("approval"); setError("");
    try {
      const response = await apiRequest(`/ideas/${idea.id}/approvals/${actionable.id}`, { method: "POST", body: JSON.stringify({ decision, comment }) });
      const body = await response.json().catch(() => null) as Idea | { detail?: string } | null;
      if (!response.ok) throw new Error((body as { detail?: string } | null)?.detail ?? "The approval decision could not be saved.");
      const next = body as Idea; setIdea(next); setCharter(toDraft(next)); setDecision(""); setComment(""); setNotice(decision === "approve" ? "Approval recorded. The idea has moved to its next stage." : "The decision and reason have been recorded.");
    } catch (caught) { setError(caught instanceof Error ? caught.message : "The approval decision could not be saved."); }
    finally { setBusy(""); }
  };

  const saveCharter = async (submit = false) => {
    if (!idea) return;
    setBusy(submit ? "submit-charter" : "save-charter"); setError("");
    try {
      const payload = { ...charter, department_id: charter.department_id || null, site_id: charter.site_id || null, start_date: charter.start_date || null, target_completion_date: charter.target_completion_date || null, team_members: charter.team_members.split(/[\n,]/).map((name) => name.trim()).filter(Boolean), budget_approved: charter.budget_approved || null, belt_level: charter.belt_level || null, action_items: charter.action_items.map((item) => ({ ...item, plan_start: item.plan_start || null, plan_end: item.plan_end || null, actual_start: item.actual_start || null, actual_end: item.actual_end || null })), monthly_tracking: charter.monthly_tracking.map((entry) => ({ month: entry.month, ftm_plan: entry.ftm_plan || null, ftm_actual: entry.ftm_actual || null, line_of_sight: entry.line_of_sight || null, kpi_actual: entry.kpi_actual || null, status: entry.status })) };
      const response = await apiRequest(`/ideas/${idea.id}/charter${submit ? "/submit" : ""}`, { method: submit ? "POST" : "PUT", body: JSON.stringify(payload) });
      const body = await response.json().catch(() => null) as Charter | { detail?: string } | null;
      if (!response.ok) throw new Error((body as { detail?: string } | null)?.detail ?? "The project charter could not be saved.");
      await loadIdea();
      const saved = body as Charter;
      setNotice(submit ? `Project charter submitted and Baseline v1 published.${saved.team_invitations_queued ? ` ${saved.team_invitations_queued} team invitation${saved.team_invitations_queued === 1 ? "" : "s"} queued.` : ""}${saved.team_invitations_skipped ? ` ${saved.team_invitations_skipped} unavailable team member${saved.team_invitations_skipped === 1 ? " was" : "s were"} skipped without blocking submission.` : ""}` : "Project charter draft saved.");
    } catch (caught) { setError(caught instanceof Error ? caught.message : "The project charter could not be saved."); }
    finally { setBusy(""); }
  };

  if (sessionLoading || !session) return <main className={styles.loading}>Opening idea details</main>;
  if (!idea) return <main className={styles.loading}>{error ? <div className={styles.loadFailure}><XCircle size={24} /><h1>Idea unavailable</h1><p>{error}</p><button type="button" onClick={() => void loadIdea()}><RefreshCw size={15} />Retry</button><Link href="/home">Return home</Link></div> : "Loading the idea and its approval route"}</main>;

  return <AdminShell session={session} active="ideas" eyebrow={`${idea.reference} · ${idea.idea_type === "project" ? "Project" : "Kaizen"}`} title={idea.title} description="Review the submitted case, understand each approval decision, and continue into the project charter when the idea is fully approved.">
    <div className={styles.backRow}><Link href="/home"><ArrowLeft size={15} />Back to Home</Link><div>{idea.can_edit_idea ? <Link className={styles.editIdea} href={`/ideas/new/v2?resume=${idea.id}`}><Pencil size={14} />{idea.status === "needs_correction" ? "Edit correction" : "Resume draft"}</Link> : null}<span className={styles.status} data-status={idea.status}>{statusLabel(idea.status)}</span></div></div>
    <div className={styles.toastStack}>{notice ? <DismissibleNotice onDismiss={() => setNotice("")}>{notice}</DismissibleNotice> : null}{error ? <DismissibleNotice tone="error" onDismiss={() => setError("")}>{error}</DismissibleNotice> : null}</div>
    <nav className={styles.tabs} aria-label="Idea detail sections">
      <button type="button" data-active={section === "overview"} onClick={() => setSection("overview")}>Idea details</button>
      <button type="button" data-active={section === "approval"} onClick={() => setSection("approval")}>Approval route <span>{idea.approval_stages.length}</span></button>
      <button type="button" data-active={section === "project-charter"} onClick={() => setSection("project-charter")}>{idea.charter_available ? <FilePenLine size={15} /> : <LockKeyhole size={15} />}Project charter</button>
    </nav>
    {section === "overview" ? <Overview idea={idea} /> : null}
    {section === "approval" ? <ApprovalPanel idea={idea} actionable={actionable} decision={decision} comment={comment} busy={busy === "approval"} onDecision={setDecision} onComment={setComment} onSubmit={() => void actOnApproval()} /> : null}
    {section === "project-charter" ? <CharterPanel
      idea={idea}
      charter={charter}
      catalog={catalog}
      teamCandidates={teamCandidates}
      departments={visibleDepartments}
      busy={busy}
      onChange={(field, value) => setCharter((current) => ({ ...current, [field]: value }))}
      onAddTeam={(membershipId) => setCharter((current) => current.team_membership_ids.includes(membershipId) ? current : ({ ...current, team_membership_ids: [...current.team_membership_ids, membershipId] }))}
      onRemoveTeam={(membershipId) => setCharter((current) => ({ ...current, team_membership_ids: current.team_membership_ids.filter((value) => value !== membershipId) }))}
      onToggleImpact={(value) => setCharter((current) => ({ ...current, impact_areas: current.impact_areas.includes(value) ? current.impact_areas.filter((item) => item !== value) : [...current.impact_areas, value] }))}
      onAddAction={() => setCharter((current) => ({ ...current, action_items: [...current.action_items, { action: "", plan_start: "", plan_end: "", actual_start: "", actual_end: "", owner: "", status: "pending", phase: idea.project_subtype?.includes("Lean Six Sigma") ? 0 : null }] }))}
      onRemoveAction={(index) => setCharter((current) => ({ ...current, action_items: current.action_items.filter((_, itemIndex) => itemIndex !== index) }))}
      onUpdateAction={(index, field, value) => setCharter((current) => ({ ...current, action_items: current.action_items.map((item, itemIndex) => itemIndex === index ? { ...item, [field]: value } : item) }))}
      onUpdateMonth={(index, field, value) => setCharter((current) => ({ ...current, monthly_tracking: current.monthly_tracking.map((entry, entryIndex) => entryIndex === index ? { ...entry, [field]: value } : entry) }))}
      onSave={() => void saveCharter(false)}
      onSubmit={() => void saveCharter(true)}
    /> : null}
  </AdminShell>;
}

function Overview({ idea }: { idea: Idea }) { return <div className={styles.overview}>
  <section><SectionHeading eyebrow="Submitted case" title="The opportunity and proposed direction" description="These are the statements supplied for evaluation. They remain unchanged while the idea moves through approval." /><div className={styles.narrativeGrid}><Detail label="Problem statement" value={idea.problem_statement} /><Detail label="Business case and proposed solution" value={idea.business_case} /><Detail label="Current state or baseline" value={measure(idea.current_state, idea.baseline_uom)} /><Detail label="Target state or KPI" value={measure(idea.target_state, idea.target_uom)} /></div></section>
  <section><SectionHeading eyebrow="Classification" title="Where the improvement belongs" description="Classification connects this idea to the organisation’s shared Operational Excellence catalogue." /><dl className={styles.metadata}><DetailItem label="Submitted by" value={`${idea.submitter_name} · ${idea.submitter_email}`} /><DetailItem label="Site" value={idea.site} /><DetailItem label="Department" value={idea.department} /><DetailItem label="Category" value={idea.category} /><DetailItem label="Subcategory" value={idea.subcategory} /><DetailItem label="Process area" value={idea.process_area} /></dl></section>
  <section><SectionHeading eyebrow="Expected impact" title="The value case recorded at submission" description="Financial estimates remain indicative until the project and Finance validation stages are complete." /><div className={styles.impactSummary}><div><span>SQDCP impact</span><p>{idea.impacts.length ? idea.impacts.map(capitalize).join(", ") : "Not provided"}</p></div><Financial label="Estimated annual saving" inr={idea.estimated_annual_saving} usd={idea.estimated_annual_saving_usd} /><Financial label="Cost avoidance" inr={idea.cost_avoidance} usd={idea.cost_avoidance_usd} /><Financial label="Investment required" inr={idea.investment_required} usd={idea.investment_required_usd} /></div>{idea.usd_exchange_rate && idea.fx_rate_date ? <p className={styles.fxProvenance}>USD equivalents use the INR to USD rate fixed on {formatDate(idea.fx_rate_date)}.</p> : null}</section>
</div>; }

function ApprovalPanel({ idea, actionable, decision, comment, busy, onDecision, onComment, onSubmit }: { idea: Idea; actionable: ApprovalStage | null; decision: string; comment: string; busy: boolean; onDecision: (value: string) => void; onComment: (value: string) => void; onSubmit: () => void }) { return <div className={styles.approvalPanel}>
  <SectionHeading eyebrow="Governed evaluation" title="Approval route and decision record" description="Stages follow the workflow contract captured when the idea was submitted. A later workflow version cannot silently change this route." />
  <ol className={styles.timeline}>{idea.approval_stages.map((stage) => <li key={stage.id} data-status={stage.status}><span className={styles.timelineIcon}>{stage.status === "approve" ? <Check size={16} /> : stage.status === "reject" ? <XCircle size={16} /> : stage.status === "pending" ? <Clock3 size={16} /> : <Circle size={14} />}</span><div><header><span>Round {stage.round_number} · Stage {stage.stage_order}</span><h3>{stage.stage_name}</h3><strong>{stageStatus(stage.status)}</strong></header><p>Assigned to {stage.assignee_name} · {stage.assignee_email}</p><small>{stage.actioned_at ? `Decision recorded ${formatDate(stage.actioned_at)}` : stage.due_at ? `Due ${formatDate(stage.due_at)} · ${stage.sla_hours}-hour service target` : `${stage.sla_hours}-hour service target after activation`}</small>{stage.decision_comment ? <blockquote>{stage.decision_comment}</blockquote> : null}</div></li>)}</ol>
  {actionable ? <section className={styles.decisionPanel}><div><ShieldCheck size={20} /><div><p>Your decision</p><h3>{actionable.stage_name}</h3><span>Review the complete idea above. A correction or rejection requires a clear reason for the submitter.</span></div></div><div className={styles.decisionChoices}><button type="button" data-selected={decision === "approve"} onClick={() => onDecision("approve")}><CheckCircle2 size={17} /><span><strong>Approve</strong><small>Move to the next stage</small></span></button><button type="button" data-selected={decision === "needs_correction"} onClick={() => onDecision("needs_correction")}><RotateCcw size={17} /><span><strong>Needs correction</strong><small>Return with a reason</small></span></button><button type="button" data-selected={decision === "reject"} onClick={() => onDecision("reject")}><XCircle size={17} /><span><strong>Reject</strong><small>End this approval journey</small></span></button></div><label>Decision comment {decision === "approve" ? <span>Optional</span> : <span>Required</span>}<textarea value={comment} onChange={(event) => onComment(event.target.value)} rows={4} placeholder={decision === "approve" ? "Record any conditions or guidance for the next stage." : "Explain exactly what should be corrected or why the idea cannot proceed."} /></label><button className={styles.primaryButton} type="button" disabled={!decision || (decision !== "approve" && !comment.trim()) || busy} onClick={onSubmit}>{busy ? "Recording decision" : "Confirm decision"}<Send size={15} /></button></section> : <div className={styles.readOnlyNote}><ShieldCheck size={18} /><div><strong>No decision is assigned to you at this stage.</strong><p>You can still review the route and every recorded comment.</p></div></div>}
</div>; }

function CharterPanel({ idea, charter, catalog, teamCandidates, departments, busy, onChange, onAddTeam, onRemoveTeam, onToggleImpact, onAddAction, onRemoveAction, onUpdateAction, onUpdateMonth, onSave, onSubmit }: { idea: Idea; charter: CharterDraft; catalog: Catalog; teamCandidates: TeamCandidate[]; departments: CatalogItem[]; busy: string; onChange: (field: keyof Omit<CharterDraft, "impact_areas" | "team_membership_ids" | "action_items" | "monthly_tracking">, value: string) => void; onAddTeam: (membershipId: string) => void; onRemoveTeam: (membershipId: string) => void; onToggleImpact: (value: string) => void; onAddAction: () => void; onRemoveAction: (index: number) => void; onUpdateAction: (index: number, field: keyof ActionDraft, value: string | number | null) => void; onUpdateMonth: (index: number, field: keyof MonthDraft, value: string) => void; onSave: () => void; onSubmit: () => void }) {
  if (!idea.charter_available) return <section className={styles.lockedCharter}><LockKeyhole size={26} /><p>Available after approval</p><h2>The project charter opens when every required approver accepts the idea.</h2><span>Approval preserves the original case. The charter then adds accountable ownership, timing, scope, team, KPI, and approved investment without changing what was submitted.</span><button type="button" disabled>Project charter locked</button></section>;
  const readOnly = !idea.can_edit_charter;
  const totalPlan = charter.monthly_tracking.reduce((total, entry) => total + Number(entry.ftm_plan || 0), 0);
  const totalActual = charter.monthly_tracking.reduce((total, entry) => total + Number(entry.ftm_actual || 0), 0);
  const totalLineOfSight = charter.monthly_tracking.reduce((total, entry) => total + Number(entry.line_of_sight || 0), 0);
  return <form className={styles.charterForm} onSubmit={(event) => event.preventDefault()} id="project-charter">
    <div className={styles.charterReady}><CheckCircle2 size={22} /><div><p>{idea.charter?.status === "submitted" ? "Ready to start" : "Approved idea"}</p><h2>{idea.charter?.status === "submitted" ? "Baseline v1 is published." : "Define how this approved idea will be delivered."}</h2><span>{idea.charter?.status === "submitted" ? "The submitted charter is locked. Continue delivery, milestones, benefits and completion from the Projects portfolio." : "Complete the URS charter fields below. Save a draft while ownership and dates are being confirmed."}</span>{idea.charter?.status === "submitted" ? <Link href="/projects">Open Projects portfolio<ArrowRight size={15} /></Link> : null}</div></div>
    <fieldset disabled={readOnly}><section>
      <SectionHeading eyebrow="Ownership and timing" title={`${idea.idea_type === "kaizen" ? "Kaizen" : "Project"} charter details`} description="Name accountable leaders, confirm the delivery location, and set a realistic implementation window." />
      <div className={styles.formGrid}><Field label={idea.idea_type === "kaizen" ? "OE Lead / Facilitator" : "Project Sponsor"} hint="Name and designation"><input value={charter.sponsor} onChange={(event) => onChange("sponsor", event.target.value)} /></Field><Field label={idea.idea_type === "kaizen" ? "Team Leader" : "Project Leader"} hint="Person accountable for day-to-day delivery"><input value={charter.leader} onChange={(event) => onChange("leader", event.target.value)} /></Field><SelectField id="charter-site" name="site_id" label="Site / Location" value={charter.site_id} onChange={(value) => { onChange("site_id", value); if (charter.department_id && !departments.some((item) => item.id === charter.department_id)) onChange("department_id", ""); }} disabled={readOnly} options={[{ value: "", label: "Select a site", description: "Where implementation will be owned" }, ...catalog.sites.map((item) => ({ value: item.id, label: item.name }))]} /><SelectField id="charter-department" name="department_id" label="Department" value={charter.department_id} onChange={(value) => onChange("department_id", value)} disabled={readOnly || !charter.site_id} options={[{ value: "", label: charter.site_id ? "Select a department" : "Choose a site first", description: "Accountable function" }, ...departments.map((item) => ({ value: item.id, label: item.name }))]} /><Field label="Start Date" hint="Planned work commencement"><input type="date" value={charter.start_date} onChange={(event) => onChange("start_date", event.target.value)} /></Field><Field label={idea.idea_type === "kaizen" ? "Completion Date" : "Target Completion"} hint="Committed implementation target"><input type="date" value={charter.target_completion_date} onChange={(event) => onChange("target_completion_date", event.target.value)} /></Field></div>
      <div className={styles.teamAssignment}>
        <div><UserPlus size={19} /><div><strong>Invite the project team</strong><p>Select active organisation members. Invitations are queued when the charter is submitted and never block submission.</p></div></div>
        <SearchableSelectField id="charter-team-member" name="team_member" label="Add team member" value="" disabled={readOnly} placeholder="Search and add a person" options={teamCandidates.filter((person) => !charter.team_membership_ids.includes(person.membership_id)).map((person) => ({ value: person.membership_id, label: person.display_name, description: person.email, status: "active" }))} onChange={onAddTeam} />
        {charter.team_membership_ids.length ? <ul>{charter.team_membership_ids.map((membershipId) => { const person = teamCandidates.find((candidate) => candidate.membership_id === membershipId); return <li key={membershipId}><span><strong>{person?.display_name ?? "Assigned member"}</strong><small>{person?.email ?? "Saved team assignment"}</small></span>{!readOnly ? <button type="button" onClick={() => onRemoveTeam(membershipId)} aria-label={`Remove ${person?.display_name ?? "team member"}`}><X size={15} /></button> : null}</li>; })}</ul> : <p className={styles.teamEmpty}>No organisation members selected yet. You can still save or submit the charter.</p>}
      </div>
      <Field label="Additional team names" hint="Optional names that do not require a TRANSPIRE invitation"><textarea rows={3} value={charter.team_members} onChange={(event) => onChange("team_members", event.target.value)} placeholder="Add any team members not yet available in TRANSPIRE" /></Field>
    </section>
      {idea.idea_type === "project" ? <section><SectionHeading eyebrow="Scope and objective" title="Set clear project boundaries" description="A strong charter says what the project will change, what it will not change, and how success will be recognised." /><div className={styles.formGrid}><Field label="In Scope" hint="Processes, areas, products, or systems included"><textarea rows={5} value={charter.in_scope} onChange={(event) => onChange("in_scope", event.target.value)} /></Field><Field label="Out of Scope" hint="Explicit exclusions that protect focus"><textarea rows={5} value={charter.out_of_scope} onChange={(event) => onChange("out_of_scope", event.target.value)} /></Field></div><Field label="Project Objective (SMART goal)" hint="Specific, measurable, achievable, relevant, and time-bound"><textarea rows={4} value={charter.objective} onChange={(event) => onChange("objective", event.target.value)} placeholder="Reduce changeover time from 90 to 55 minutes by 31 March without increasing safety events or quality defects." /></Field></section> : null}
      <section><SectionHeading eyebrow="Benefit and measurement" title="Define the value and the measure" description="Connect the approved idea to a named KPI, agreed investment, and the SQDCP outcomes the project must protect." /><div className={styles.formGrid}><SelectField id="charter-benefit" name="benefit_type" label="Benefit Type" value={charter.benefit_type} onChange={(value) => onChange("benefit_type", value)} disabled={readOnly} options={[{ value: "cost_saving", label: "Cost Saving" }, { value: "cost_avoidance", label: "Cost Avoidance" }, { value: "both", label: "Cost Saving + Avoidance" }, { value: "revenue", label: "Revenue Enhancement" }, { value: "kpi_only", label: "KPI Only", description: "No direct financial saving" }]} /><Field label="KPI / Metric Name" hint="For example OEE %, yield %, cycle time, or OTIF"><input value={charter.kpi_name} onChange={(event) => onChange("kpi_name", event.target.value)} /></Field><Field label="Budget Approved (₹)" hint="Confirmed implementation investment"><input type="number" min="0" step="0.01" value={charter.budget_approved} onChange={(event) => onChange("budget_approved", event.target.value)} /></Field>{idea.project_subtype?.includes("Lean Six Sigma") ? <SelectField id="charter-belt" name="belt_level" label="LSS Belt Level" value={charter.belt_level} onChange={(value) => onChange("belt_level", value)} disabled={readOnly} options={[{ value: "", label: "Select belt level" }, ...["Yellow Belt", "Green Belt", "Black Belt", "Master Black Belt"].map((value) => ({ value, label: value }))]} /> : null}</div><fieldset className={styles.impactChoices}><legend>SQDCP Impact Areas</legend><p>Select every dimension this charter will measure or protect.</p><div>{impacts.map((impact) => <label key={impact.value} data-selected={charter.impact_areas.includes(impact.value)}><input type="checkbox" checked={charter.impact_areas.includes(impact.value)} onChange={() => onToggleImpact(impact.value)} /><span>{impact.value.slice(0, 1).toUpperCase()}</span>{impact.label}</label>)}</div></fieldset></section>
      <section><div className={styles.sectionActionHeader}><SectionHeading eyebrow="Delivery plan" title={idea.project_subtype?.includes("Lean Six Sigma") ? "DMAIC action plan" : "Action items"} description="Translate the charter into owned work with planned and actual dates. Status remains visible on the idea throughout delivery." />{!readOnly ? <button type="button" className={styles.secondaryButton} onClick={onAddAction}><Plus size={15} />Add action</button> : null}</div>{charter.action_items.length ? <div className={styles.actionItems}>{charter.action_items.map((item, index) => <article key={`${index}-${item.action}`}><header><span>Action {index + 1}</span>{!readOnly ? <button type="button" onClick={() => onRemoveAction(index)} aria-label={`Remove action ${index + 1}`}><Trash2 size={15} /></button> : null}</header><Field label="Action" hint="A specific, observable delivery step"><textarea rows={3} value={item.action} onChange={(event) => onUpdateAction(index, "action", event.target.value)} /></Field><div className={styles.actionGrid}><Field label="Plan Start" hint="Committed start"><input type="date" value={item.plan_start} onChange={(event) => onUpdateAction(index, "plan_start", event.target.value)} /></Field><Field label="Plan End" hint="Committed finish"><input type="date" value={item.plan_end} onChange={(event) => onUpdateAction(index, "plan_end", event.target.value)} /></Field><Field label="Actual Start" hint="When work began"><input type="date" value={item.actual_start} onChange={(event) => onUpdateAction(index, "actual_start", event.target.value)} /></Field><Field label="Actual End" hint="When work completed"><input type="date" value={item.actual_end} onChange={(event) => onUpdateAction(index, "actual_end", event.target.value)} /></Field><Field label="Owner" hint="Person accountable"><input value={item.owner} onChange={(event) => onUpdateAction(index, "owner", event.target.value)} /></Field><SelectField id={`action-status-${index}`} name={`action_status_${index}`} label="Status" value={item.status} onChange={(value) => onUpdateAction(index, "status", value)} disabled={readOnly} options={[{ value: "pending", label: "Pending" }, { value: "in_progress", label: "In Progress" }, { value: "complete", label: "Complete" }]} />{idea.project_subtype?.includes("Lean Six Sigma") ? <SelectField id={`action-phase-${index}`} name={`action_phase_${index}`} label="DMAIC phase" value={String(item.phase ?? 0)} onChange={(value) => onUpdateAction(index, "phase", Number(value))} disabled={readOnly} options={["Define", "Measure", "Analyse", "Improve", "Control"].map((label, phase) => ({ value: String(phase), label }))} /> : null}</div></article>)}</div> : <div className={styles.actionEmpty}><FilePenLine size={20} /><strong>No action items recorded yet.</strong><p>Add the first owned delivery step when the implementation plan is known.</p></div>}</section>
      <section><SectionHeading eyebrow="Savings and KPI" title="Month-on-month benefit tracker" description="Record For The Month plan and actual values in ₹ lakhs, line of sight, KPI actual, and delivery status. Year-to-month totals update automatically." /><div className={styles.trackingSummary}><div><span>YTM Plan</span><strong>₹{totalPlan.toFixed(2)}L</strong></div><div><span>YTM Actual</span><strong>₹{totalActual.toFixed(2)}L</strong></div><div><span>Line of sight</span><strong>₹{totalLineOfSight.toFixed(2)}L</strong></div><div><span>Achievement</span><strong>{totalPlan ? `${Math.round(totalActual / totalPlan * 100)}%` : "Not started"}</strong></div></div><div className={styles.trackingTable}><table><thead><tr><th>Month</th><th>FTM Plan (₹L)</th><th>FTM Actual (₹L)</th><th>Line of sight (₹L)</th><th>KPI actual</th><th>Status</th><th>Finance</th></tr></thead><tbody>{charter.monthly_tracking.map((entry, index) => <tr key={entry.month}><th scope="row">{entry.month}</th>{(["ftm_plan", "ftm_actual", "line_of_sight", "kpi_actual"] as const).map((field) => <td key={field}><input aria-label={`${entry.month} ${field.replaceAll("_", " ")}`} type="number" step="0.01" value={entry[field]} onChange={(event) => onUpdateMonth(index, field, event.target.value)} /></td>)}<td><SelectField id={`tracking-status-${index}`} name={`tracking_status_${index}`} label={`${entry.month} status`} value={entry.status} onChange={(value) => onUpdateMonth(index, "status", value)} disabled={readOnly} options={[{ value: "", label: "Not set" }, { value: "on_track", label: "On Track" }, { value: "delayed", label: "Delayed" }, { value: "achieved", label: "Achieved" }]} /></td><td><span className={styles.financeState}>{entry.finance_approved ? "Approved" : "Pending"}</span></td></tr>)}</tbody></table></div></section>
    </fieldset>
    {!readOnly ? <div className={styles.formActions}><button type="button" className={styles.secondaryButton} disabled={Boolean(busy)} onClick={onSave}>{busy === "save-charter" ? "Saving draft" : "Save charter draft"}</button><button type="button" className={styles.primaryButton} disabled={Boolean(busy)} onClick={onSubmit}>{busy === "submit-charter" ? "Submitting charter" : "Submit project charter"}<Send size={15} /></button></div> : null}
  </form>;
}

function SectionHeading({ eyebrow, title, description }: { eyebrow: string; title: string; description: string }) { return <header className={styles.sectionHeading}><p>{eyebrow}</p><h2>{title}</h2><span>{description}</span></header>; }
function Detail({ label, value }: { label: string; value: string }) { return <article><span>{label}</span><p>{value || "Not provided"}</p></article>; }
function Financial({ label, inr, usd }: { label: string; inr: string | null; usd: string | null }) { return <div><span>{label}</span><p>{currency(inr)}</p>{usd ? <small>{new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(Number(usd))} USD</small> : null}</div>; }
function DetailItem({ label, value }: { label: string; value: string | null }) { return <div><dt>{label}</dt><dd>{value || "Not provided"}</dd></div>; }
function Field({ label, hint, children }: { label: string; hint: string; children: React.ReactNode }) { return <label className={styles.field}><span>{label}</span><small>{hint}</small>{children}</label>; }
function toDraft(idea: Idea): CharterDraft {
  const charter = idea.charter;
  if (!charter) return { ...emptyCharter, monthly_tracking: emptyCharter.monthly_tracking.map((entry) => ({ ...entry })), department_id: idea.department_id ?? "", site_id: idea.site_id ?? "", impact_areas: idea.impacts };
  return {
    sponsor: charter.sponsor, leader: charter.leader, department_id: charter.department_id ?? "",
    site_id: charter.site_id ?? "", start_date: charter.start_date ?? "",
    target_completion_date: charter.target_completion_date ?? "", team_members: charter.team_members.join("\n"),
    team_membership_ids: charter.team_membership_ids ?? [], in_scope: charter.in_scope,
    out_of_scope: charter.out_of_scope, objective: charter.objective, benefit_type: charter.benefit_type,
    kpi_name: charter.kpi_name, budget_approved: charter.budget_approved ?? "",
    impact_areas: charter.impact_areas, belt_level: charter.belt_level ?? "",
    action_items: charter.action_items.map((item) => ({ action: item.action, plan_start: item.plan_start ?? "", plan_end: item.plan_end ?? "", actual_start: item.actual_start ?? "", actual_end: item.actual_end ?? "", owner: item.owner, status: item.status, phase: item.phase })),
    monthly_tracking: months.map((month) => { const entry = charter.monthly_tracking.find((item) => item.month === month); return entry ? { ...entry, ftm_plan: entry.ftm_plan ?? "", ftm_actual: entry.ftm_actual ?? "", line_of_sight: entry.line_of_sight ?? "", kpi_actual: entry.kpi_actual ?? "" } : { month, ftm_plan: "", ftm_actual: "", line_of_sight: "", kpi_actual: "", status: "" }; }),
  };
}
function statusLabel(value: string) { return ({ draft: "Draft", submitted: "In approval", needs_correction: "Needs correction", rejected: "Rejected", approved: "Approved", charter_in_progress: "Charter in progress", charter_submitted: "Charter submitted", withdrawn: "Withdrawn" } as Record<string, string>)[value] ?? value; }
function stageStatus(value: string) { return ({ waiting: "Upcoming", pending: "Pending", approve: "Approved", needs_correction: "Correction requested", reject: "Rejected", cancelled: "Not reached" } as Record<string, string>)[value] ?? value; }
function currency(value: string | null) { return value ? new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 0 }).format(Number(value)) : "Not provided"; }
function measure(value: string, uom: string) { return [value, uom].filter(Boolean).join(" · "); }
function capitalize(value: string) { return value.charAt(0).toUpperCase() + value.slice(1); }
function formatDate(value: string) { return new Intl.DateTimeFormat("en-IN", { day: "2-digit", month: "short", year: "numeric" }).format(new Date(value)); }
