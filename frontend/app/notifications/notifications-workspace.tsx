"use client";

import { AlertTriangle, ArrowRight, CalendarClock, CheckCircle2, ClipboardCheck, Clock3, RotateCcw, Send } from "lucide-react";
import { TenantLink as Link } from "@/components/app/tenant-link";
import { useTenantRouter as useRouter } from "@/lib/use-tenant-router";
import { useEffect, useMemo, useState } from "react";
import { AdminShell } from "@/components/admin/admin-shell";
import { DismissibleNotice } from "@/components/ui/dismissible-notice";
import { IdeaStatusPill } from "@/components/ui/idea-status";
import { SectionCard, StatusPill, SummaryStrip } from "@/components/ui/workspace";
import { apiRequest } from "@/lib/api";
import { useSession } from "@/lib/use-session";
import styles from "./notifications.module.css";

type Idea = { id: string; reference: string; title: string; status: string; current_stage: string | null; correction_reason: string | null; updated_at: string };
type Approval = { idea_id: string; reference: string; title: string; stage_id: string; stage_name: string; submitted_by: string; submitted_at: string | null; due_at: string | null };
type Summary = { ideas: Idea[]; approval_items: Approval[] };

export function NotificationsWorkspace() {
  const router = useRouter();
  const { session, loading } = useSession();
  const [summary, setSummary] = useState<Summary | null>(null);
  const [error, setError] = useState("");
  const [now, setNow] = useState(0);

  useEffect(() => {
    if (!session) return;
    void apiRequest("/ideas/home-summary").then(async (response) => {
      if (response.status === 401) return router.replace("/sign-in");
      if (!response.ok) throw new Error();
      setSummary(await response.json() as Summary); setNow(Date.now());
    }).catch(() => setError("Approval notifications could not be loaded. Try again after checking the service connection."));
  }, [router, session]);

  const ownJourneys = useMemo(() => summary?.ideas.filter((idea) => ["submitted", "needs_correction"].includes(idea.status)) ?? [], [summary]);
  if (loading || !session || (!summary && !error)) return <main className={styles.loading}>Opening approval notifications</main>;
  const approvalItems = summary?.approval_items ?? [];
  const overdue = approvalItems.filter((item) => item.due_at && new Date(item.due_at).getTime() < now).length;
  const dueSoon = approvalItems.filter((item) => item.due_at && new Date(item.due_at).getTime() >= now && new Date(item.due_at).getTime() - now < 7 * 864e5).length;
  const corrections = ownJourneys.filter((idea) => idea.status === "needs_correction").length;

  return <AdminShell session={session} active="notifications" eyebrow="Approval notifications" title="Keep every review moving." description="Act on decisions assigned to you and follow ideas currently moving through approval.">
    {error ? <DismissibleNotice tone="error" onDismiss={() => setError("")}>{error}</DismissibleNotice> : null}
    {summary ? <><SummaryStrip label="Approval summary" items={[
      { icon: <ClipboardCheck size={18} />, value: approvalItems.length, label: "Assigned to you", note: approvalItems.length ? `${dueSoon} due in the next 7 days` : "Your queue is clear", tone: approvalItems.length ? "warning" : undefined },
      { icon: <AlertTriangle size={18} />, value: overdue, label: "Overdue", note: overdue ? "Past the service target" : "Nothing is late", tone: overdue ? "danger" : "success" },
      { icon: <Send size={18} />, value: ownJourneys.length, label: "Ideas under approval", note: "Your submissions in review" },
      { icon: <RotateCcw size={18} />, value: corrections, label: "Needs correction", note: corrections ? "Returned to you to edit" : "None waiting on you", tone: corrections ? "warning" : undefined },
    ]} />
    <SectionCard icon={<ClipboardCheck size={17} />} title="Assigned approval items" description="Requires your attention. Open an item to review the idea and record your decision." meta={`${approvalItems.length} pending`} flush>
      {approvalItems.length ? <div className={styles.tableWrap}><table><thead><tr><th>Idea</th><th>Your stage</th><th>Submitted by</th><th>Due</th><th><span className={styles.srOnly}>Action</span></th></tr></thead><tbody>{approvalItems.map((item) => <tr key={item.stage_id}><td data-label="Idea"><span className={styles.reference}>{item.reference}</span><Link className={styles.ideaLink} href={`/ideas/${item.idea_id}?section=approval`}>{item.title}</Link></td><td data-label="Your stage">{item.stage_name}</td><td data-label="Submitted by"><span>{item.submitted_by}</span>{item.submitted_at ? <small>{formatDate(item.submitted_at)}</small> : null}</td><td data-label="Due"><DuePill due={item.due_at} now={now} /></td><td><Link className={styles.review} href={`/ideas/${item.idea_id}?section=approval`} aria-label={`Review ${item.reference}`}>Review<ArrowRight size={15} /></Link></td></tr>)}</tbody></table></div> : <Empty icon={<CheckCircle2 size={24} />} title="Your approval queue is clear." body="New items appear here when a workflow stage is assigned to you." />}
    </SectionCard>
    <SectionCard icon={<Send size={17} />} title="Ideas under approval" description="Your submissions and their current position." meta={`${ownJourneys.length} active`} flush>
      {ownJourneys.length ? <div className={styles.tableWrap}><table><thead><tr><th>Idea</th><th>Current position</th><th>Status</th><th>Updated</th><th><span className={styles.srOnly}>Action</span></th></tr></thead><tbody>{ownJourneys.map((idea) => <tr key={idea.id}><td data-label="Idea"><span className={styles.reference}>{idea.reference}</span><strong>{idea.title}</strong></td><td data-label="Current position"><span>{idea.status === "needs_correction" ? "Correction requested" : idea.current_stage || "In approval"}</span>{idea.correction_reason ? <small>{idea.correction_reason}</small> : null}</td><td data-label="Status"><IdeaStatusPill status={idea.status} /></td><td data-label="Updated"><time dateTime={idea.updated_at}>{formatDate(idea.updated_at)}</time></td><td><Link className={styles.rowLink} href={idea.status === "needs_correction" ? `/ideas/new/v2?resume=${idea.id}` : `/ideas/${idea.id}?section=approval`} aria-label={`${idea.status === "needs_correction" ? "Edit" : "View"} ${idea.reference}`}>{idea.status === "needs_correction" ? "Edit" : "View"}<ArrowRight size={15} /></Link></td></tr>)}</tbody></table></div> : <Empty icon={<Clock3 size={24} />} title="No ideas are currently in approval." body="Submitted ideas appear here until a final approval, correction, or rejection is recorded." />}
    </SectionCard></> : null}
  </AdminShell>;
}

function DuePill({ due, now }: { due: string | null; now: number }) {
  if (!due) return <StatusPill tone="info" icon={<Clock3 size={14} aria-hidden="true" />}>Review requested</StatusPill>;
  const remaining = new Date(due).getTime() - now;
  if (remaining < 0) return <StatusPill tone="danger" icon={<AlertTriangle size={14} aria-hidden="true" />}>Overdue · {formatDate(due)}</StatusPill>;
  return <StatusPill tone={remaining < 2 * 864e5 ? "warning" : "info"} icon={<CalendarClock size={14} aria-hidden="true" />}>Due {formatDate(due)}</StatusPill>;
}
function Empty({ icon, title, body }: { icon: React.ReactNode; title: string; body: string }) { return <div className={styles.empty}><span aria-hidden="true">{icon}</span><h3>{title}</h3><p>{body}</p></div>; }
function formatDate(value: string) { return new Intl.DateTimeFormat("en-IN", { day: "2-digit", month: "short", year: "numeric" }).format(new Date(value)); }
