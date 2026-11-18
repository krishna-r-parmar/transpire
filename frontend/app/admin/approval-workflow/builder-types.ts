export type StageSource = "dynamic" | "group" | "person";
export type Relationship = "reporting_manager" | "hod";
export type StageMode = "any" | "round_robin" | "all_sequential" | "all_parallel";
export type UnresolvedRule = "skip" | "fallback_group" | "fallback_admin";
export type NotifyKind = "none" | "group" | "hods_same_location" | "hods_all";

/** One step as drawn in the builder; `uid` only identifies the box on screen. */
export type BuilderStage = {
  uid: string;
  key: string;
  name: string;
  source: StageSource;
  relationship: Relationship | null;
  group_id: string | null;
  assignee_membership_id: string | null;
  assignee_name?: string | null;
  mode: StageMode;
  on_unresolved: UnresolvedRule;
  fallback_group_id: string | null;
  skip_if_same_as_previous: boolean;
  notify_kind: NotifyKind;
  notify_group_id: string | null;
  sla_hours: number;
};

export type StoredStage = Omit<BuilderStage, "uid"> & { group_name?: string | null; fallback_group_name?: string | null; notify_group_name?: string | null; required?: boolean };
export type Version = { id: string; version: number; status: "draft" | "published" | "retired"; stages: StoredStage[]; published_at: string | null; created_at: string };
export type Workflow = { id: string; key: string; name: string; description: string; is_active: boolean; versions: Version[] };
export type GroupOption = { id: string; name: string; purpose: "approval" | "notification"; is_active: boolean; members: { display_name: string; status: string }[] };
export type PreviewStep = { key: string; name: string; outcome: "assigned" | "skipped"; mode: string; approvers: { display_name: string; email: string | null }[]; note: string };
export type Preview = { employee_name: string; employee_email: string | null; steps: PreviewStep[] };
export type DirectoryEmployee = { employee_id: string; display_name: string; email: string | null; department: string; status: string; manager_name: string | null; hod_name: string | null };

export const relationshipLabels: Record<Relationship, { title: string; detail: string }> = {
  reporting_manager: { title: "Reporting manager", detail: "The submitter's manager in the HR file" },
  hod: { title: "Head of department", detail: "The submitter's HoD in the HR file" },
};

export const modeLabels: Record<StageMode, { title: string; detail: string }> = {
  any: { title: "Any one", detail: "Everyone is asked; the first decision counts" },
  round_robin: { title: "Round robin", detail: "One person, taking turns across ideas" },
  all_sequential: { title: "All, in sequence", detail: "Everyone approves, one after another" },
  all_parallel: { title: "All, in parallel", detail: "Everyone approves, at the same time" },
};

export const notifyLabels: Record<NotifyKind, { title: string; detail: string }> = {
  none: { title: "No one", detail: "Only the approvers are told" },
  group: { title: "A user group", detail: "Everyone in the chosen group" },
  hods_same_location: { title: "Other HoDs, same location", detail: "HoDs from the HR file at the submitter's location" },
  hods_all: { title: "All other HoDs", detail: "Every HoD in the HR file. Can be a lot of email" },
};

export const unresolvedLabels: Record<UnresolvedRule, string> = {
  skip: "Skip this step",
  fallback_group: "Send to another group",
  fallback_admin: "Send to a Workspace Admin",
};

let counter = 0;
export const newUid = () => `step-${Date.now().toString(36)}-${(counter += 1)}`;

export const slugify = (value: string) => value.toLocaleLowerCase().trim().replace(/[^a-z0-9]+/g, "_").replace(/^_|_$/g, "") || "step";

export function newStage(source: "dynamic" | "group"): BuilderStage {
  return {
    uid: newUid(),
    key: "",
    name: source === "dynamic" ? "Reporting manager" : "",
    source,
    relationship: source === "dynamic" ? "reporting_manager" : null,
    group_id: null,
    assignee_membership_id: null,
    mode: "any",
    on_unresolved: "skip",
    fallback_group_id: null,
    skip_if_same_as_previous: true,
    notify_kind: "none",
    notify_group_id: null,
    sla_hours: 48,
  };
}

export function fromStored(stage: StoredStage): BuilderStage {
  return {
    uid: newUid(),
    key: stage.key,
    name: stage.name,
    source: (stage.source ?? (stage.assignee_membership_id ? "person" : "group")) as StageSource,
    relationship: stage.relationship ?? null,
    group_id: stage.group_id ?? null,
    assignee_membership_id: stage.assignee_membership_id ?? null,
    assignee_name: stage.assignee_name ?? null,
    mode: stage.mode ?? "any",
    on_unresolved: stage.on_unresolved ?? "skip",
    fallback_group_id: stage.fallback_group_id ?? null,
    skip_if_same_as_previous: stage.skip_if_same_as_previous ?? true,
    notify_kind: stage.notify_kind ?? "none",
    notify_group_id: stage.notify_group_id ?? null,
    sla_hours: stage.sla_hours ?? 48,
  };
}

/** What still needs choosing before a step can be saved; empty when complete. */
export function stageProblems(stage: BuilderStage): string[] {
  const problems: string[] = [];
  if (stage.name.trim().length < 2) problems.push("Name the step");
  if (stage.source === "dynamic" && !stage.relationship) problems.push("Choose RM or HoD");
  if (stage.source === "group" && !stage.group_id) problems.push("Choose an approver group");
  if (stage.source === "person" && !stage.assignee_membership_id) problems.push("Choose a person");
  if (stage.on_unresolved === "fallback_group" && !stage.fallback_group_id) problems.push("Choose the fallback group");
  if (stage.notify_kind === "group" && !stage.notify_group_id) problems.push("Choose the group to notify");
  if (!Number.isFinite(stage.sla_hours) || stage.sla_hours < 1) problems.push("Set a response time");
  return problems;
}

/** Stage keys must be unique; derive them from names. */
export function toPayload(stages: BuilderStage[]) {
  const used = new Set<string>();
  return stages.map((stage) => {
    const base = stage.key || slugify(stage.name);
    let key = base;
    for (let suffix = 2; used.has(key); suffix += 1) key = `${base}_${suffix}`;
    used.add(key);
    return {
      key,
      name: stage.name.trim(),
      source: stage.source,
      relationship: stage.source === "dynamic" ? stage.relationship : null,
      group_id: stage.source === "group" ? stage.group_id : null,
      assignee_membership_id: stage.source === "person" ? stage.assignee_membership_id : null,
      mode: stage.mode,
      on_unresolved: stage.on_unresolved,
      fallback_group_id: stage.on_unresolved === "fallback_group" ? stage.fallback_group_id : null,
      skip_if_same_as_previous: stage.skip_if_same_as_previous,
      notify_kind: stage.notify_kind,
      notify_group_id: stage.notify_kind === "group" ? stage.notify_group_id : null,
      sla_hours: stage.sla_hours,
      required: true,
    };
  });
}
