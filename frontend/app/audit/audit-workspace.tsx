"use client";

import { ArrowLeft, ArrowRight, CheckCircle2, FileClock, GitBranch, Lightbulb, RotateCcw, ShieldCheck, Trash2 } from "lucide-react";
import { TenantLink as Link } from "@/components/app/tenant-link";
import { useTenantRouter as useRouter } from "@/lib/use-tenant-router";
import { useCallback, useEffect, useState } from "react";
import { DismissibleNotice } from "@/components/ui/dismissible-notice";
import { SearchField } from "@/components/ui/search-field";
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
  if (!data && !error) return <section className={embedded ? styles.embeddedLoading : styles.loading}>Opening accountable history</section>;

  const pages = Math.max(1, Math.ceil((data?.total ?? 0) / (data?.page_size ?? 30)));
  return <>
    {error ? <DismissibleNotice tone="error" onDismiss={() => setError("")}>{error}</DismissibleNotice> : null}
    <section className={styles.log}>
      <header><SearchField id={embedded ? "profile-audit-search" : "audit-search"} label="Search audit history" value={query} onChange={(value) => { setQuery(value); setPage(1); }} placeholder="Search event, person, or reference" resultCount={data?.total ?? 0} /><div><ShieldCheck size={17} /><span>{data?.tenant_scope ? "Tenant-wide record" : "Account-specific record"}</span></div></header>
      {data?.items.length ? <ol>{data.items.map((event) => { const Icon = eventIcon(event.event_type); return <li key={event.id}><span className={styles.eventIcon}><Icon size={16} /></span><div><div className={styles.eventHeader}><h2>{event.summary}</h2><time>{formatDateTime(event.created_at)}</time></div><p>{event.actor_name || "System"}{event.actor_email ? ` · ${event.actor_email}` : ""}</p><div className={styles.metadata}><span>{eventLabel(event.event_type)}</span>{event.entity_reference ? <span>{event.entity_reference}</span> : null}{event.details.approval_round ? <span>Round {String(event.details.approval_round)}</span> : null}</div></div>{event.entity_type === "idea" && event.entity_id && event.event_type !== "idea.draft_deleted" ? <Link href={`/ideas/${event.entity_id}`} aria-label={`Open ${event.entity_reference ?? "idea"}`}><ArrowRight size={15} /></Link> : null}</li>; })}</ol> : <div className={styles.empty}><FileClock size={25} /><h2>{query ? "No events match this search." : "No business events have been recorded yet."}</h2><p>{query ? "Try a person, idea reference, or event type." : "New idea, approval, workflow, and charter activity will appear here."}</p></div>}
      {data ? <footer><span>Page {data.page} of {pages} · {data.total} events</span><div><button type="button" disabled={page <= 1} onClick={() => setPage((current) => current - 1)}><ArrowLeft size={14} />Previous</button><button type="button" disabled={page >= pages} onClick={() => setPage((current) => current + 1)}>Next<ArrowRight size={14} /></button></div></footer> : null}
    </section>
  </>;
}

function eventIcon(type: string) { if (type.includes("deleted")) return Trash2; if (type.includes("correction") || type.includes("resubmitted")) return RotateCcw; if (type.includes("approval") || type.includes("published")) return CheckCircle2; if (type.includes("workflow")) return GitBranch; return Lightbulb; }
function eventLabel(type: string) { return type.replaceAll(".", " · ").replaceAll("_", " "); }
function formatDateTime(value: string) { return new Intl.DateTimeFormat("en-IN", { dateStyle: "medium", timeStyle: "short" }).format(new Date(value)); }
