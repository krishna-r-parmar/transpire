"use client";

import { ArrowLeft, ArrowRight, CheckCircle2, FileClock, GitBranch, History, Lightbulb, ListFilter, RotateCcw, ShieldCheck, Trash2, XCircle } from "lucide-react";
import { TenantLink as Link } from "@/components/app/tenant-link";
import { useTenantRouter as useRouter } from "@/lib/use-tenant-router";
import { useCallback, useEffect, useState } from "react";
import { DismissibleNotice } from "@/components/ui/dismissible-notice";
import { SearchField } from "@/components/ui/search-field";
import { SectionCard, StatusPill } from "@/components/ui/workspace";
import { apiRequest, type SessionIdentity } from "@/lib/api";
import styles from "./audit.module.css";

type AuditEvent = { id: string; event_type: string; entity_type: string; entity_id: string | null; entity_reference: string | null; summary: string; details: Record<string, unknown>; actor_name: string | null; actor_email: string | null; subject_name: string | null; created_at: string };
type AuditPage = { items: AuditEvent[]; total: number; page: number; page_size: number; tenant_scope: boolean };

export function AuditLog({ session, embedded = false }: { session: SessionIdentity; embedded?: boolean }) {
  const router = useRouter();
  const [data, setData] = useState<AuditPage | null>(null);
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(1);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    if (!session) return;
    setError("");
    try {
      const params = new URLSearchParams({ page: String(page), page_size: "30" });
      if (query.trim()) params.set("query", query.trim());
      const response = await apiRequest(`/audit/events?${params}`);
      if (response.status === 401) return router.replace("/sign-in");
      if (!response.ok) throw new Error();
      setData(await response.json() as AuditPage);
    } catch { setError("The audit history could not be loaded. Check the service connection, then retry."); }
  }, [page, query, router, session]);

  useEffect(() => { const timer = window.setTimeout(() => void load(), 180); return () => window.clearTimeout(timer); }, [load]);
  if (!data && !error) return <section className={embedded ? styles.embeddedLoading : styles.loading} aria-busy="true">Opening accountable history</section>;

  const pages = Math.max(1, Math.ceil((data?.total ?? 0) / (data?.page_size ?? 30)));
  return <div className={embedded ? styles.embedded : styles.standalone}>
    {error ? <DismissibleNotice tone="error" onDismiss={() => setError("")}>{error}</DismissibleNotice> : null}
    <SectionCard icon={<ListFilter size={17} />} title="Filter the log" description="Search by event, person, or idea reference." meta={data ? <span className={styles.scope}><ShieldCheck size={16} aria-hidden="true" />{data.tenant_scope ? "Tenant-wide record" : "Account-specific record"}</span> : undefined}>
      <div className={styles.filters}><SearchField id={embedded ? "profile-audit-search" : "audit-search"} label="Search audit history" value={query} onChange={(value) => { setQuery(value); setPage(1); }} placeholder="Search event, person, or reference" resultCount={data?.total ?? 0} /></div>
    </SectionCard>
    <SectionCard className={styles.events} icon={<History size={17} />} title="Events" description="A permanent record of who changed what, and when." meta={data ? `${data.total} ${data.total === 1 ? "event" : "events"}` : undefined} flush>
      {data?.items.length ? <div className={styles.tableWrap}><table><thead><tr><th>When</th><th>Who</th><th>Event</th><th>What happened</th><th><span className={styles.srOnly}>Open</span></th></tr></thead><tbody>{data.items.map((event) => { const { Icon, tone } = eventStyle(event.event_type); return <tr key={event.id}>
        <td data-label="When"><time dateTime={event.created_at}>{formatDateTime(event.created_at)}</time></td>
        <td data-label="Who"><strong>{event.actor_name || "System"}</strong>{event.actor_email ? <small>{event.actor_email}</small> : null}</td>
        <td data-label="Event"><StatusPill tone={tone} icon={<Icon size={14} aria-hidden="true" />}>{eventLabel(event.event_type)}</StatusPill></td>
        <td data-label="What happened"><span className={styles.summary}>{event.summary}</span>{event.entity_reference || event.details.approval_round ? <div className={styles.metadata}>{event.entity_reference ? <span>{event.entity_reference}</span> : null}{event.details.approval_round ? <span>Round {String(event.details.approval_round)}</span> : null}</div> : null}</td>
        <td className={styles.open}>{event.entity_type === "idea" && event.entity_id && event.event_type !== "idea.draft_deleted" ? <Link href={`/ideas/${event.entity_id}`} aria-label={`Open ${event.entity_reference ?? "idea"}`}><ArrowRight size={16} /></Link> : null}</td>
      </tr>; })}</tbody></table></div> : <div className={styles.empty}><FileClock size={26} /><h3>{query ? "No events match this search." : "No business events have been recorded yet."}</h3><p>{query ? "Try a person, idea reference, or event type." : "New idea, approval, workflow, and charter activity will appear here."}</p></div>}
      {data ? <footer className={styles.pager}><span>Page {data.page} of {pages} · {data.total} events</span><div><button type="button" disabled={page <= 1} onClick={() => setPage((current) => current - 1)}><ArrowLeft size={15} />Previous</button><button type="button" disabled={page >= pages} onClick={() => setPage((current) => current + 1)}>Next<ArrowRight size={15} /></button></div></footer> : null}
    </SectionCard>
  </div>;
}

type EventTone = "neutral" | "info" | "success" | "warning" | "danger";
function eventStyle(type: string): { Icon: typeof Lightbulb; tone: EventTone } {
  if (type.includes("deleted")) return { Icon: Trash2, tone: "danger" };
  if (type.includes("reject")) return { Icon: XCircle, tone: "danger" };
  if (type.includes("correction") || type.includes("resubmitted")) return { Icon: RotateCcw, tone: "warning" };
  if (type.includes("approval") || type.includes("published")) return { Icon: CheckCircle2, tone: "success" };
  if (type.includes("workflow")) return { Icon: GitBranch, tone: "info" };
  return { Icon: Lightbulb, tone: "info" };
}
function eventLabel(type: string) { const label = type.replaceAll(".", " · ").replaceAll("_", " "); return label.charAt(0).toUpperCase() + label.slice(1); }
function formatDateTime(value: string) { return new Intl.DateTimeFormat("en-IN", { dateStyle: "medium", timeStyle: "short" }).format(new Date(value)); }
