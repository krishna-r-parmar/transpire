"use client";

import { ArrowLeft, ArrowRight, Check, EyeOff, Hand, IndianRupee, LockKeyhole, Shield, Timer, Users, X } from "lucide-react";
import { useCallback, useEffect, useState, type ReactNode } from "react";
import { AdminShell } from "@/components/admin/admin-shell";
import { TenantLink as Link } from "@/components/app/tenant-link";
import { IdeaJourney } from "@/components/ui/idea-journey";
import { IdeaStatusPill } from "@/components/ui/idea-status";
import { initials } from "@/components/ui/people";
import { apiRequest } from "@/lib/api";
import { useSession } from "@/lib/use-session";
import { useTenantRouter as useRouter } from "@/lib/use-tenant-router";
import styles from "./summary.module.css";

type JoinState = "owner" | "member" | "pending" | "available" | "closed" | "not_allowed";
type JoinRequest = { id: string; requester_name: string; requester_email: string; message: string; created_at: string };
type JourneyStage = { stage_name: string; status: string; round_number: number; stage_order: number };
type IdeaSummary = {
  id: string; reference: string; title: string; status: string; idea_type: string; category: string | null; submitted_at: string | null;
  contributor: string | null; subcategory: string | null; process_area: string | null; impacts: string[] | null;
  current_state: string | null; baseline_uom: string | null; target_state: string | null; target_uom: string | null;
  problem_statement: string | null; business_case: string | null;
  estimated_annual_saving: string | null; cost_avoidance: string | null; investment_required: string | null;
  site: string | null; department: string | null; approval_journey: JourneyStage[];
  charter_available: boolean; charter_submitted: boolean; can_manage: boolean;
  team: string[]; join_state: JoinState; join_requests: JoinRequest[];
  shows_operational: boolean; shows_narrative: boolean; shows_contributor: boolean; shows_financials: boolean;
};

const impactLabels: Record<string, string> = { safety: "Safety", quality: "Quality", delivery: "Delivery / OTIF", cost: "Cost", productivity: "Productivity / People" };
const hiddenCopy = "Hidden by your workspace's sharing policy";

/** Read-only view of an idea for anyone browsing the Idea Bank. Fields the policy hides never reach the browser. */
export function IdeaSummary({ ideaId }: { ideaId: string }) {
  const router = useRouter();
  const { session, loading } = useSession();
  const [idea, setIdea] = useState<IdeaSummary | null>(null);
  const [failure, setFailure] = useState<"" | "private" | "missing" | "error">("");

  const load = useCallback(async () => {
    setFailure("");
    try {
      const response = await apiRequest(`/ideas/${ideaId}/summary`);
      if (response.status === 401) { router.replace("/sign-in"); return; }
      if (response.status === 403) { setFailure("private"); return; }
      if (response.status === 404) { setFailure("missing"); return; }
      if (!response.ok) throw new Error();
      setIdea(await response.json() as IdeaSummary);
    } catch { setFailure("error"); }
  }, [ideaId, router]);

  useEffect(() => { if (!session) return; const timer = window.setTimeout(() => void load(), 0); return () => window.clearTimeout(timer); }, [load, session]);

  if (loading || !session) return <main className={styles.loading}>Opening idea</main>;

  if (failure || !idea) {
    const copy = {
      private: { title: "This idea isn't shared in the Idea Bank", body: "Drafts and ideas being corrected stay with their owner and approvers until they're submitted." },
      missing: { title: "We couldn't find this idea", body: "It may have been withdrawn, or the link may be incomplete." },
      error: { title: "This idea couldn't be loaded", body: "Check your connection and try again." },
      "": null,
    }[failure];
    return <AdminShell session={session} active="ideas" title={copy?.title ?? "Loading idea"}>
      {copy ? <div className={styles.unavailable}><LockKeyhole size={22} aria-hidden="true" /><p>{copy.body}</p><div>{failure === "error" ? <button type="button" onClick={() => void load()}>Try again</button> : null}<Link href="/ideas"><ArrowLeft size={16} aria-hidden="true" />Back to Idea Bank</Link></div></div> : <div className={styles.skeleton} aria-label="Loading idea"><span /><span /><span /></div>}
    </AdminShell>;
  }

  const anyHidden = !idea.shows_operational || !idea.shows_narrative || !idea.shows_contributor || !idea.shows_financials;
  const saving = Number(idea.estimated_annual_saving || 0);
  const investment = Number(idea.investment_required || 0);

  return <AdminShell
    session={session}
    active="ideas"
    eyebrow={`${idea.reference} · ${idea.idea_type === "project" ? "Project" : "Kaizen"}`}
    title={idea.title}
    actions={<><IdeaStatusPill status={idea.status} />{idea.can_manage ? <Link className={styles.manage} href={`/ideas/${idea.id}`}>Manage idea<ArrowRight size={16} aria-hidden="true" /></Link> : null}</>}
  >
    <div className={styles.back}><Link href="/ideas"><ArrowLeft size={16} aria-hidden="true" />Back to Idea Bank</Link></div>

    <p className={styles.byline}>
      {idea.shows_contributor ? <span className={styles.person}><span aria-hidden="true">{initials(idea.contributor)}</span>{idea.contributor ?? "Unknown contributor"}</span> : <span className={styles.person}><span aria-hidden="true"><EyeOff size={13} /></span>Contributor hidden</span>}
      {idea.submitted_at ? <span>Submitted {formatDate(idea.submitted_at)}</span> : null}
      {idea.category ? <span>{idea.category}{idea.subcategory ? ` · ${idea.subcategory}` : ""}</span> : null}
    </p>

    <IdeaJourney stages={idea.approval_journey} submitted={Boolean(idea.submitted_at)} charterAvailable={idea.charter_available} charterSubmitted={idea.charter_submitted} />

    {idea.shows_financials ? (saving || investment || idea.cost_avoidance ? <section className={styles.values} aria-label="Value case">
      {saving ? <Value icon={<IndianRupee size={16} />} label="Annual saving" value={compactCurrency(saving)} note={idea.cost_avoidance ? `Plus ${compactCurrency(Number(idea.cost_avoidance))} cost avoidance` : "Estimated at submission"} /> : null}
      {investment ? <Value icon={<IndianRupee size={16} />} label="Investment" value={compactCurrency(investment)} /> : null}
      {saving && investment ? <Value icon={<Timer size={16} />} label="Payback" value={`${(investment / (saving / 12)).toFixed(1)} months`} /> : null}
    </section> : null) : <Hidden what="Financial estimates" />}

    <div className={styles.story}>
      <section aria-labelledby="summary-problem">
        <h2 id="summary-problem">The problem</h2>
        {idea.shows_narrative ? <p>{idea.problem_statement || "Not provided."}</p> : <Hidden what="The problem statement" inline />}
      </section>
      <section aria-labelledby="summary-idea">
        <h2 id="summary-idea">The idea</h2>
        {idea.shows_narrative ? <p>{idea.business_case || "Not provided."}</p> : <Hidden what="The proposed solution" inline />}
      </section>
    </div>

    <section className={styles.team} aria-labelledby="summary-team">
      <h2 id="summary-team">Team</h2>
      <ul>
        <li><span aria-hidden="true" data-owner="true">{initials(idea.contributor)}</span><div><strong>{idea.contributor ?? "Unknown"}</strong><small>Owner</small></div></li>
        {idea.team.filter((name) => name !== idea.contributor).map((name) => <li key={name}><span aria-hidden="true">{initials(name)}</span><div><strong>{name}</strong><small>Team member</small></div></li>)}
      </ul>
      <JoinPanel idea={idea} onChanged={load} />
      {idea.join_requests.length ? <JoinRequests ideaId={idea.id} requests={idea.join_requests} onChanged={load} /> : null}
    </section>

    <section className={styles.facts} aria-labelledby="summary-details">
      <h2 id="summary-details">Details</h2>
      <dl>
        <Fact label="Measure">{idea.shows_operational ? (idea.current_state || idea.target_state ? `${measure(idea.current_state, idea.baseline_uom) || "Not set"} → ${measure(idea.target_state, idea.target_uom) || "Not set"}` : "Not provided") : null}</Fact>
        <Fact label="Impact">{idea.shows_operational ? (idea.impacts?.length ? idea.impacts.map((impact) => impactLabels[impact] ?? impact).join(", ") : "Not provided") : null}</Fact>
        <Fact label="Category">{idea.category ?? "Unclassified"}</Fact>
        <Fact label="Subcategory">{idea.shows_operational ? idea.subcategory ?? "Not provided" : null}</Fact>
        <Fact label="Process area">{idea.shows_operational ? idea.process_area ?? "Not provided" : null}</Fact>
        <Fact label="Site">{idea.shows_operational ? idea.site ?? "Not provided" : null}</Fact>
        <Fact label="Department">{idea.shows_operational ? idea.department ?? "Not provided" : null}</Fact>
      </dl>
    </section>

    {anyHidden ? <p className={styles.policyNote}><Shield size={16} aria-hidden="true" />Your workspace shares a limited view of ideas in the Idea Bank. The idea&apos;s owner, its approvers, and Workspace Admins can see everything.</p> : null}
  </AdminShell>;
}

/** What this viewer can do about joining the team. Owners see requests instead. */
function JoinPanel({ idea, onChanged }: { idea: IdeaSummary; onChanged: () => Promise<void> }) {
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const send = async (method: "POST" | "DELETE") => {
    setBusy(true); setError("");
    try {
      const response = await apiRequest(method === "POST" ? `/ideas/${idea.id}/join-requests` : `/ideas/${idea.id}/join-requests/mine`, method === "POST" ? { method, body: JSON.stringify({ message }) } : { method });
      if (!response.ok) { const body = await response.json().catch(() => null) as { detail?: string } | null; throw new Error(body?.detail ?? "That didn't go through. Try again."); }
      setMessage(""); await onChanged();
    } catch (caught) { setError(caught instanceof Error ? caught.message : "That didn't go through. Try again."); }
    finally { setBusy(false); }
  };
  const owner = idea.contributor ?? "The owner";
  if (idea.join_state === "member") return <p className={styles.joinNote} data-tone="success"><Check size={16} aria-hidden="true" />You&apos;re on this team.</p>;
  if (idea.join_state === "closed") return <p className={styles.joinNote}><Hand size={16} aria-hidden="true" />You can ask to join once this idea is approved.</p>;
  if (idea.join_state === "pending") return <div className={styles.join}><p><strong>You&apos;ve asked to join.</strong> {owner} will accept or decline your request.</p><button type="button" className={styles.secondary} disabled={busy} onClick={() => void send("DELETE")}>{busy ? "Withdrawing" : "Withdraw request"}</button>{error ? <p role="alert" className={styles.joinError}>{error}</p> : null}</div>;
  if (idea.join_state !== "available") return null;
  return <form className={styles.join} onSubmit={(event) => { event.preventDefault(); void send("POST"); }}>
    <p><strong>Want to help deliver this?</strong> Ask {owner} to add you to the team.</p>
    <label>Why you&apos;d like to join <span>Optional</span><textarea value={message} maxLength={500} rows={2} onChange={(event) => setMessage(event.target.value)} placeholder="I run Line 3 and can help with trials." /></label>
    <button type="submit" disabled={busy}><Users size={16} aria-hidden="true" />{busy ? "Sending request" : "Ask to join"}</button>
    {error ? <p role="alert" className={styles.joinError}>{error}</p> : null}
  </form>;
}

/** Pending requests, shown to the idea's owner and Workspace Admins. */
export function JoinRequests({ ideaId, requests, onChanged }: { ideaId: string; requests: JoinRequest[]; onChanged: () => Promise<void> | void }) {
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const answer = async (requestId: string, decision: "accept" | "decline") => {
    setBusy(requestId); setError("");
    try {
      const response = await apiRequest(`/ideas/${ideaId}/join-requests/${requestId}/${decision}`, { method: "POST" });
      if (!response.ok) { const body = await response.json().catch(() => null) as { detail?: string } | null; throw new Error(body?.detail ?? "That didn't go through. Try again."); }
      window.dispatchEvent(new Event("transpire:inbox-changed"));
      await onChanged();
    } catch (caught) { setError(caught instanceof Error ? caught.message : "That didn't go through. Try again."); }
    finally { setBusy(""); }
  };
  return <div className={styles.requests}>
    <h3>{requests.length === 1 ? "1 person wants to join" : `${requests.length} people want to join`}</h3>
    {requests.map((request) => <article key={request.id}>
      <span aria-hidden="true">{initials(request.requester_name)}</span>
      <div><strong>{request.requester_name}</strong><small>{request.requester_email}</small>{request.message ? <p>&ldquo;{request.message}&rdquo;</p> : null}</div>
      <div className={styles.requestActions}>
        <button type="button" disabled={Boolean(busy)} onClick={() => void answer(request.id, "accept")}><Check size={16} aria-hidden="true" />Add to team</button>
        <button type="button" className={styles.secondary} disabled={Boolean(busy)} onClick={() => void answer(request.id, "decline")}><X size={16} aria-hidden="true" />Decline</button>
      </div>
    </article>)}
    {error ? <p role="alert" className={styles.joinError}>{error}</p> : null}
  </div>;
}

function Value({ icon, label, value, note }: { icon: ReactNode; label: string; value: string; note?: string }) {
  return <div className={styles.value}><span aria-hidden="true">{icon}</span><strong>{value}</strong><small>{label}</small>{note ? <em>{note}</em> : null}</div>;
}

function Hidden({ what, inline = false }: { what: string; inline?: boolean }) {
  return <p className={styles.hidden} data-inline={inline}><EyeOff size={15} aria-hidden="true" />{what}: {hiddenCopy.toLowerCase()}.</p>;
}

/** A row whose null child means the policy hid it. */
function Fact({ label, children }: { label: string; children: ReactNode }) {
  return <div><dt>{label}</dt><dd data-hidden={children === null}>{children ?? <><EyeOff size={14} aria-hidden="true" />Hidden</>}</dd></div>;
}

function measure(value: string | null, uom: string | null) { return [value, uom].filter(Boolean).join(" "); }
function formatDate(value: string) { return new Intl.DateTimeFormat("en-IN", { day: "numeric", month: "short", year: "numeric" }).format(new Date(value)); }
function compactCurrency(value: number) { return new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", notation: "compact", maximumFractionDigits: 1 }).format(value); }
