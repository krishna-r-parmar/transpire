"use client";

import { ArrowRight, Bell, CheckCircle2, Clock3, RotateCcw } from "lucide-react";
import { TenantLink as Link } from "@/components/app/tenant-link";
import { useTenantRouter as useRouter } from "@/lib/use-tenant-router";
import { useEffect, useMemo, useState } from "react";
import { AdminShell } from "@/components/admin/admin-shell";
import { DismissibleNotice } from "@/components/ui/dismissible-notice";
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

  useEffect(() => {
    if (!session) return;
    void apiRequest("/ideas/home-summary").then(async (response) => {
      if (response.status === 401) return router.replace("/sign-in");
      if (!response.ok) throw new Error();
      setSummary(await response.json() as Summary);
    }).catch(() => setError("Approval notifications could not be loaded. Try again after checking the service connection."));
  }, [router, session]);

  const ownJourneys = useMemo(() => summary?.ideas.filter((idea) => ["submitted", "needs_correction"].includes(idea.status)) ?? [], [summary]);
  if (loading || !session || !summary) return <main className={styles.loading}>Opening approval notifications</main>;

  return <AdminShell session={session} active="notifications" eyebrow="Approval notifications" title="Keep every review moving." description="Act on decisions assigned to you and follow ideas currently moving through approval.">
    {error ? <DismissibleNotice tone="error" onDismiss={() => setError("")}>{error}</DismissibleNotice> : null}
    <section className={styles.priority} aria-labelledby="assigned-heading">
      <header><div><p>Requires your attention</p><h2 id="assigned-heading">Assigned approval items</h2></div><span>{summary.approval_items.length} pending</span></header>
      {summary.approval_items.length ? <div className={styles.list}>{summary.approval_items.map((item) => <Link href={`/ideas/${item.idea_id}?section=approval`} key={item.stage_id}><span className={styles.icon}><Bell size={17} /></span><div><small>{item.reference} · {item.stage_name}</small><h3>{item.title}</h3><p>Submitted by {item.submitted_by}</p><em><Clock3 size={13} />{item.due_at ? `Due ${formatDate(item.due_at)}` : "Review requested"}</em></div><ArrowRight size={17} /></Link>)}</div> : <Empty icon={<CheckCircle2 size={22} />} title="Your approval queue is clear." body="New items appear here when a workflow stage is assigned to you." />}
    </section>
    <section className={styles.journeys} aria-labelledby="journeys-heading">
      <header><div><p>Your submissions</p><h2 id="journeys-heading">Ideas under approval</h2></div><span>{ownJourneys.length} active</span></header>
      {ownJourneys.length ? <div className={styles.journeyTable}><table><thead><tr><th>Idea</th><th>Current position</th><th>Updated</th><th><span className={styles.srOnly}>Action</span></th></tr></thead><tbody>{ownJourneys.map((idea) => <tr key={idea.id}><td><small>{idea.reference}</small><strong>{idea.title}</strong></td><td><span data-status={idea.status}>{idea.status === "needs_correction" ? <RotateCcw size={13} /> : <Clock3 size={13} />}{idea.status === "needs_correction" ? "Correction requested" : idea.current_stage || "In approval"}</span>{idea.correction_reason ? <small>{idea.correction_reason}</small> : null}</td><td>{formatDate(idea.updated_at)}</td><td><Link href={idea.status === "needs_correction" ? `/ideas/new/v2?resume=${idea.id}` : `/ideas/${idea.id}?section=approval`}>{idea.status === "needs_correction" ? "Edit" : "View"}<ArrowRight size={14} /></Link></td></tr>)}</tbody></table></div> : <Empty icon={<Clock3 size={22} />} title="No ideas are currently in approval." body="Submitted ideas appear here until a final approval, correction, or rejection is recorded." />}
    </section>
  </AdminShell>;
}

function Empty({ icon, title, body }: { icon: React.ReactNode; title: string; body: string }) { return <div className={styles.empty}>{icon}<h3>{title}</h3><p>{body}</p></div>; }
function formatDate(value: string) { return new Intl.DateTimeFormat("en-IN", { day: "2-digit", month: "short", year: "numeric" }).format(new Date(value)); }
