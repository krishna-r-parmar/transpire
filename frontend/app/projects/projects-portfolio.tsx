"use client";

import {
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  FolderKanban,
  IndianRupee,
  OctagonAlert,
  RefreshCw,
  SearchCheck,
  SlidersHorizontal,
  X,
} from "lucide-react";
import { TenantLink as Link } from "@/components/app/tenant-link";
import { useTenantRouter as useRouter } from "@/lib/use-tenant-router";
import { useCallback, useEffect, useMemo, useState } from "react";
import { AdminShell } from "@/components/admin/admin-shell";
import { SearchField } from "@/components/ui/search-field";
import { SelectField } from "@/components/ui/select-field";
import { SectionCard, SummaryStrip } from "@/components/ui/workspace";
import { apiRequest } from "@/lib/api";
import { useSession } from "@/lib/use-session";
import {
  filterProjects,
  formatLakhs,
  summarizeFinancials,
  uniqueProjectValues,
  type ProjectPortfolioRecord,
} from "./projects-portfolio-utils";
import { HealthPill, ProjectStatusPill, healthStates, healthTone, projectStatuses } from "./project-status";
import styles from "./projects.module.css";

export function ProjectsPortfolio() {
  const router = useRouter();
  const { session, loading } = useSession();
  const [projects, setProjects] = useState<ProjectPortfolioRecord[]>([]);
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("");
  const [health, setHealth] = useState("");
  const [site, setSite] = useState("");
  const [department, setDepartment] = useState("");
  const [loadingProjects, setLoadingProjects] = useState(true);
  const [error, setError] = useState("");

  const loadProjects = useCallback(async () => {
    setLoadingProjects(true);
    setError("");
    try {
      const response = await apiRequest("/projects");
      if (response.status === 401) {
        router.replace("/sign-in");
        return;
      }
      if (!response.ok) throw new Error();
      setProjects(await response.json() as ProjectPortfolioRecord[]);
    } catch {
      setError("Projects could not be reached. Check your connection, then retry.");
    } finally {
      setLoadingProjects(false);
    }
  }, [router]);

  useEffect(() => {
    if (!session) return;
    const timer = window.setTimeout(() => void loadProjects(), 0);
    return () => window.clearTimeout(timer);
  }, [loadProjects, session]);

  const visible = useMemo(
    () => filterProjects(projects, { query, status, health, site, department }),
    [department, health, projects, query, site, status],
  );
  const sites = useMemo(() => uniqueProjectValues(projects, "site"), [projects]);
  const departments = useMemo(
    () => uniqueProjectValues(projects, "department"),
    [projects],
  );
  const financials = useMemo(() => summarizeFinancials(visible), [visible]);
  const portfolio = useMemo(() => summarizeFinancials(projects), [projects]);
  const filtersActive = Boolean(query || status || health || site || department);
  const active = projects.filter((project) =>
    ["ready_to_start", "in_progress", "on_hold"].includes(project.status),
  ).length;
  const onTrack = projects.filter((project) => project.health === "on_track").length;
  const atRisk = projects.filter((project) => project.health === "at_risk").length;
  const blocked = projects.filter((project) => project.health === "blocked").length;
  const inReview = projects.filter((project) =>
    ["completion_review", "oe_verified", "finance_validation"].includes(project.status),
  ).length;
  const success = projects.filter((project) => project.status === "success").length;

  const clearFilters = () => {
    setQuery("");
    setStatus("");
    setHealth("");
    setSite("");
    setDepartment("");
  };

  if (loading || !session) {
    return <main className={styles.loading}>Opening the Projects portfolio</main>;
  }

  return (
    <AdminShell
      session={session}
      active="projects"
      eyebrow="Execution portfolio"
      title="Projects"
      description="Track implementation, benefits and completion across the organisation."
    >
      {!loadingProjects && !error ? (
        <SummaryStrip
          label="Project portfolio summary"
          items={[
            { icon: <FolderKanban size={18} />, value: active, label: "Active", note: "Ready, in progress or on hold" },
            { icon: <CheckCircle2 size={18} />, value: onTrack, label: "On track", tone: "success" },
            { icon: <AlertTriangle size={18} />, value: atRisk, label: "At risk", note: "Need attention", tone: "warning" },
            { icon: <OctagonAlert size={18} />, value: blocked, label: "Blocked", tone: "danger" },
            { icon: <SearchCheck size={18} />, value: inReview, label: "Completion review", note: `${success} closed as success` },
            { icon: <IndianRupee size={18} />, value: formatLakhs(portfolio.achieved), label: "Achieved", note: `of ${formatLakhs(portfolio.target)} target` },
          ]}
        />
      ) : null}

      {error ? (
        <div className={styles.error} role="alert">
          <span>{error}</span>
          <button type="button" onClick={() => void loadProjects()}>
            <RefreshCw aria-hidden="true" size={14} />Retry
          </button>
        </div>
      ) : null}

      <SectionCard
        icon={<SlidersHorizontal size={17} />}
        title="Find project work"
        description="Filter by delivery state or organisation, then compare forecast value."
        actions={filtersActive ? (
          <button className={styles.clear} type="button" onClick={clearFilters}>
            <X aria-hidden="true" size={14} />
            Clear filters
          </button>
        ) : undefined}
      >
        <div className={styles.searchRow}>
          <SearchField
            id="project-search"
            label="Search projects"
            value={query}
            onChange={setQuery}
            placeholder="Search project, idea, lead, site, or department"
            resultCount={visible.length}
          />
        </div>

        <div className={styles.filters}>
          <SelectField
            id="project-status"
            name="status"
            label="Status"
            value={status}
            onChange={setStatus}
            options={[
              { value: "", label: "All statuses", description: "No status restriction" },
              ...Object.entries(projectStatuses).map(([value, entry]) => ({
                value,
                label: entry.label,
                description: "Project lifecycle state",
              })),
            ]}
          />
          <SelectField
            id="project-health"
            name="health"
            label="Health"
            value={health}
            onChange={setHealth}
            options={[
              { value: "", label: "All health states", description: "No health restriction" },
              ...Object.entries(healthStates).map(([value, entry]) => ({
                value,
                label: entry.label,
                description: "Current delivery assessment",
              })),
            ]}
          />
          <SelectField
            id="project-site"
            name="site"
            label="Site"
            value={site}
            onChange={setSite}
            options={[
              { value: "", label: "All sites", description: "Across the tenant" },
              ...sites.map((value) => ({ value, label: value, description: "Project site" })),
            ]}
          />
          <SelectField
            id="project-department"
            name="department"
            label="Department"
            value={department}
            onChange={setDepartment}
            options={[
              { value: "", label: "All departments", description: "Across all functions" },
              ...departments.map((value) => ({
                value,
                label: value,
                description: "Owning department",
              })),
            ]}
          />
        </div>

        <section className={styles.benefitSummary} aria-labelledby="portfolio-benefit-heading">
          <header>
            <p>Filtered portfolio value</p>
            <h3 id="portfolio-benefit-heading">Benefits and line of sight</h3>
          </header>
          <dl>
            <div><dt>Target</dt><dd>{formatLakhs(financials.target)}</dd></div>
            <div><dt>Achieved</dt><dd>{formatLakhs(financials.achieved)}</dd></div>
            <div><dt>LOS</dt><dd>{formatLakhs(financials.lineOfSight)}</dd></div>
          </dl>
        </section>
      </SectionCard>

      <SectionCard
        className={styles.results}
        icon={<FolderKanban size={17} />}
        title="Project portfolio"
        description="Open a project for its milestones, benefits, charter and team."
        meta={loadingProjects ? undefined : `${visible.length} shown`}
        flush
      >
        {loadingProjects ? (
          <div className={styles.skeleton} aria-label="Loading projects">
            <span /><span /><span />
          </div>
        ) : null}

        {!loadingProjects && visible.length ? (
          <div className={styles.tableWrap}>
            <table>
              <thead>
                <tr>
                  <th>Project</th>
                  <th>Status and health</th>
                  <th>Milestones</th>
                  <th className={styles.numeric}>Target</th>
                  <th className={styles.numeric}>Achieved</th>
                  <th className={styles.numeric}>LOS</th>
                  <th className={styles.numeric}>Projected</th>
                  <th><span className={styles.srOnly}>Open</span></th>
                </tr>
              </thead>
              <tbody>
                {visible.map((project) => {
                  const progress = Math.min(100, Math.max(0, Number(project.progress) || 0));
                  return (
                    <tr key={project.id}>
                      <td data-label="Project">
                        <span className={styles.reference}>{project.reference}</span>
                        <Link className={styles.projectLink} href={`/projects/${project.id}`}>{project.title}</Link>
                        <small>{project.lead_name || "Lead not recorded"}</small>
                        <small>
                          {[project.site, project.department].filter(Boolean).join(" · ")
                            || "Location not recorded"}
                        </small>
                      </td>
                      <td data-label="Status and health">
                        <div className={styles.pills}>
                          <ProjectStatusPill status={project.status} />
                          <HealthPill health={project.health} />
                        </div>
                        <small>Baseline v{project.baseline_version} · {formatCompletionDate(project.target_completion_date)}</small>
                      </td>
                      <td data-label="Milestones">
                        <div className={styles.barRow}>
                          <span className={styles.bar} data-tone={healthTone(project.health)} aria-hidden="true">
                            <span style={{ width: `${progress}%` }} />
                          </span>
                          <strong>{Number(project.progress).toFixed(0)}%</strong>
                        </div>
                        <small>
                          {project.milestone_count
                            ? `${project.milestone_count} milestone${project.milestone_count === 1 ? "" : "s"}`
                            : "Plan not created"}
                        </small>
                      </td>
                      <MoneyCell label="Target" value={project.target} />
                      <MoneyCell label="Achieved" value={project.achieved} />
                      <MoneyCell label="LOS" value={project.line_of_sight} />
                      <MoneyCell label="Projected" value={project.projected_outcome} />
                      <td className={styles.open}>
                        <Link
                          href={`/projects/${project.id}`}
                          aria-label={`Open project workspace for ${project.reference}`}
                        >
                          <ArrowRight aria-hidden="true" size={16} />
                        </Link>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : null}

        {!loadingProjects && !visible.length ? (
          <div className={styles.empty}>
            <FolderKanban aria-hidden="true" size={26} />
            <h3>{projects.length ? "No projects match these filters." : "Approved work will appear here."}</h3>
            <p>
              {projects.length
                ? "Clear a filter or try a broader search."
                : "Submitting an approved project charter publishes its first baseline and creates the execution workspace."}
            </p>
            {projects.length ? (
              <button type="button" onClick={clearFilters}>Clear filters</button>
            ) : (
              <Link href="/ideas">Open Idea Bank</Link>
            )}
          </div>
        ) : null}
      </SectionCard>
    </AdminShell>
  );
}

function MoneyCell({ label, value }: { label: string; value: string }) {
  return <td className={styles.numeric} data-label={label}><strong className={styles.money}>{formatLakhs(value)}</strong></td>;
}

function formatCompletionDate(value: string | null) {
  if (!value) return "Completion date not recorded";
  return `Due ${new Intl.DateTimeFormat("en-IN", {
    day: "numeric",
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  }).format(new Date(`${value}T00:00:00Z`))}`;
}
