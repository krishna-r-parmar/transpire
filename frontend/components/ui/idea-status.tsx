import { CheckCircle2, CircleDot, FileClock, FilePenLine, Flag, RotateCcw, Undo2, XCircle } from "lucide-react";
import { StatusPill } from "./workspace";

const ideaStatuses: Record<string, { label: string; tone: "neutral" | "info" | "success" | "warning" | "danger"; Icon: typeof CircleDot }> = {
  draft: { label: "Draft", tone: "neutral", Icon: FileClock },
  submitted: { label: "In approval", tone: "info", Icon: CircleDot },
  needs_correction: { label: "Needs correction", tone: "warning", Icon: RotateCcw },
  rejected: { label: "Rejected", tone: "danger", Icon: XCircle },
  approved: { label: "Approved", tone: "success", Icon: CheckCircle2 },
  charter_in_progress: { label: "Charter in progress", tone: "info", Icon: FilePenLine },
  charter_submitted: { label: "Charter submitted", tone: "success", Icon: Flag },
  withdrawn: { label: "Withdrawn", tone: "neutral", Icon: Undo2 },
};

export function ideaStatusLabel(status: string) { return ideaStatuses[status]?.label ?? status; }

export function IdeaStatusPill({ status }: { status: string }) {
  const entry = ideaStatuses[status] ?? { label: status, tone: "neutral" as const, Icon: CircleDot };
  return <StatusPill tone={entry.tone} icon={<entry.Icon size={14} aria-hidden="true" />}>{entry.label}</StatusPill>;
}
