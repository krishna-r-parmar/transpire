"use client";

import { AlertTriangle, BellRing, CheckCircle2, Clock, GitBranch, Lightbulb, Plus, SkipForward, UserRound, UsersRound } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { type BuilderStage, type GroupOption, type PreviewStep, modeLabels, relationshipLabels, stageProblems, unresolvedLabels } from "./builder-types";
import styles from "./builder.module.css";

type CanvasProps = {
  stages: BuilderStage[];
  groups: GroupOption[];
  selected: string | null;
  preview: PreviewStep[] | null;
  readOnly: boolean;
  onSelect: (uid: string) => void;
  onInsert: (index: number, source: "dynamic" | "group") => void;
};

/** The approval route drawn top to bottom: trigger, steps, outcome. */
export function WorkflowCanvas({ stages, groups, selected, preview, readOnly, onSelect, onInsert }: CanvasProps) {
  return <ol className={styles.canvas} aria-label="Approval route">
    <li className={styles.terminal} data-kind="start">
      <span className={styles.terminalIcon}><Lightbulb size={18} aria-hidden="true" /></span>
      <span><strong>Idea submitted</strong><small>By any Contributor</small></span>
    </li>
    <Connector index={0} readOnly={readOnly} onInsert={onInsert} />
    {stages.map((stage, index) => <li key={stage.uid} className={styles.slot}>
      <StepNode stage={stage} index={index} groups={groups} selected={selected === stage.uid} preview={preview?.[index] ?? null} onSelect={onSelect} />
      <Connector index={index + 1} readOnly={readOnly} onInsert={onInsert} />
    </li>)}
    <li className={styles.terminal} data-kind="end">
      <span className={styles.terminalIcon}><CheckCircle2 size={18} aria-hidden="true" /></span>
      <span><strong>Approved</strong><small>The project charter opens for the submitter</small></span>
    </li>
  </ol>;
}

function Connector({ index, readOnly, onInsert }: { index: number; readOnly: boolean; onInsert: CanvasProps["onInsert"] }) {
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const close = (event: MouseEvent) => { if (!root.current?.contains(event.target as Node)) setOpen(false); };
    const escape = (event: KeyboardEvent) => { if (event.key === "Escape") setOpen(false); };
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", escape);
    return () => { document.removeEventListener("mousedown", close); document.removeEventListener("keydown", escape); };
  }, [open]);
  return <div className={styles.connector} ref={root}>
    <span className={styles.line} aria-hidden="true" />
    {readOnly ? null : <>
      <button type="button" className={styles.addButton} aria-expanded={open} aria-label={`Add a step at position ${index + 1}`} onClick={() => setOpen((value) => !value)}><Plus size={14} aria-hidden="true" /></button>
      {open ? <div className={styles.addMenu} role="menu">
        <button type="button" role="menuitem" onClick={() => { onInsert(index, "dynamic"); setOpen(false); }}>
          <span data-kind="dynamic"><GitBranch size={16} aria-hidden="true" /></span>
          <span><strong>Dynamic approver</strong><small>Reporting manager or HoD, from the HR file</small></span>
        </button>
        <button type="button" role="menuitem" onClick={() => { onInsert(index, "group"); setOpen(false); }}>
          <span data-kind="group"><UsersRound size={16} aria-hidden="true" /></span>
          <span><strong>Fixed approver group</strong><small>A named group such as Finance Head</small></span>
        </button>
      </div> : null}
    </>}
  </div>;
}

function StepNode({ stage, index, groups, selected, preview, onSelect }: { stage: BuilderStage; index: number; groups: GroupOption[]; selected: boolean; preview: PreviewStep | null; onSelect: (uid: string) => void }) {
  const problems = stageProblems(stage);
  const group = groups.find((item) => item.id === stage.group_id);
  const fallback = groups.find((item) => item.id === stage.fallback_group_id);
  const kind = stage.source === "dynamic" ? "dynamic" : stage.source === "group" ? "group" : "person";
  const Icon = kind === "dynamic" ? GitBranch : kind === "group" ? UsersRound : UserRound;
  const who = stage.source === "dynamic"
    ? stage.relationship ? relationshipLabels[stage.relationship].title : "Not chosen"
    : stage.source === "group" ? group?.name ?? "No group chosen" : stage.assignee_name ?? "Named person";
  return <button type="button" className={styles.node} data-kind={kind} data-selected={selected} data-invalid={problems.length > 0} onClick={() => onSelect(stage.uid)} aria-pressed={selected}>
    <span className={styles.nodeHead}>
      <span className={styles.nodeIcon}><Icon size={16} aria-hidden="true" /></span>
      <span className={styles.nodeTitle}><small>Step {index + 1} · {kind === "dynamic" ? "Dynamic" : kind === "group" ? "Fixed group" : "Named person"}</small><strong>{stage.name.trim() || "Untitled step"}</strong></span>
    </span>
    <span className={styles.nodeWho}>{who}{stage.source === "group" && group ? <em>{modeLabels[stage.mode].title}</em> : null}</span>
    <span className={styles.chips}>
      <span><Clock size={12} aria-hidden="true" />{stage.sla_hours}h</span>
      <span title="If no approver is found">If none: {stage.on_unresolved === "fallback_group" ? fallback?.name ?? "group" : unresolvedLabels[stage.on_unresolved].replace("Send to a ", "").replace("Skip this step", "skip")}</span>
      {stage.skip_if_same_as_previous ? <span><SkipForward size={12} aria-hidden="true" />Skips repeats</span> : null}
      {stage.notify_kind !== "none" ? <span data-tone="notify"><BellRing size={12} aria-hidden="true" />Notifies {stage.notify_kind === "group" ? groups.find((item) => item.id === stage.notify_group_id)?.name ?? "a group" : stage.notify_kind === "hods_all" ? "all HoDs" : "HoDs here"}</span> : null}
    </span>
    {problems.length ? <span className={styles.problem}><AlertTriangle size={13} aria-hidden="true" />{problems[0]}</span> : null}
    {preview ? <span className={styles.previewResult} data-outcome={preview.outcome}>
      {preview.outcome === "assigned"
        ? <><strong>{preview.approvers.map((approver) => approver.display_name).join(", ")}</strong><small>{preview.note}</small></>
        : <><strong>Skipped</strong><small>{preview.note}</small></>}
    </span> : null}
  </button>;
}
