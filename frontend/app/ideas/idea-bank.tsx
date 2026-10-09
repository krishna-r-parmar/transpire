"use client";

import { ArrowRight, ChevronDown, Lightbulb, Plus, RefreshCw } from "lucide-react";
import { TenantLink as Link } from "@/components/app/tenant-link";
import { useTenantRouter as useRouter } from "@/lib/use-tenant-router";
import { useCallback, useEffect, useMemo, useState } from "react";
import { AdminShell } from "@/components/admin/admin-shell";
import { SearchField } from "@/components/ui/search-field";
import { SelectField } from "@/components/ui/select-field";
import { apiRequest } from "@/lib/api";
import { useSession } from "@/lib/use-session";
import styles from "./idea-bank.module.css";

type Idea = { id: string; reference: string; title: string; status: string; idea_type: string; category: string | null; submitted_at: string | null; contributor: string | null; subcategory: string | null; process_area: string | null; impacts: string[] | null; current_state: string | null; target_state: string | null; problem_statement: string | null; business_case: string | null; estimated_annual_saving: string | null; cost_avoidance: string | null; investment_required: string | null };

export function IdeaBank() {
  const router = useRouter();
  const { session, loading } = useSession();
  const [ideas, setIdeas] = useState<Idea[]>([]);
  const [query, setQuery] = useState("");
  const [type, setType] = useState("");
  const [category, setCategory] = useState("");
  const [expanded, setExpanded] = useState("");
  const [loadingIdeas, setLoadingIdeas] = useState(true);
  const [error, setError] = useState("");

  const loadIdeas = useCallback(async () => {
    setLoadingIdeas(true); setError("");
    try {
      const response = await apiRequest("/ideas");
      if (response.status === 401) return router.replace("/sign-in");
      if (!response.ok) throw new Error();
      setIdeas(await response.json() as Idea[]);
    } catch { setError("The Idea Bank could not be reached. Confirm the backend migration is current, then retry."); }
    finally { setLoadingIdeas(false); }
  }, [router]);

  useEffect(() => { if (session) { const timer = window.setTimeout(() => void loadIdeas(), 0); return () => window.clearTimeout(timer); } }, [loadIdeas, session]);

  const categories = useMemo(() => [...new Set(ideas.map((idea) => idea.category).filter((value): value is string => Boolean(value)))].sort(), [ideas]);
  const visible = useMemo(() => { const term = query.trim().toLocaleLowerCase(); return ideas.filter((idea) => (!type || idea.idea_type === type) && (!category || idea.category === category) && (!term || [idea.reference, idea.title, idea.category, idea.subcategory, idea.process_area, idea.contributor, ...(idea.impacts ?? [])].some((value) => value?.toLocaleLowerCase().includes(term)))); }, [category, ideas, query, type]);

  if (loading || !session) return <main className={styles.loading}>Opening the Idea Bank</main>;
  return <AdminShell session={session} active="ideas" eyebrow="Global Idea Bank" title="See what the organisation is improving." description="Shared detail follows the visibility policy set by your Tenant Administrator. Search the collective signal without exposing restricted information.">
    <div className={styles.toolbar}><SearchField id="idea-search" label="Search Idea Bank" value={query} onChange={setQuery} placeholder="Search reference, title, category, process, or impact" resultCount={visible.length} /><div><SelectField id="idea-type" name="idea_type" label="Idea type" value={type} onChange={setType} options={[{ value: "", label: "All idea types" }, { value: "kaizen", label: "Kaizen" }, { value: "project", label: "Project" }]} /><SelectField id="idea-category" name="category" label="Category" value={category} onChange={setCategory} options={[{ value: "", label: "All categories" }, ...categories.map((value) => ({ value, label: value }))]} /></div><Link href="/ideas/new/v2"><Plus size={16} />Submit an idea</Link></div>
    {error ? <div className={styles.error} role="alert"><span>{error}</span><button type="button" onClick={() => void loadIdeas()}><RefreshCw size={14} />Retry</button></div> : null}
    {loadingIdeas ? <div className={styles.skeleton} aria-label="Loading ideas"><span /><span /><span /></div> : null}
    {!loadingIdeas && visible.length ? <div className={styles.tableWrap}><table><thead><tr><th>Idea</th><th>Type</th><th>Classification</th><th>Impact</th><th>Submitted</th><th><span className={styles.srOnly}>Details</span></th></tr></thead><tbody>{visible.map((idea) => <IdeaRow key={idea.id} idea={idea} open={expanded === idea.id} onToggle={() => setExpanded((current) => current === idea.id ? "" : idea.id)} />)}</tbody></table></div> : null}
    {!loadingIdeas && !visible.length ? <section className={styles.empty}><Lightbulb size={24} /><h2>{ideas.length ? "No ideas match these filters." : "The first shared idea starts here."}</h2><p>{ideas.length ? "Clear a filter or search with a broader term." : "Capture an improvement opportunity and build the organisation’s idea memory."}</p><Link href="/ideas/new/v2">Submit an idea</Link></section> : null}
  </AdminShell>;
}

function IdeaRow({ idea, open, onToggle }: { idea: Idea; open: boolean; onToggle: () => void }) {
  const hasDetail = Boolean(idea.current_state || idea.problem_statement || idea.estimated_annual_saving);
  return <><tr><td><Link className={styles.ideaLink} href={`/ideas/${idea.id}`}>{idea.title}</Link><small>{idea.reference}{idea.contributor ? ` · ${idea.contributor}` : ""}</small></td><td><span className={styles.type}>{idea.idea_type}</span></td><td><span>{idea.category ?? "Unclassified"}</span><small>{idea.subcategory ?? idea.process_area ?? ""}</small></td><td><div className={styles.impacts}>{idea.impacts?.map((impact) => <span key={impact}>{impact.slice(0, 1).toUpperCase()}</span>) ?? <small>Restricted</small>}</div></td><td><time>{idea.submitted_at ? new Date(idea.submitted_at).toLocaleDateString() : "Pending"}</time></td><td><div className={styles.rowActions}><button className={styles.expand} type="button" onClick={onToggle} disabled={!hasDetail} aria-expanded={open} aria-label={`${open ? "Hide" : "Show"} preview for ${idea.reference}`}><ChevronDown size={16} /></button><Link href={`/ideas/${idea.id}`} aria-label={`Open full details for ${idea.reference}`}><ArrowRight size={16} /></Link></div></td></tr>{open ? <tr className={styles.detailRow}><td colSpan={6}><div className={styles.detail}><Detail label="Process area" value={idea.process_area} /><Detail label="Current state" value={idea.current_state} /><Detail label="Target state" value={idea.target_state} /><Detail label="Problem statement" value={idea.problem_statement} wide /><Detail label="Business case" value={idea.business_case} wide />{idea.estimated_annual_saving ? <Detail label="Estimated annual saving" value={formatCurrency(idea.estimated_annual_saving)} /> : null}{idea.cost_avoidance ? <Detail label="Cost avoidance" value={formatCurrency(idea.cost_avoidance)} /> : null}{idea.investment_required ? <Detail label="Investment required" value={formatCurrency(idea.investment_required)} /> : null}<Link className={styles.fullDetail} href={`/ideas/${idea.id}`}>Open protected idea record<ArrowRight size={15} /></Link></div></td></tr> : null}</>;
}

function Detail({ label, value, wide = false }: { label: string; value: string | null; wide?: boolean }) { if (!value) return null; return <div data-wide={wide}><span>{label}</span><p>{value}</p></div>; }
function formatCurrency(value: string) { return new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 0 }).format(Number(value)); }
