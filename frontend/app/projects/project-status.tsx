import { AlertTriangle, Ban, CheckCircle2, CircleDashed, CircleDot, Clock3, Flag, OctagonAlert, PauseCircle, PlayCircle, SearchCheck, ShieldCheck, XCircle } from "lucide-react";
import { StatusPill } from "@/components/ui/workspace";

type Tone = "neutral" | "info" | "success" | "warning" | "danger";
type Entry = { label: string; tone: Tone; Icon: typeof CircleDot };

export const projectStatuses: Record<string, Entry> = {
  ready_to_start: { label: "Ready to start", tone: "neutral", Icon: Flag },
  in_progress: { label: "In progress", tone: "info", Icon: PlayCircle },
  on_hold: { label: "On hold", tone: "warning", Icon: PauseCircle },
  completion_review: { label: "Completion review", tone: "warning", Icon: SearchCheck },
  oe_verified: { label: "OE verified", tone: "info", Icon: ShieldCheck },
  finance_validation: { label: "Finance validation", tone: "warning", Icon: Clock3 },
  success: { label: "Success", tone: "success", Icon: CheckCircle2 },
  cancelled: { label: "Cancelled", tone: "danger", Icon: Ban },
  unsuccessful: { label: "Closed unsuccessful", tone: "danger", Icon: XCircle },
};

export const healthStates: Record<string, Entry> = {
  not_set: { label: "Not assessed", tone: "neutral", Icon: CircleDashed },
  on_track: { label: "On track", tone: "success", Icon: CheckCircle2 },
  at_risk: { label: "At risk", tone: "warning", Icon: AlertTriangle },
  blocked: { label: "Blocked", tone: "danger", Icon: OctagonAlert },
};

const deliveryStates: Record<string, Entry> = {
  not_started: { label: "Not started", tone: "neutral", Icon: CircleDashed },
  in_progress: { label: "In progress", tone: "info", Icon: PlayCircle },
  blocked: { label: "Blocked", tone: "danger", Icon: OctagonAlert },
  complete: { label: "Complete", tone: "success", Icon: CheckCircle2 },
};

function labelize(value: string) { return value.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase()); }

function Pill({ entry, fallback }: { entry: Entry | undefined; fallback: string }) {
  const { label, tone, Icon } = entry ?? { label: labelize(fallback), tone: "neutral" as const, Icon: CircleDot };
  return <StatusPill tone={tone} icon={<Icon size={14} aria-hidden="true" />}>{label}</StatusPill>;
}

export function ProjectStatusPill({ status }: { status: string }) { return <Pill entry={projectStatuses[status]} fallback={status} />; }
export function HealthPill({ health }: { health: string }) { return <Pill entry={healthStates[health]} fallback={health} />; }
export function DeliveryPill({ status }: { status: string }) { return <Pill entry={deliveryStates[status]} fallback={status} />; }
export function healthTone(health: string): Tone { return healthStates[health]?.tone ?? "neutral"; }
