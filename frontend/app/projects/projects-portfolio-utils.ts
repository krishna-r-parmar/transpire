export type ProjectPortfolioRecord = {
  id: string;
  idea_id: string;
  reference: string;
  idea_reference: string;
  title: string;
  status: string;
  health: string;
  lead_name: string;
  site: string | null;
  department: string | null;
  target_completion_date: string | null;
  baseline_version: number;
  milestone_count: number;
  progress: string;
  target: string;
  achieved: string;
  validated: string;
  line_of_sight: string;
  projected_outcome: string;
  updated_at: string;
};

export type PortfolioFilters = {
  query: string;
  status: string;
  health: string;
  site: string;
  department: string;
};

export function filterProjects(
  projects: ProjectPortfolioRecord[],
  filters: PortfolioFilters,
) {
  const term = filters.query.trim().toLocaleLowerCase();

  return projects.filter((project) => {
    const matchesSearch = !term || [
      project.reference,
      project.idea_reference,
      project.title,
      project.lead_name,
      project.site,
      project.department,
    ].some((value) => value?.toLocaleLowerCase().includes(term));

    return matchesSearch
      && (!filters.status || project.status === filters.status)
      && (!filters.health || project.health === filters.health)
      && (!filters.site || project.site === filters.site)
      && (!filters.department || project.department === filters.department);
  });
}

export function uniqueProjectValues(
  projects: ProjectPortfolioRecord[],
  field: "site" | "department",
) {
  return [...new Set(projects.map((project) => project[field]).filter(Boolean) as string[])]
    .sort((left, right) => left.localeCompare(right));
}

export function summarizeFinancials(projects: ProjectPortfolioRecord[]) {
  return projects.reduce(
    (summary, project) => ({
      target: summary.target + Number(project.target || 0),
      achieved: summary.achieved + Number(project.achieved || 0),
      lineOfSight: summary.lineOfSight + Number(project.line_of_sight || 0),
    }),
    { target: 0, achieved: 0, lineOfSight: 0 },
  );
}

export function formatLakhs(value: string | number) {
  return `₹${Number(value).toLocaleString("en-IN", { maximumFractionDigits: 2 })} L`;
}
