"use client";

import { ArrowRight, CalendarClock, CheckCircle2, CircleDot, ClipboardCheck, FileClock, FilePenLine, Lightbulb, Plus, RefreshCw, RotateCcw, Trash2 } from "lucide-react";
import Image from "next/image";
import { TenantLink as Link } from "@/components/app/tenant-link";
import { useTenantRouter as useRouter } from "@/lib/use-tenant-router";
import { useCallback, useEffect, useMemo, useState } from "react";
import { AppMenu } from "@/components/app/app-menu";
import { DesktopNavigation } from "@/components/app/desktop-navigation";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { DismissibleNotice } from "@/components/ui/dismissible-notice";
import { apiRequest, type SessionIdentity } from "@/lib/api";
import styles from "./home.module.css";

type IdeaSummary = { id: string; reference: string; title: string; idea_type: string; status: string; submitted_at: string | null; updated_at: string; current_stage: string | null; charter_available: boolean; charter_status: string | null; can_edit_idea: boolean; can_delete_draft: boolean; correction_reason: string | null };
type ApprovalItem = { idea_id: string; reference: string; title: string; idea_type: string; stage_id: string; stage_name: string; submitted_by: string; submitted_at: string | null; due_at: string | null };
type HomeSummary = { ideas: IdeaSummary[]; approval_items: ApprovalItem[] };

const statusCopy: Record<string, { label: string; detail: string }> = {
  draft: { label: "Draft", detail: "Continue shaping this idea" },
  submitted: { label: "In approval", detail: "Waiting for the approval route" },
  needs_correction: { label: "Needs correction", detail: "Review the approver’s comments" },
  rejected: { label: "Rejected", detail: "Approval has ended" },
  approved: { label: "Approved", detail: "Project charter is ready" },
  charter_in_progress: { label: "Charter in progress", detail: "Complete the implementation plan" },
  charter_submitted: { label: "Ready to start", detail: "Execution baseline published" },
  withdrawn: { label: "Withdrawn", detail: "This idea is no longer active" },
};

export function HomeWorkspace() {
  const router = useRouter();
  const [session, setSession] = useState<SessionIdentity | null>(null);
  const [summary, setSummary] = useState<HomeSummary | null>(null);
  const [error, setError] = useState("");
  const [deleteTarget, setDeleteTarget] = useState<IdeaSummary | null>(null);
  const [deleting, setDeleting] = useState(false);

  const loadWorkspace = useCallback(async () => {
    setError("");
    try {
      const [sessionResponse, summaryResponse] = await Promise.all([apiRequest("/auth/session"), apiRequest("/ideas/home-summary")]);
      if (sessionResponse.status === 401 || summaryResponse.status === 401) { router.replace("/sign-in"); return; }
      if (!sessionResponse.ok || !summaryResponse.ok) throw new Error();
      setSession((await sessionResponse.json()) as SessionIdentity);
      setSummary((await summaryResponse.json()) as HomeSummary);
    } catch { setError("Your workspace could not be reached. Check the service connection, then retry."); }
  }, [router]);

  useEffect(() => { const timer = window.setTimeout(() => void loadWorkspace(), 0); return () => window.clearTimeout(timer); }, [loadWorkspace]);

  const activeIdeas = useMemo(() => summary?.ideas.filter((idea) => !["rejected", "withdrawn"].includes(idea.status)).length ?? 0, [summary]);
  const approvedIdeas = useMemo(() => summary?.ideas.filter((idea) => ["approved", "charter_in_progress", "charter_submitted"].includes(idea.status)).length ?? 0, [summary]);
  const editableIdeas = useMemo(() => summary?.ideas.filter((idea) => idea.can_edit_idea) ?? [], [summary]);
  const publishedIdeas = useMemo(() => summary?.ideas.filter((idea) => !idea.can_edit_idea) ?? [], [summary]);

  const deleteDraft = async () => {
    if (!deleteTarget) return;
    setDeleting(true);
    try {
      const response = await apiRequest(`/ideas/${deleteTarget.id}`, { method: "DELETE" });
      if (!response.ok) throw new Error();
      setSummary((current) => current ? { ...current, ideas: current.ideas.filter((idea) => idea.id !== deleteTarget.id) } : current);
      setDeleteTarget(null);
    } catch { setError("The draft could not be deleted. It may have already moved into review."); }
    finally { setDeleting(false); }
  };

  if (!session || !summary) return <main className={styles.loading} aria-label="Loading your TRANSPIRE workspace">{error ? <div className={styles.loadError} role="alert"><strong>We could not open your workspace.</strong><p>{error}</p><button type="button" onClick={() => void loadWorkspace()}><RefreshCw size={15} />Retry</button></div> : <><div className={styles.loadingMark} /><span>Preparing your improvement workspace</span></>}</main>;

  const firstName = session.user.display_name.split(" ")[0];
  return <div className={styles.page}>
    <header className={styles.header}><Link href="/home" aria-label="TRANSPIRE home"><Image src="/brand/transpire-logo.png" alt="TRANSPIRE" width={1400} height={371} priority /></Link><DesktopNavigation session={session} active="home" /><AppMenu session={session} active="home" /></header>
    <main className={styles.main}>
      {error ? <DismissibleNotice tone="error" onDismiss={() => setError("")}>{error}</DismissibleNotice> : null}
      <section className={styles.welcome} aria-labelledby="home-title"><div><p className={styles.eyebrow}>Your improvement workspace</p><h1 id="home-title">Good to have you here, {firstName}.</h1><p>Track the ideas you have contributed, respond to approval work assigned to you, and move approved ideas into implementation.</p></div><Link className={styles.primaryAction} href="/ideas/new/v2"><Plus size={17} />Submit an idea</Link></section>
      <section className={styles.summaryStrip} aria-label="Workspace summary"><div><Lightbulb size={18} /><span><strong>{summary.ideas.length}</strong>Ideas recorded</span></div><div><CircleDot size={18} /><span><strong>{activeIdeas}</strong>Active journeys</span></div><div><ClipboardCheck size={18} /><span><strong>{summary.approval_items.length}</strong>Awaiting your approval</span></div><div><CheckCircle2 size={18} /><span><strong>{approvedIdeas}</strong>Approved ideas</span></div></section>
      {editableIdeas.length ? <section className={styles.editableSection} aria-labelledby="work-in-progress-heading"><header className={styles.sectionHeader}><div><p>Continue your work</p><h2 id="work-in-progress-heading">Drafts and requested corrections</h2></div><span>{editableIdeas.length} requiring your attention</span></header><div className={styles.editableList}>{editableIdeas.map((idea) => <article key={idea.id} data-status={idea.status}><span className={styles.editableIcon}>{idea.status === "needs_correction" ? <RotateCcw size={18} /> : <FileClock size={18} />}</span><div><small>{idea.reference} · Updated {formatDate(idea.updated_at)}</small><h3>{idea.title}</h3><p>{idea.status === "needs_correction" ? idea.correction_reason || "An approver requested clarification before review can continue." : "This idea is saved securely in your TRANSPIRE workspace."}</p></div><div className={styles.editableActions}><Link href={`/ideas/new/v2?resume=${idea.id}`}>{idea.status === "needs_correction" ? "Edit and resubmit" : "Resume draft"}<ArrowRight size={15} /></Link>{idea.can_delete_draft ? <button type="button" onClick={() => setDeleteTarget(idea)}><Trash2 size={15} />Delete</button> : null}</div></article>)}</div></section> : null}
      <div className={styles.workspaceGrid}>
        <section className={styles.ideaSection} aria-labelledby="my-ideas-heading"><header className={styles.sectionHeader}><div><p>Contribution</p><h2 id="my-ideas-heading">My ideas</h2></div><Link href="/ideas">Open Idea Bank <ArrowRight size={15} /></Link></header>
          {publishedIdeas.length ? <div className={styles.ideaTable}><table><thead><tr><th>Idea</th><th>Type</th><th>Status and stage</th><th>Updated</th><th><span className={styles.srOnly}>Open</span></th></tr></thead><tbody>{publishedIdeas.map((idea) => { const status = statusCopy[idea.status] ?? { label: idea.status, detail: "Review current activity" }; return <tr key={idea.id}><td><span>{idea.reference}</span><strong>{idea.title}</strong></td><td>{idea.idea_type === "project" ? "Project" : "Kaizen"}</td><td><span className={styles.status} data-status={idea.status}>{status.label}</span><small>{idea.charter_available ? status.detail : idea.current_stage ?? status.detail}</small></td><td>{formatDate(idea.updated_at)}</td><td><Link href={`/ideas/${idea.id}`} aria-label={`Open ${idea.reference}`}><ArrowRight size={16} /></Link></td></tr>; })}</tbody></table></div> : <div className={styles.emptyState}><Lightbulb size={24} /><h3>{editableIdeas.length ? "No ideas are in review yet." : "Your first improvement starts with what you notice."}</h3><p>{editableIdeas.length ? "Resume a draft above and submit it when the case is ready." : "Capture the problem, the proposed change, and the outcome you believe is possible."}</p><Link href={editableIdeas.length ? `/ideas/new/v2?resume=${editableIdeas[0].id}` : "/ideas/new/v2"}>{editableIdeas.length ? "Resume your draft" : "Submit your first idea"}</Link></div>}
        </section>
        <aside className={styles.approvalSection} aria-labelledby="approvals-heading"><header className={styles.sectionHeader}><div><p>Assigned to you</p><h2 id="approvals-heading">Approval items</h2></div><span>{summary.approval_items.length} pending</span></header>
          {summary.approval_items.length ? <div className={styles.approvalList}>{summary.approval_items.map((item) => <Link href={`/ideas/${item.idea_id}?section=approval`} key={item.stage_id}><span className={styles.approvalIcon}><ClipboardCheck size={17} /></span><div><small>{item.reference} · {item.stage_name}</small><h3>{item.title}</h3><p>Submitted by {item.submitted_by}</p><span><CalendarClock size={13} />{item.due_at ? `Due ${formatDate(item.due_at)}` : "Review requested"}</span></div><ArrowRight size={16} /></Link>)}</div> : <div className={styles.approvalEmpty}><CheckCircle2 size={22} /><h3>You are up to date.</h3><p>New work appears here when a workflow stage is assigned to you.</p></div>}
          {summary.ideas.some((idea) => idea.charter_available && idea.charter_status !== "submitted") ? <div className={styles.charterReminder}><FilePenLine size={18} /><div><strong>An approved idea is ready.</strong><p>Open its detail page to complete the project charter.</p></div></div> : null}
        </aside>
      </div>
    </main>
    <ConfirmDialog open={Boolean(deleteTarget)} title="Delete this draft?" description={`${deleteTarget?.reference ?? "This draft"} will be permanently removed. Submitted ideas and correction requests cannot be deleted.`} confirmLabel="Delete draft" busyLabel="Deleting draft" onClose={() => setDeleteTarget(null)} onConfirm={() => void deleteDraft()} busy={deleting} />
  </div>;
}

function formatDate(value: string) { return new Intl.DateTimeFormat("en-IN", { day: "2-digit", month: "short", year: "numeric" }).format(new Date(value)); }
