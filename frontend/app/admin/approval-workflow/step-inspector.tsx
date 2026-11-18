"use client";

import { ArrowDown, ArrowUp, GitBranch, Trash2, UsersRound } from "lucide-react";
import { SelectField } from "@/components/ui/select-field";
import { TenantLink as Link } from "@/components/app/tenant-link";
import { type BuilderStage, type GroupOption, type NotifyKind, type Relationship, type StageMode, type UnresolvedRule, modeLabels, notifyLabels, relationshipLabels, stageProblems, unresolvedLabels } from "./builder-types";
import styles from "./builder.module.css";

type InspectorProps = {
  stage: BuilderStage;
  index: number;
  count: number;
  groups: GroupOption[];
  readOnly: boolean;
  onChange: (stage: BuilderStage) => void;
  onMove: (direction: -1 | 1) => void;
  onRemove: () => void;
};

/** The few settings a step can have. Deliberately small: type, who, mode, timing, fallback. */
export function StepInspector({ stage, index, count, groups, readOnly, onChange, onMove, onRemove }: InspectorProps) {
  const set = (patch: Partial<BuilderStage>) => onChange({ ...stage, ...patch });
  const activeGroups = groups.filter((group) => group.is_active);
  const approvalGroups = activeGroups.filter((group) => group.purpose === "approval");
  const describe = (group: GroupOption) => group.members.map((member) => member.display_name).join(", ") || "No members";
  const groupOptions = [{ value: "", label: "Choose a group", description: "Approval groups only" }, ...approvalGroups.map((group) => ({ value: group.id, label: group.name, description: describe(group) }))];
  const notifyGroupOptions = [{ value: "", label: "Choose a group", description: "Any active user group" }, ...activeGroups.map((group) => ({ value: group.id, label: group.name, description: `${group.purpose === "approval" ? "Approval" : "Notification"} · ${describe(group)}` }))];
  const problems = stageProblems(stage);
  const switchSource = (source: "dynamic" | "group") => {
    if (source === stage.source) return;
    set(source === "dynamic"
      ? { source, relationship: "reporting_manager", group_id: null, assignee_membership_id: null, name: stage.name || "Reporting manager" }
      : { source, relationship: null, assignee_membership_id: null });
  };

  return <div className={styles.inspector} aria-label={`Settings for step ${index + 1}`}>
    <header className={styles.inspectorHead}>
      <div><small>Step {index + 1} of {count}</small><h2>{stage.name.trim() || "Untitled step"}</h2></div>
      {readOnly ? null : <div className={styles.inspectorTools}>
        <button type="button" onClick={() => onMove(-1)} disabled={index === 0} aria-label="Move step up"><ArrowUp size={15} aria-hidden="true" /></button>
        <button type="button" onClick={() => onMove(1)} disabled={index === count - 1} aria-label="Move step down"><ArrowDown size={15} aria-hidden="true" /></button>
        <button type="button" data-tone="danger" onClick={onRemove} disabled={count === 1} aria-label="Remove step"><Trash2 size={15} aria-hidden="true" /></button>
      </div>}
    </header>
    <fieldset className={styles.inspectorBody} disabled={readOnly}>
      <div className={styles.setting}>
        <label htmlFor="step-name">Step name</label>
        <input id="step-name" value={stage.name} maxLength={160} onChange={(event) => set({ name: event.target.value })} placeholder="Finance Head approval" />
      </div>

      <div className={styles.setting}>
        <span className={styles.settingLabel}>Approver type</span>
        <div className={styles.segmented} role="radiogroup" aria-label="Approver type">
          <button type="button" role="radio" aria-checked={stage.source === "dynamic"} onClick={() => switchSource("dynamic")}><GitBranch size={15} aria-hidden="true" />Dynamic</button>
          <button type="button" role="radio" aria-checked={stage.source === "group"} onClick={() => switchSource("group")}><UsersRound size={15} aria-hidden="true" />Fixed</button>
        </div>
        {stage.source === "person" ? <p className={styles.hint}>This step names one person ({stage.assignee_name ?? "from an older workflow"}). Switch it to Dynamic or Fixed to use the new routing.</p> : null}
      </div>

      {stage.source === "dynamic" ? <div className={styles.setting}>
        <span className={styles.settingLabel}>Approver, from the HR file</span>
        <div className={styles.choiceList} role="radiogroup" aria-label="Dynamic approver">
          {(Object.keys(relationshipLabels) as Relationship[]).map((key) => <label key={key} className={styles.choice} data-checked={stage.relationship === key}>
            <input type="radio" name="relationship" checked={stage.relationship === key} onChange={() => set({ relationship: key, name: !stage.name || Object.values(relationshipLabels).some((label) => label.title === stage.name) ? relationshipLabels[key].title : stage.name })} />
            <span><strong>{relationshipLabels[key].title}</strong><small>{relationshipLabels[key].detail}</small></span>
          </label>)}
        </div>
      </div> : null}

      {stage.source === "group" ? <>
        <div className={styles.setting}>
          <SelectField id="step-group" name="group_id" label="Approval group" value={stage.group_id ?? ""} options={groupOptions} onChange={(value) => { const chosen = approvalGroups.find((group) => group.id === value); set({ group_id: value || null, name: stage.name || chosen?.name || "" }); }} />
          <p className={styles.hint}><Link href="/admin/user-groups">Manage user groups</Link></p>
        </div>
        <div className={styles.setting}>
          <span className={styles.settingLabel}>When the group has several people</span>
          <div className={styles.choiceList} role="radiogroup" aria-label="Multi-person mode">
            {(Object.keys(modeLabels) as StageMode[]).map((key) => <label key={key} className={styles.choice} data-checked={stage.mode === key}>
              <input type="radio" name="mode" checked={stage.mode === key} onChange={() => set({ mode: key })} />
              <ModeGlyph mode={key} />
              <span><strong>{modeLabels[key].title}</strong><small>{modeLabels[key].detail}</small></span>
            </label>)}
          </div>
        </div>
      </> : null}

      <div className={styles.setting}>
        <label htmlFor="step-sla">Response time (hours)</label>
        <input id="step-sla" type="number" min={1} max={8760} value={stage.sla_hours} onChange={(event) => set({ sla_hours: Number(event.target.value) })} />
      </div>

      <div className={styles.setting}>
        <SelectField id="step-unresolved" name="on_unresolved" label="If no approver is found" value={stage.on_unresolved} onChange={(value) => set({ on_unresolved: value as UnresolvedRule })} options={(Object.keys(unresolvedLabels) as UnresolvedRule[]).map((key) => ({ value: key, label: unresolvedLabels[key], description: key === "skip" ? "Go straight to the next step" : key === "fallback_group" ? "Any one person in that group decides" : "The first available Workspace Admin" }))} />
        {stage.on_unresolved === "fallback_group" ? <SelectField id="step-fallback" name="fallback_group_id" label="Fallback group" value={stage.fallback_group_id ?? ""} options={groupOptions} onChange={(value) => set({ fallback_group_id: value || null })} /> : null}
        <p className={styles.hint}>For example: the submitter is the head of department, someone left, or the group is empty. Submitters never approve their own ideas.</p>
      </div>

      <div className={styles.setting}>
        <SelectField id="step-notify" name="notify_kind" label="Also notify for comments" value={stage.notify_kind} onChange={(value) => set({ notify_kind: value as NotifyKind, notify_group_id: value === "group" ? stage.notify_group_id : null })} options={(Object.keys(notifyLabels) as NotifyKind[]).map((key) => ({ value: key, label: notifyLabels[key].title, description: notifyLabels[key].detail }))} />
        {stage.notify_kind === "group" ? <SelectField id="step-notify-group" name="notify_group_id" label="Group to notify" value={stage.notify_group_id ?? ""} options={notifyGroupOptions} onChange={(value) => set({ notify_group_id: value || null })} /> : null}
        {stage.notify_kind !== "none" ? <p className={styles.hint}>When this step starts they get the idea by email and can comment. Comments don&apos;t block the decision, but the approver confirms before deciding if any are unanswered.</p> : null}
      </div>

      <label className={styles.toggle}>
        <input type="checkbox" checked={stage.skip_if_same_as_previous} onChange={(event) => set({ skip_if_same_as_previous: event.target.checked })} />
        <span><strong>Skip if it is the same approver as the previous step</strong><small>Avoids asking the same person twice, e.g. when the reporting manager is also the HoD.</small></span>
      </label>
    </fieldset>
    {problems.length ? <ul className={styles.problems}>{problems.map((problem) => <li key={problem}>{problem}</li>)}</ul> : null}
  </div>;
}

/** A tiny picture of how approvers are arranged in each mode. */
function ModeGlyph({ mode }: { mode: StageMode }) {
  const dots = mode === "round_robin" ? 1 : 3;
  return <svg className={styles.glyph} viewBox="0 0 40 24" aria-hidden="true">
    {mode === "all_sequential"
      ? <>{[6, 20, 34].map((x) => <circle key={x} cx={x} cy={12} r={4} />)}<path d="M10 12h6M24 12h6" /></>
      : mode === "round_robin"
        ? <><circle cx={20} cy={12} r={4} /><path d="M9 7a12 12 0 0 1 22 0M31 17a12 12 0 0 1-22 0" fill="none" /></>
        : <>{[5, 12, 19].slice(0, dots).map((y) => <circle key={y} cx={mode === "any" && y !== 12 ? 26 : 26} cy={y} r={3.5} data-dim={mode === "any" && y !== 12} />)}<path d="M4 12h8M12 12L22 5M12 12h10M12 12l10 7" fill="none" /></>}
  </svg>;
}
