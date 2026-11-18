"use client";

import { AlertTriangle, ArrowRight, CalendarClock, Check, CheckCircle2, ClipboardCheck, Clock3, RotateCcw, Send, Users, X } from "lucide-react";
import { TenantLink as Link } from "@/components/app/tenant-link";
import { useTenantRouter as useRouter } from "@/lib/use-tenant-router";
import { useCallback, useEffect, useMemo, useState } from "react";
import { AdminShell } from "@/components/admin/admin-shell";
import { DismissibleNotice } from "@/components/ui/dismissible-notice";
import { IdeaStatusPill } from "@/components/ui/idea-status";
import { SectionCard, StatusPill, SummaryStrip } from "@/components/ui/workspace";
import { apiRequest } from "@/lib/api";
import { useSession } from "@/lib/use-session";
import styles from "./notifications.module.css";

type Idea = { id: string; reference: string; title: string; status: string; current_stage: string | null; correction_reason: string | null; updated_at: string };
type Approval = { idea_id: string; reference: string; title: string; stage_id: string; stage_name: string; submitted_by: string; submitted_at: string | null; due_at: string | null };
type JoinRequest = { id: string; idea_id: string; idea_reference: string; idea_title: string; requester_name: string; requester_email: string; message: string; created_at: string };
type Summary = { ideas: Idea[]; approval_items: Approval[]; join_requests?: JoinRequest[] };

export function NotificationsWorkspace() {
  const router = useRouter();
  const { session, loading } = useSession();
  const [summary, setSummary] = useState<Summary | null>(null);
  const [error, setError] = useState("");
  const [now, setNow] = useState(0);

  // Tiles elsewhere link to #assigned / #in-approval; those sections only exist once data loads.
  useEffect(() => {
    if (!summary || !window.location.hash) return;
    document.getElementById(window.location.hash.slice(1))?.scrollIntoView({ block: "start" });
  }, [summary]);

  const load = useCallback(async () => {
    try {
      const response = await apiRequest("/ideas/home-summary");
      if (response.status === 401) { router.replace("/sign-in"); return; }
      if (!response.ok) throw new Error();
      setSummary(await response.json() as Summary); setNow(Date.now());
    } catch { setError("Your inbox couldn't be loaded. Check your connection and try again."); }
  }, [router]);

  useEffect(() => { if (!session) return; const timer = window.setTimeout(() => void load(), 0); return () => window.clearTimeout(timer); }, [load, session]);

  const [answering, setAnswering] = useState("");
  const answer = async (request: JoinRequest, decision: "accept" | "decline") => {
    setAnswering(request.id); setError("");
    try {
      const response = await apiRequest(`/ideas/${request.idea_id}/join-requests/${request.id}/${decision}`, { method: "POST" });
      if (!response.ok) { const body = await response.json().catch(() => null) as { detail?: string } | null; throw new Error(body?.detail ?? "That didn't go through. Try again."); }
      window.dispatchEvent(new Event("transpire:inbox-changed"));
      await load();
    } catch (caught) { setError(caught instanceof Error ? caught.message : "That didn't go through. Try again."); }
    finally { setAnswering(""); }
  };

  const ownJourneys = useMemo(() => summary?.ideas.filter((idea) => ["submitted", "needs_correction"].includes(idea.status)) ?? [], [summary]);
  if (loading || !session || (!summary && !error)) return <main className={styles.loading}>Opening approval notifications</main>;
  const approvalItems = summary?.approval_items ?? [];
  const overdue = approvalItems.filter((item) => item.due_at && new Date(item.due_at).getTime() < now).length;
  const dueSoon = approvalItems.filter((item) => item.due_at && new Date(item.due_at).getTime() >= now && new Date(item.due_at).getTime() - now < 7 * 864e5).length;
  const corrections = ownJourneys.filter((idea) => idea.status === "needs_correction").length;

  return <AdminShell session={session} active="notifications" title="Inbox" description="Approval decisions and corrections waiting on you, plus your ideas in review.">
    {error ? <DismissibleNotice tone="error" onDismiss={() => setError("")}>{error}</DismissibleNotice> : null}
    {summary ? <><SummaryStrip label="Approval summary" items={[
      { icon: <ClipboardCheck size={18} />, value: approvalItems.length, label: "Assigned to you", href: "#assigned", note: approvalItems.length ? `${dueSoon} due in the next 7 days` : "Your queue is clear", tone: approvalItems.length ? "warning" : undefined },
      { icon: <AlertTriangle size={18} />, value: overdue, label: "Overdue", href: "#assigned", note: overdue ? "Past the service target" : "Nothing is late", tone: overdue ? "danger" : "success" },
      { icon: <Send size={18} />, value: ownJourneys.length, label: "Ideas under approval", href: "#in-approval", note: "Your submissions in review" },
      { icon: <RotateCcw size={18} />, value: corrections, label: "Needs correction", href: "#in-approval", note: corrections ? "Returned to you to edit" : "None waiting on you", tone: corrections ? "warning" : undefined },
    ]} />
    <SectionCard id="assigned" icon={<ClipboardCheck size={17} />} title="Assigned to you" meta={`${approvalItems.length} pending`} flush>
      {approvalItems.length ? <div className={styles.tableWrap}><table><thead><tr><th>Idea</th><th>Your stage</th><th>Submitted by</th><th>Due</th><th><span className={styles.srOnly}>Action</span></th></tr></thead><tbody>{approvalItems.map((item) => <tr key={item.stage_id}><td data-label="Idea"><span className={styles.reference}>{item.reference}</span><Link className={styles.ideaLink} href={`/ideas/${item.idea_id}?section=approval`}>{item.title}</Link></td><td data-label="Your stage">{item.stage_name}</td><td data-label="Submitted by"><span>{item.submitted_by}</span>{item.submitted_at ? <small>{formatDate(item.submitted_at)}</small> : null}</td><td data-label="Due"><DuePill due={item.due_at} now={now} /></td><td><Link className={styles.review} href={`/ideas/${item.idea_id}?section=approval`} aria-label={`Review ${item.reference}`}>Review<ArrowRight size={15} /></Link></td></tr>)}</tbody></table></div> : <Empty icon={<CheckCircle2 size={18} />} title="Nothing is waiting for your decision." />}
    </SectionCard>
    {summary.join_requests?.length ? <SectionCard id="join-requests" icon={<Users size={17} />} title="Requests to join your ideas" meta={`${summary.join_requests.length} waiting`} flush>
      <ul className={styles.joinList}>{summary.join_requests.map((request) => <li key={request.id}>
        <div><strong>{request.requester_name}</strong> wants to help with <Link className={styles.ideaLink} href={`/ideas/${request.idea_id}/summary`}>{request.idea_title}</Link><small>{request.idea_reference} · {request.requester_email}</small>{request.message ? <p>&ldquo;{request.message}&rdquo;</p> : null}</div>
        <div className={styles.joinActions}>
          <button type="button" className={styles.review} disabled={Boolean(answering)} onClick={() => void answer(request, "accept")}><Check size={15} aria-hidden="true" />Add to team</button>
          <button type="button" className={styles.rowLink} disabled={Boolean(answering)} onClick={() => void answer(request, "decline")}><X size={15} aria-hidden="true" />Decline</button>
        </div>
      </li>)}</ul>
    </SectionCard> : null}
    <SectionCard id="in-approval" icon={<Send size={17} />} title="Your ideas under approval" meta={`${ownJourneys.length} active`} flush>
      {ownJourneys.length ? <div className={styles.tableWrap}><table><thead><tr><th>Idea</th><th>Current position</th><th>Status</th><th>Updated</th><th><span className={styles.srOnly}>Action</span></th></tr></thead><tbody>{ownJourneys.map((idea) => <tr key={idea.id}><td data-label="Idea"><span className={styles.reference}>{idea.reference}</span><strong>{idea.title}</strong></td><td data-label="Current position"><span>{idea.status === "needs_correction" ? "Correction requested" : idea.current_stage || "In approval"}</span>{idea.correction_reason ? <small>{idea.correction_reason}</small> : null}</td><td data-label="Status"><IdeaStatusPill status={idea.status} /></td><td data-label="Updated"><time dateTime={idea.updated_at}>{formatDate(idea.updated_at)}</time></td><td><Link className={styles.rowLink} href={idea.status === "needs_correction" ? `/ideas/new/v2?resume=${idea.id}` : `/ideas/${idea.id}?section=approval`} aria-label={`${idea.status === "needs_correction" ? "Edit" : "View"} ${idea.reference}`}>{idea.status === "needs_correction" ? "Edit" : "View"}<ArrowRight size={15} /></Link></td></tr>)}</tbody></table></div> : <Empty icon={<Clock3 size={18} />} title="None of your ideas are in approval right now." />}
    </SectionCard></> : null}
  </AdminShell>;
}

function DuePill({ due, now }: { due: string | null; now: number }) {
  if (!due) return <StatusPill tone="info" icon={<Clock3 size={14} aria-hidden="true" />}>Review requested</StatusPill>;
  const remaining = new Date(due).getTime() - now;
  if (remaining < 0) return <StatusPill tone="danger" icon={<AlertTriangle size={14} aria-hidden="true" />}>Overdue · {formatDate(due)}</StatusPill>;
  return <StatusPill tone={remaining < 2 * 864e5 ? "warning" : "info"} icon={<CalendarClock size={14} aria-hidden="true" />}>Due {formatDate(due)}</StatusPill>;
}
function Empty({ icon, title }: { icon: React.ReactNode; title: string }) { return <div className={styles.empty}><span aria-hidden="true">{icon}</span><p>{title}</p></div>; }
function formatDate(value: string) { return new Intl.DateTimeFormat("en-IN", { day: "2-digit", month: "short", year: "numeric" }).format(new Date(value)); }
