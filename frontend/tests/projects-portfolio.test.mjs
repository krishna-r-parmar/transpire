import assert from "node:assert/strict";
import test from "node:test";
import {
  filterProjects,
  summarizeFinancials,
  uniqueProjectValues,
} from "../app/projects/projects-portfolio-utils.ts";

const projects = [
  {
    id: "one", idea_id: "idea-one", reference: "PRJ-001", idea_reference: "IDEA-001",
    title: "Reduce batch loss", status: "in_progress", health: "on_track", lead_name: "Asha",
    site: "Naroda", department: "Operations", target_completion_date: "2026-12-31",
    baseline_version: 1, milestone_count: 2, progress: "25", target: "100", achieved: "30",
    validated: "20", line_of_sight: "50", projected_outcome: "80",
    updated_at: "2026-08-23T00:00:00Z",
  },
  {
    id: "two", idea_id: "idea-two", reference: "PRJ-002", idea_reference: "IDEA-002",
    title: "Improve changeover", status: "ready_to_start", health: "not_set", lead_name: "Vikram",
    site: "Bavla", department: "Engineering", target_completion_date: null,
    baseline_version: 1, milestone_count: 0, progress: "0", target: "75", achieved: "0",
    validated: "0", line_of_sight: "25", projected_outcome: "25",
    updated_at: "2026-08-22T00:00:00Z",
  },
];

test("portfolio discovery combines search and organisation filters", () => {
  assert.deepEqual(
    filterProjects(projects, {
      query: "batch", status: "in_progress", health: "on_track", site: "Naroda",
      department: "Operations",
    }).map((project) => project.id),
    ["one"],
  );
  assert.equal(
    filterProjects(projects, {
      query: "", status: "", health: "", site: "Naroda", department: "Engineering",
    }).length,
    0,
  );
});

test("portfolio financial summary reflects the visible project set", () => {
  assert.deepEqual(summarizeFinancials(projects), {
    target: 175,
    achieved: 30,
    lineOfSight: 75,
  });
});

test("site and department choices are unique and sorted", () => {
  assert.deepEqual(uniqueProjectValues(projects, "site"), ["Bavla", "Naroda"]);
  assert.deepEqual(uniqueProjectValues(projects, "department"), ["Engineering", "Operations"]);
});
