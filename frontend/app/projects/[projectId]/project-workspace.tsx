"use client";

import {
  Activity,
  ArrowLeft,
  BarChart3,
  CalendarClock,
  CheckCircle2,
  FileClock,
  Flag,
  FolderKanban,
  IndianRupee,
  ListChecks,
  RefreshCw,
  ShieldCheck,
  Target,
  UserRound,
  Users,
} from "lucide-react";
import { TenantLink as Link } from "@/components/app/tenant-link";
import { useTenantRouter as useRouter } from "@/lib/use-tenant-router";
import { Fragment, useCallback, useEffect, useState } from "react";
import { AdminShell } from "@/components/admin/admin-shell";
import { SectionCard, StatusPill, SummaryStrip } from "@/components/ui/workspace";
import { apiRequest } from "@/lib/api";
import { useSession } from "@/lib/use-session";
import { formatLakhs } from "../projects-portfolio-utils";
import { HealthPill, ProjectStatusPill } from "../project-status";
import { BenefitTracker, type BenefitMonth, type BenefitTracking } from "./benefit-tracker";
import { MilestoneBoard } from "./milestone-board";
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
  baseline_planned_end?: string | null; baseline_weight?: string | null; benefits_start?: boolean; variance_days?: number | null;
};
type BenefitPeriod = BenefitMonth;
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
  benefits?: BenefitTracking | null;
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
      const loaded = body as ProjectWorkspaceRecord;
      if ((loaded as { status?: string }).status === "charter_in_progress") { router.replace(`/projects/${loaded.id}/charter`); return; }
      setProject(loaded);
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
      actions={!loading && project ? <div className={styles.headerPills}><ProjectStatusPill status={project.status} /><HealthPill health={project.health} /></div> : undefined}
    >
      {loading ? <WorkspaceSkeleton /> : null}
      {error ? (
        <section className={styles.error} role="alert">
          <FolderKanban aria-hidden="true" size={26} />
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
              <span>Baseline v{project.baseline_version}</span>
              <span>From <Link href={`/ideas/${project.idea_id}`}>{project.idea_reference}</Link></span>
            </div>
          </div>

          <WorkspaceSummary project={project} />

          <nav className={styles.tabs} role="tablist" aria-label="Project workspace sections">
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
                  <Icon aria-hidden="true" size={16} />{tab.label}
                </button>
              );
            })}
          </nav>

          <div className={styles.panel} role="tabpanel">
            {section === "overview" ? <Overview project={project} /> : null}
            {section === "milestones" ? <MilestoneBoard project={project} onChange={setProject} /> : null}
            {section === "benefits" ? <BenefitTracker project={project} onChange={setProject} onOpenMilestones={() => setSection("milestones")} /> : null}
            {section === "charter" ? <Charter project={project} /> : null}
            {section === "team" ? <Team project={project} /> : null}
            {section === "activity" ? <ActivityPanel project={project} /> : null}
          </div>
        </>
      ) : null}
    </AdminShell>
  );
}

function WorkspaceSummary({ project }: { project: ProjectWorkspaceRecord }) {
  const completed = project.milestones.filter((milestone) => milestone.status === "complete").length;
  const next = [...project.milestones].sort((left, right) => left.position - right.position).find((milestone) => milestone.status !== "complete");
  return <SummaryStrip label="Project summary" items={[
    { icon: <ListChecks size={18} />, value: `${Number(project.progress).toFixed(0)}%`, label: "Complete", note: project.milestones.length ? `${completed} of ${project.milestones.length} milestones` : "Plan not created" },
    { icon: <IndianRupee size={18} />, value: formatLakhs(project.achieved), label: "Achieved", note: `of ${formatLakhs(project.target)} target`, tone: "success" },
    { icon: <Users size={18} />, value: project.team.length, label: "Team members", note: `Lead: ${project.lead_name || "Not recorded"}` },
    { icon: <CalendarClock size={18} />, value: next ? (next.planned_end ? formatShortDate(next.planned_end) : "Not dated") : "None", label: "Next milestone", note: next ? next.title || `Milestone ${next.position}` : project.milestones.length ? "All milestones complete" : "Plan not created", tone: next ? "warning" : undefined },
  ]} />;
}

function Overview({ project }: { project: ProjectWorkspaceRecord }) {
  return (
    <div className={styles.overviewGrid}>
      <SectionCard icon={<Target size={17} />} title="Objective and scope" description="The active charter baseline defines what this project is accountable for delivering.">
        <ReadOnly label="SMART objective" value={project.charter.objective} />
        <div className={styles.scopeGrid}>
          <ReadOnly label="In scope" value={project.charter.in_scope} />
          <ReadOnly label="Out of scope" value={project.charter.out_of_scope} />
        </div>
      </SectionCard>
      <SectionCard icon={<FileClock size={17} />} title="Project facts" tinted>
        <dl className={styles.facts}>
          <Fact label="Project lead" value={project.lead_name} />
          <Fact label="Sponsor" value={project.charter.sponsor} />
          <Fact label="Site" value={project.site} />
          <Fact label="Department" value={project.department} />
          <Fact label="Start" value={formatDate(project.start_date)} />
          <Fact label="Target completion" value={formatDate(project.target_completion_date)} />
          <Fact label="Benefit type" value={labelize(project.charter.benefit_type)} />
          <Fact label="KPI" value={project.charter.kpi_name} />
          <Fact label="Validated" value={formatLakhs(project.validated)} />
          <Fact label="LOS" value={formatLakhs(project.line_of_sight)} />
          <Fact label="Projected" value={formatLakhs(project.projected_outcome)} />
        </dl>
      </SectionCard>
    </div>
  );
}

function Charter({ project }: { project: ProjectWorkspaceRecord }) {
  return (
    <div className={styles.charterGrid}>
      <SectionCard icon={<FileClock size={17} />} title="Published baselines" description="Every OE revision retains its reason and author." flush>
        <div className={styles.baselines}>
          {project.baselines.map((baseline) => <article key={baseline.id} data-active={baseline.is_active}><span>v{baseline.version}</span><div><strong>{baseline.reason}</strong><small>{baseline.created_by_name} · {formatDateTime(baseline.published_at)}</small></div>{baseline.is_active ? <StatusPill tone="success" icon={<ShieldCheck aria-hidden="true" size={14} />}>Active</StatusPill> : null}</article>)}
        </div>
      </SectionCard>
      <SectionCard icon={<ShieldCheck size={17} />} title={`Baseline v${project.baseline_version}`} description="The active baseline remains the execution reference.">
        <dl className={styles.facts}>
          <Fact label="Leader" value={project.charter.leader} />
          <Fact label="Sponsor" value={project.charter.sponsor} />
          <Fact label="Approved budget" value={project.charter.budget_approved ? `₹${Number(project.charter.budget_approved).toLocaleString("en-IN")}` : null} />
          <Fact label="Belt level" value={project.charter.belt_level} />
          <Fact label="Impact areas" value={project.charter.impact_areas.map(labelize).join(", ")} />
          <Fact label="Additional team" value={project.charter.team_members.join(", ")} />
        </dl>
        <div className={styles.charterText}>
          <ReadOnly label="Objective" value={project.charter.objective} />
          <div className={styles.scopeGrid}><ReadOnly label="In scope" value={project.charter.in_scope} /><ReadOnly label="Out of scope" value={project.charter.out_of_scope} /></div>
        </div>
      </SectionCard>
    </div>
  );
}

function Team({ project }: { project: ProjectWorkspaceRecord }) {
  return (
    <SectionCard icon={<Users size={17} />} title="Project team" description="The Project Lead and assigned team can contribute to delivery. Invitation responses remain visible without blocking the project." meta={project.team.length ? `${project.team.length} members` : undefined} flush>
      <div className={styles.teamLead}><span aria-hidden="true"><UserRound size={20} /></span><div><small>Project lead</small><h3>{project.lead_name || "Not recorded"}</h3><span>{[project.department, project.site].filter(Boolean).join(" · ") || "Organisation assignment not recorded"}</span></div></div>
      {project.team.length ? <div className={styles.teamList}>{project.team.map((member) => <article key={member.id}><span aria-hidden="true">{initials(member.name)}</span><div><strong>{member.name}</strong><small>{member.email}</small></div><StatusPill tone={member.status === "accepted" ? "success" : "warning"} icon={member.status === "accepted" ? <CheckCircle2 size={14} aria-hidden="true" /> : <FileClock size={14} aria-hidden="true" />}>{labelize(member.status)}</StatusPill></article>)}</div> : <EmptyState icon={Users} title="No TRANSPIRE members were assigned." text="Additional names from the published charter remain visible in Charter & revisions." />}
    </SectionCard>
  );
}

function ActivityPanel({ project }: { project: ProjectWorkspaceRecord }) {
  return (
    <SectionCard icon={<Activity size={17} />} title="Project activity" description="Submission, approval, charter, and future execution events are retained in chronological order." meta={project.activity.length ? `${project.activity.length} events` : undefined} flush>
      {project.activity.length ? <ol className={styles.activityList}>{project.activity.map((event) => <li key={event.id}><span><CheckCircle2 aria-hidden="true" size={15} /></span><div><strong>{event.summary}</strong><small>{event.actor_name ?? "System"} · {formatDateTime(event.created_at)}</small></div><i>{labelize(event.event_type.replace(".", " "))}</i></li>)}</ol> : <EmptyState icon={Activity} title="No activity has been recorded." text="Governed project events will appear here as the execution lifecycle advances." />}
    </SectionCard>
  );
}


function WorkspaceSkeleton() { return <div className={styles.skeleton} aria-label="Loading project"><span /><span /><span /></div>; }
function Fact({ label, value }: { label: string; value: string | null | undefined }) { return <div><dt>{label}</dt><dd>{value || "Not provided"}</dd></div>; }
function ReadOnly({ label, value }: { label: string; value: string | null | undefined }) { return <div className={styles.readOnly}><span>{label}</span><p>{value || "Not provided"}</p></div>; }
function EmptyState({ icon: Icon, title, text }: { icon: typeof Target; title: string; text: string }) { return <div className={styles.empty}><Icon aria-hidden="true" /><h3>{title}</h3><p>{text}</p></div>; }
function formatDate(value: string | null) { return value ? new Intl.DateTimeFormat("en-IN", { day: "2-digit", month: "short", year: "numeric", timeZone: "UTC" }).format(new Date(`${value}T00:00:00Z`)) : "Not recorded"; }
function formatDateTime(value: string) { return new Intl.DateTimeFormat("en-IN", { day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" }).format(new Date(value)); }
function formatShortDate(value: string) { return new Intl.DateTimeFormat("en-IN", { day: "2-digit", month: "short", timeZone: "UTC" }).format(new Date(`${value}T00:00:00Z`)); }
function labelize(value: string) { return value.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase()); }
function initials(name: string) { return name.split(/\s+/).filter(Boolean).slice(0, 2).map((part) => part[0]?.toUpperCase()).join("") || "?"; }
