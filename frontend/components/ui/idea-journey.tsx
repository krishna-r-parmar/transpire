import { Check, Circle, CircleDot, RotateCcw, X } from "lucide-react";
import type { ReactNode } from "react";
import styles from "./idea-journey.module.css";

type JourneyStage = { stage_name: string; status: string; round_number: number; stage_order: number; assignee_name?: string };
type JourneyState = "done" | "current" | "upcoming" | "returned" | "rejected";

const icons: Record<JourneyState, ReactNode> = {
  done: <Check size={14} />,
  current: <CircleDot size={14} />,
  upcoming: <Circle size={14} />,
  returned: <RotateCcw size={14} />,
  rejected: <X size={14} />,
};
const spoken: Record<JourneyState, string> = { done: "complete", current: "current step", upcoming: "not started", returned: "returned for correction", rejected: "rejected" };

// Approval stage statuses are the recorded decision (approve / reject / needs_correction) or the queue state.
function stageState(status: string): JourneyState {
  if (status === "approve") return "done";
  if (status === "pending") return "current";
  if (status === "reject") return "rejected";
  if (status === "needs_correction") return "returned";
  return "upcoming";
}

/** One line from submission to delivery, using the latest approval round. */
export function IdeaJourney({ stages, submitted, charterAvailable, charterSubmitted }: { stages: JourneyStage[]; submitted: boolean; charterAvailable: boolean; charterSubmitted: boolean }) {
  const latestRound = Math.max(0, ...stages.map((stage) => stage.round_number));
  const steps: Array<{ key: string; label: string; detail?: string; state: JourneyState }> = [
    { key: "submitted", label: "Submitted", state: submitted ? "done" : "current" },
    ...stages
      .filter((stage) => stage.round_number === latestRound)
      .sort((a, b) => a.stage_order - b.stage_order)
      .map((stage) => ({ key: `${stage.round_number}-${stage.stage_order}`, label: stage.stage_name, detail: stage.assignee_name, state: stageState(stage.status) })),
    { key: "charter", label: "Project charter", state: charterSubmitted ? "done" : charterAvailable ? "current" : "upcoming" },
    { key: "delivery", label: "Delivery", state: charterSubmitted ? "current" : "upcoming" },
  ];
  return <ol className={styles.journey} aria-label="Idea journey">
    {steps.map((step) => <li key={step.key} className={styles.step} data-state={step.state} aria-current={step.state === "current" ? "step" : undefined}>
      <span aria-hidden="true">{icons[step.state]}</span>
      <div><strong className={styles.label}>{step.label}</strong>{step.detail ? <small className={styles.detail}>{step.detail}</small> : null}<span className={styles.srOnly}>, {spoken[step.state]}</span></div>
    </li>)}
  </ol>;
}
