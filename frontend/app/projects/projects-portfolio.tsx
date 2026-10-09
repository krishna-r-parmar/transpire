"use client";

import {
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  CircleDot,
  FolderKanban,
  RefreshCw,
  SlidersHorizontal,
  X,
} from "lucide-react";
import { TenantLink as Link } from "@/components/app/tenant-link";
import { useTenantRouter as useRouter } from "@/lib/use-tenant-router";
import { useCallback, useEffect, useMemo, useState } from "react";
import { AdminShell } from "@/components/admin/admin-shell";
import { SearchField } from "@/components/ui/search-field";
import { SelectField } from "@/components/ui/select-field";
import { apiRequest } from "@/lib/api";
import { useSession } from "@/lib/use-session";
import {
  filterProjects,
  formatLakhs,
  summarizeFinancials,
  uniqueProjectValues,
  type ProjectPortfolioRecord,
} from "./projects-portfolio-utils";
import styles from "./projects.module.css";

const statusLabels: Record<string, string> = {
  ready_to_start: "Ready to start",
  in_progress: "In progress",
  on_hold: "On hold",
  completion_review: "Completion review",
  oe_verified: "OE verified",
  finance_validation: "Finance validation",
  success: "Success",
  cancelled: "Cancelled",
  unsuccessful: "Closed unsuccessful",
};

const healthLabels: Record<string, string> = {
  not_set: "Not assessed",
  on_track: "On track",
  at_risk: "At risk",
  blocked: "Blocked",
};

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
  const filtersActive = Boolean(query || status || health || site || department);
  const active = projects.filter((project) =>
    ["ready_to_start", "in_progress", "on_hold"].includes(project.status),
  ).length;
  const atRisk = projects.filter((project) =>
    ["at_risk", "blocked"].includes(project.health),
  ).length;
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
      <section className={styles.summary} aria-label="Project portfolio summary">
        <div><CircleDot /><span><strong>{active}</strong>Active</span></div>
        <div><AlertTriangle /><span><strong>{atRisk}</strong>At risk</span></div>
        <div><FolderKanban /><span><strong>{inReview}</strong>Completion review</span></div>
        <div><CheckCircle2 /><span><strong>{success}</strong>Success</span></div>
      </section>

      <section className={styles.discovery} aria-labelledby="project-discovery-heading">
        <header>
          <div>
            <SlidersHorizontal aria-hidden="true" />
            <span>
              <h2 id="project-discovery-heading">Find project work</h2>
              <p>Filter by delivery state or organisation, then compare forecast value.</p>
            </span>
          </div>
          {filtersActive ? (
            <button type="button" onClick={clearFilters}>
              <X aria-hidden="true" size={14} />
              Clear filters
            </button>
          ) : null}
        </header>

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
              ...Object.entries(statusLabels).map(([value, label]) => ({
                value,
                label,
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
              ...Object.entries(healthLabels).map(([value, label]) => ({
                value,
                label,
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
      </section>

      <section className={styles.benefitSummary} aria-labelledby="portfolio-benefit-heading">
        <header>
          <p>Filtered portfolio value</p>
          <h2 id="portfolio-benefit-heading">Benefits and line of sight</h2>
        </header>
        <dl>
          <div><dt>Target</dt><dd>{formatLakhs(financials.target)}</dd></div>
          <div><dt>Achieved</dt><dd>{formatLakhs(financials.achieved)}</dd></div>
          <div><dt>LOS</dt><dd>{formatLakhs(financials.lineOfSight)}</dd></div>
        </dl>
      </section>

      {error ? (
        <div className={styles.error} role="alert">
          <span>{error}</span>
          <button type="button" onClick={() => void loadProjects()}>
            <RefreshCw aria-hidden="true" size={14} />Retry
          </button>
        </div>
      ) : null}

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
                <th>Target</th>
                <th>Achieved</th>
                <th>LOS</th>
                <th>Projected</th>
                <th><span className={styles.srOnly}>Open</span></th>
              </tr>
            </thead>
            <tbody>
              {visible.map((project) => (
                <tr key={project.id}>
                  <td data-label="Project">
                    <Link href={`/projects/${project.id}`}>{project.title}</Link>
                    <small>{project.reference} · {project.lead_name || "Lead not recorded"}</small>
                    <small>
                      {[project.site, project.department].filter(Boolean).join(" · ")
                        || "Location not recorded"}
                    </small>
                  </td>
                  <td data-label="Status and health">
                    <span className={styles.status} data-status={project.status}>
                      {statusLabels[project.status] ?? project.status}
                    </span>
                    <small>{healthLabel(project.health)} · Baseline v{project.baseline_version}</small>
                    <small>{formatCompletionDate(project.target_completion_date)}</small>
                  </td>
                  <td data-label="Milestones">
                    <strong>{Number(project.progress).toFixed(0)}%</strong>
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
                      <ArrowRight aria-hidden="true" />
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}

      {!loadingProjects && !visible.length ? (
        <section className={styles.empty}>
          <FolderKanban aria-hidden="true" />
          <h2>{projects.length ? "No projects match these filters." : "Approved work will appear here."}</h2>
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
        </section>
      ) : null}
    </AdminShell>
  );
}

function MoneyCell({ label, value }: { label: string; value: string }) {
  return <td data-label={label}><strong className={styles.money}>{formatLakhs(value)}</strong></td>;
}

function healthLabel(value: string) {
  return value === "not_set" ? "Health not assessed" : healthLabels[value] ?? value;
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
