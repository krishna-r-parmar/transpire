"use client";

import { ArrowLeft, ArrowRight, Check, CheckCircle2, ChevronDown, ChevronUp, Circle, CircleDot, Cloud, CloudOff, LockKeyhole, Plus, Search, Send, Trash2, X } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { AdminShell } from "@/components/admin/admin-shell";
import { TenantLink as Link } from "@/components/app/tenant-link";
import { DismissibleNotice } from "@/components/ui/dismissible-notice";
import { initials } from "@/components/ui/people";
import { SelectField } from "@/components/ui/select-field";
import { apiRequest } from "@/lib/api";
import { useSession } from "@/lib/use-session";
import { useTenantRouter as useRouter } from "@/lib/use-tenant-router";
import { ProjectStatusPill } from "../../project-status";
import styles from "./charter.module.css";

type Candidate = { membership_id: string; user_id: string; display_name: string; email: string };
type CatalogItem = { id: string; name: string; site_ids: string[]; applies_to_all_sites: boolean };
type Catalog = { sites: CatalogItem[]; departments: CatalogItem[] };
type Charter = {
  sponsor: string; leader: string; sponsor_user_id: string | null; leader_user_id: string | null;
  department_id: string | null; site_id: string | null; start_date: string | null; target_completion_date: string | null;
  team_members: string[]; team_membership_ids: string[]; in_scope: string; out_of_scope: string; objective: string;
  benefit_type: string; kpi_name: string; budget_approved: string | null; impact_areas: string[]; belt_level: string | null;
  milestone_plan: PlanItem[];
  status: "draft" | "submitted"; submitted_at: string | null;
};
type IdeaContext = {
  id: string; reference: string; title: string; idea_type: string; project_subtype: string | null; submitter_name: string; submitter_user_id: string;
  site_id: string | null; site: string | null; department_id: string | null; department: string | null; category: string | null; subcategory: string | null;
  impacts: string[]; current_state: string; baseline_uom: string; target_state: string; target_uom: string; target_completion_date: string | null;
  estimated_annual_saving: string | null; cost_avoidance: string | null; investment_required: string | null; kpi_hint: string; suggested_benefit_type: string;
};
type Workspace = { project_id: string; project_reference: string; project_status: string; can_edit: boolean; charter: Charter; idea: IdeaContext };
type Step = 1 | 2 | 3 | 4 | 5;
type PlanItem = { id: string; title: string; owner_user_id: string | null; owner_name: string; due_date: string | null; weight: string; benefits_start: boolean };
type SaveState = "saved" | "saving" | "unsaved" | "error";

const steps: Array<{ label: string; hint: string }> = [
  { label: "People", hint: "Who leads and helps" },
  { label: "Scope and goal", hint: "What will change" },
  { label: "Plan", hint: "Milestones" },
  { label: "Measure", hint: "From the idea" },
  { label: "Review", hint: "Submit and lock" },
];
const impacts = [
  { value: "safety", label: "Safety" }, { value: "quality", label: "Quality" }, { value: "delivery", label: "Delivery / OTIF" },
  { value: "cost", label: "Cost" }, { value: "productivity", label: "Productivity / People" },
];
const benefitTypes = [
  { value: "cost_saving", label: "Cost saving" }, { value: "cost_avoidance", label: "Cost avoidance" }, { value: "both", label: "Saving and avoidance" },
  { value: "revenue", label: "Revenue" }, { value: "kpi_only", label: "KPI only" },
];

/** The project charter: four guided steps, pre-filled from the approved idea, saved as you go. */
export function CharterEditor({ projectId }: { projectId: string }) {
  const router = useRouter();
  const { session, loading } = useSession();
  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [draft, setDraft] = useState<Charter | null>(null);
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [catalog, setCatalog] = useState<Catalog>({ sites: [], departments: [] });
  const [step, setStep] = useState<Step>(1);
  const [saveState, setSaveState] = useState<SaveState>("saved");
  const [failure, setFailure] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const dirty = useRef(false);

  const load = useCallback(async () => {
    try {
      const [charterResponse, peopleResponse, catalogResponse] = await Promise.all([
        apiRequest(`/projects/${projectId}/charter`), apiRequest("/projects/team-candidates"), apiRequest("/ideas/submission-catalog"),
      ]);
      if (charterResponse.status === 401) { router.replace("/sign-in"); return; }
      if (!charterResponse.ok) { setFailure(charterResponse.status === 404 ? "This project could not be found." : "The charter couldn't be loaded. Try again."); return; }
      const next = await charterResponse.json() as Workspace;
      if (peopleResponse.ok) setCandidates(await peopleResponse.json() as Candidate[]);
      if (catalogResponse.ok) setCatalog(await catalogResponse.json() as Catalog);
      const { charter, changed } = withIdeaDefaults(next.charter, next.idea);
      setWorkspace(next);
      setDraft(charter);
      // Persist the suggestions straight away so the draft matches what the page shows.
      if (changed && next.can_edit) { dirty.current = true; setSaveState("unsaved"); }
    } catch { setFailure("The charter couldn't be loaded. Check your connection and try again."); }
  }, [projectId, router]);

  useEffect(() => { if (!session) return; const timer = window.setTimeout(() => void load(), 0); return () => window.clearTimeout(timer); }, [load, session]);

  const persist = useCallback(async (charter: Charter, ideaId: string) => {
    setSaveState("saving");
    try {
      const response = await apiRequest(`/ideas/${ideaId}/charter?autosave=true`, { method: "PUT", body: JSON.stringify(payloadFor(charter)) });
      if (!response.ok) { const body = await response.json().catch(() => null) as { detail?: unknown } | null; throw new Error(typeof body?.detail === "string" ? body.detail : "Couldn't save your latest changes."); }
      if (!dirty.current) setSaveState("saved");
    } catch (caught) { setSaveState("error"); setError(caught instanceof Error ? caught.message : "Couldn't save your latest changes."); }
  }, []);

  // Autosave a moment after the last change.
  useEffect(() => {
    if (!draft || !workspace?.can_edit || saveState !== "unsaved") return;
    const timer = window.setTimeout(() => { dirty.current = false; void persist(draft, workspace.idea.id); }, 1200);
    return () => window.clearTimeout(timer);
  }, [draft, persist, saveState, workspace]);

  const update = (patch: Partial<Charter>) => { if (!workspace?.can_edit) return; dirty.current = true; setDraft((current) => current ? { ...current, ...patch } : current); setSaveState("unsaved"); };

  const siteId = draft?.site_id ?? null;
  const departments = useMemo(() => catalog.departments.filter((item) => !siteId || item.applies_to_all_sites || item.site_ids.includes(siteId)), [catalog.departments, siteId]);

  if (loading || !session) return <main className={styles.loading}>Opening charter</main>;
  if (failure || !workspace || !draft) {
    return <AdminShell session={session} active="projects" title={failure ? "Charter unavailable" : "Loading charter"}>
      {failure ? <div className={styles.unavailable}><p>{failure}</p><Link href="/projects"><ArrowLeft size={16} aria-hidden="true" />Back to Projects</Link></div> : <div className={styles.skeleton} aria-label="Loading charter"><span /><span /><span /></div>}
    </AdminShell>;
  }

  const { idea } = workspace;
  const isKaizen = idea.idea_type === "kaizen";
  const isLss = Boolean(idea.project_subtype?.includes("Lean Six Sigma"));
  const submitted = draft.status === "submitted";
  const editable = workspace.can_edit && !submitted;
  const missing = missingFields(draft, isKaizen, catalog.sites.length > 0, catalog.departments.length > 0);
  const sponsorLabel = isKaizen ? "OE Lead / Facilitator" : "Sponsor";
  const leaderLabel = isKaizen ? "Team leader" : "Project leader";
  const planOwners = candidates.filter((person) => person.user_id === draft.leader_user_id || person.user_id === idea.submitter_user_id || draft.team_membership_ids.includes(person.membership_id));
  const nameOf = (userId: string | null, fallback: string) => candidates.find((person) => person.user_id === userId)?.display_name ?? fallback;

  const submit = async () => {
    setSubmitting(true); setError("");
    try {
      if (dirty.current || saveState !== "saved") { dirty.current = false; await persist(draft, idea.id); }
      const response = await apiRequest(`/ideas/${idea.id}/charter/submit`, { method: "POST", body: JSON.stringify(payloadFor(draft)) });
      const body = await response.json().catch(() => null) as { detail?: unknown; team_invitations_queued?: number } | null;
      if (!response.ok) throw new Error(typeof body?.detail === "string" ? body.detail : "The charter couldn't be submitted.");
      setNotice(`Charter submitted and locked as baseline v1.${body?.team_invitations_queued ? ` ${body.team_invitations_queued} team ${body.team_invitations_queued === 1 ? "invitation" : "invitations"} sent.` : ""}`);
      await load();
    } catch (caught) { setError(caught instanceof Error ? caught.message : "The charter couldn't be submitted."); }
    finally { setSubmitting(false); }
  };

  return <AdminShell
    session={session}
    active="projects"
    eyebrow={`${workspace.project_reference} · ${isKaizen ? "Kaizen" : "Project"} charter`}
    title={idea.title}
    actions={<ProjectStatusPill status={workspace.project_status} />}
  >
    <div className={styles.back}><Link href="/projects"><ArrowLeft size={16} aria-hidden="true" />Back to Projects</Link><Link href={`/ideas/${idea.id}/summary`}>View the approved idea</Link></div>
    <div className={styles.notices}>
      {notice ? <DismissibleNotice onDismiss={() => setNotice("")}>{notice}</DismissibleNotice> : null}
      {error ? <DismissibleNotice tone="error" onDismiss={() => setError("")}>{error}</DismissibleNotice> : null}
    </div>

    {submitted
      ? <section className={styles.banner} data-tone="done"><div><strong>Charter submitted and locked</strong><p>It&apos;s baseline v1 for delivery. Plan milestones and track progress in the project.</p></div><Link href={`/projects/${workspace.project_id}`}>Open project<ArrowRight size={16} aria-hidden="true" /></Link></section>
      : editable
        ? <section className={styles.banner}><div><strong>Next step: complete the charter</strong><p>Most of it comes from the approved idea. Add the people and scope, then submit.</p></div></section>
        : <section className={styles.banner} data-tone="info"><div><strong>Charter in progress</strong><p>{idea.submitter_name} is completing this charter. You can read it as it takes shape.</p></div></section>}

    <ol className={styles.journey} aria-label="Charter journey">
      <JourneyStep state="done" label="Idea approved" />
      <JourneyStep state={submitted ? "done" : "current"} label="Charter" />
      <JourneyStep state={submitted ? "done" : "upcoming"} label="Locked v1" icon={<LockKeyhole size={13} />} />
      <JourneyStep state={submitted ? "current" : "upcoming"} label="Delivery" />
    </ol>

    {editable ? <nav aria-label="Charter steps"><ol className={styles.steps}>
      {steps.map((item, index) => {
        const number = (index + 1) as Step;
        return <li key={item.label} data-active={step === number} data-complete={step > number}>
          <button type="button" onClick={() => setStep(number)} aria-current={step === number ? "step" : undefined}>
            <span aria-hidden="true">{step > number ? <Check size={13} /> : number}</span><strong>{item.label}</strong><small>{item.hint}</small>
          </button>
        </li>;
      })}
    </ol></nav> : null}

    {editable && step === 1 ? <Section title="Who will deliver this?" intro={`The ${leaderLabel.toLowerCase()} starts as the person who submitted the idea. You can hand it to someone else.`}>
      <div className={styles.card}>
        <PersonField label={leaderLabel} candidates={candidates} selectedId={draft.leader_user_id} fallbackName={draft.leader} onChange={(person) => update({ leader_user_id: person?.user_id ?? null, leader: person?.display_name ?? "" })} />
        <PersonField label={sponsorLabel} hint={isKaizen ? "Guides the method and signs off the result." : "Senior owner who removes blockers and accepts the outcome."} candidates={candidates} selectedId={draft.sponsor_user_id} fallbackName={draft.sponsor} onChange={(person) => update({ sponsor_user_id: person?.user_id ?? null, sponsor: person?.display_name ?? "" })} />
        <TeamField candidates={candidates} selected={draft.team_membership_ids} extraNames={draft.team_members.filter((name) => !candidates.some((person) => draft.team_membership_ids.includes(person.membership_id) && person.display_name === name))} onChange={(ids, names) => update({ team_membership_ids: ids, team_members: names })} />
      </div>
    </Section> : null}

    {editable && step === 2 ? <Section title={isKaizen ? "When will it happen?" : "What will change, and by when?"} intro={isKaizen ? "Set the dates for this Kaizen." : "Be specific about what this project covers and what success looks like."}>
      <div className={styles.card}>
        <div className={styles.grid}>
          <DateField label="Start date" value={draft.start_date} onChange={(value) => update({ start_date: value })} />
          <DateField label={isKaizen ? "Completion date" : "Target completion"} value={draft.target_completion_date} onChange={(value) => update({ target_completion_date: value })} fromIdea={idea.target_completion_date === draft.target_completion_date && Boolean(idea.target_completion_date)} />
        </div>
        {!isKaizen ? <>
          <TextField label="In scope" hint="Processes, lines, or areas this project changes." value={draft.in_scope} onChange={(value) => update({ in_scope: value })} placeholder="Feed water line from DM plant to Boiler 2, including the new pre-heater." />
          <TextField label="Out of scope" hint="What is explicitly not part of this project." value={draft.out_of_scope} onChange={(value) => update({ out_of_scope: value })} placeholder="Boiler 1 and steam distribution." />
          <TextField label="Objective" hint="Specific, measurable, achievable, relevant, and time-bound." value={draft.objective} onChange={(value) => update({ objective: value })} placeholder={`Reduce ${idea.kpi_hint || "fuel use"} from ${measure(idea.current_state, idea.baseline_uom) || "the baseline"} to ${measure(idea.target_state, idea.target_uom) || "the target"} by ${idea.target_completion_date ? formatDate(idea.target_completion_date) : "the target date"}.`} />
        </> : null}
        {isLss ? <div className={styles.field}><span className={styles.label}>Belt level</span><div className={styles.choiceRow}>{["Yellow Belt", "Green Belt", "Black Belt", "Master Black Belt"].map((belt) => <button key={belt} type="button" aria-pressed={draft.belt_level === belt} onClick={() => update({ belt_level: belt })}>{belt}</button>)}</div></div> : null}
      </div>
    </Section> : null}

    {editable && step === 3 ? <Section title="How will it be delivered?" intro="List the main milestones. Tasks, progress and evidence are added in delivery.">
      <PlanEditor
        plan={draft.milestone_plan}
        owners={planOwners}
        kind={isLss ? "lss" : isKaizen ? "kaizen" : "project"}
        moneyBenefits={draft.benefit_type !== "kpi_only"}
        start={draft.start_date}
        target={draft.target_completion_date}
        onChange={(milestone_plan) => update({ milestone_plan })}
      />
    </Section> : null}

    {editable && step === 4 ? <Section title="How will success be measured?" intro="These come from the approved idea. Change them only if delivery differs, and reviewers will see what changed.">
      <FromIdea idea={idea} />
      <div className={styles.card}>
        {catalog.sites.length || catalog.departments.length ? <div className={styles.grid}>
          <div className={styles.field}>
            <SelectField id="charter-site" name="site_id" label="Site" value={draft.site_id ?? ""} onChange={(value) => update({ site_id: value || null, department_id: departments.some((item) => item.id === draft.department_id) ? draft.department_id : null })} options={[{ value: "", label: "Select a site" }, ...catalog.sites.map((item) => ({ value: item.id, label: item.name }))]} />
            <Differs show={draft.site_id !== idea.site_id} idea={idea.site} />
          </div>
          <div className={styles.field}>
            <SelectField id="charter-department" name="department_id" label="Department" value={draft.department_id ?? ""} onChange={(value) => update({ department_id: value || null })} options={[{ value: "", label: "Select a department" }, ...departments.map((item) => ({ value: item.id, label: item.name }))]} />
            <Differs show={draft.department_id !== idea.department_id} idea={idea.department} />
          </div>
        </div> : null}
        <TextField label="KPI or metric" hint={idea.kpi_hint ? `Suggested for ${idea.subcategory ?? "this subcategory"}: ${idea.kpi_hint}` : "The measure that shows this worked."} value={draft.kpi_name} onChange={(value) => update({ kpi_name: value })} single placeholder="Fuel use (litres/day)" />
        <div className={styles.field}><span className={styles.label}>Benefit type</span><div className={styles.choiceRow}>{benefitTypes.map((type) => <button key={type.value} type="button" aria-pressed={draft.benefit_type === type.value} onClick={() => update({ benefit_type: type.value })}>{type.label}</button>)}</div><Differs show={draft.benefit_type !== idea.suggested_benefit_type} idea={benefitTypes.find((type) => type.value === idea.suggested_benefit_type)?.label ?? null} /></div>
        <div className={styles.field}><span className={styles.label}>SQDCP impact</span><div className={styles.choiceRow}>{impacts.map((impact) => <button key={impact.value} type="button" aria-pressed={draft.impact_areas.includes(impact.value)} onClick={() => update({ impact_areas: draft.impact_areas.includes(impact.value) ? draft.impact_areas.filter((value) => value !== impact.value) : [...draft.impact_areas, impact.value] })}>{impact.label}</button>)}</div><Differs show={!sameSet(draft.impact_areas, idea.impacts)} idea={idea.impacts.map((value) => impacts.find((impact) => impact.value === value)?.label ?? value).join(", ") || null} /></div>
        <label className={styles.field}><span className={styles.label}>Budget approved (₹)</span><small className={styles.hint}>Investment confirmed for delivery. The idea estimated {idea.investment_required ? rupees(idea.investment_required) : "no investment"}.</small><input type="number" min="0" step="1000" inputMode="decimal" value={draft.budget_approved ?? ""} onChange={(event) => update({ budget_approved: event.target.value || null })} /></label>
        <p className={styles.deliveryNote}>Month-on-month benefits aren&apos;t estimated here. They&apos;re tracked in delivery, once the milestone that starts realising the benefit is complete.</p>
      </div>
    </Section> : null}

    {(!editable || step === 5) ? <Section title={editable ? "Review and submit" : "Charter"} intro={editable ? "Submitting locks the charter as baseline v1. After that, changes need approval from the Head of Department." : undefined}>
      {editable && missing.length ? <div className={styles.missing} role="status"><strong>Complete these before submitting</strong><ul>{missing.map((item) => <li key={item.label}><button type="button" onClick={() => setStep(item.step)}>{item.label}</button></li>)}</ul></div> : null}
      <div className={styles.review}>
        <ReviewGroup title="People" onEdit={editable ? () => setStep(1) : undefined}>
          <Fact label={leaderLabel}>{nameOf(draft.leader_user_id, draft.leader) || "Not chosen"}</Fact>
          <Fact label={sponsorLabel}>{nameOf(draft.sponsor_user_id, draft.sponsor) || "Not chosen"}</Fact>
          <Fact label="Team" wide>{draft.team_members.length ? draft.team_members.join(", ") : "No team members yet"}</Fact>
        </ReviewGroup>
        <ReviewGroup title={isKaizen ? "Dates" : "Scope and goal"} onEdit={editable ? () => setStep(2) : undefined}>
          <Fact label="Start date">{draft.start_date ? formatDate(draft.start_date) : "Not set"}</Fact>
          <Fact label={isKaizen ? "Completion date" : "Target completion"}>{draft.target_completion_date ? formatDate(draft.target_completion_date) : "Not set"}</Fact>
          {!isKaizen ? <><Fact label="In scope" wide>{draft.in_scope || "Not provided"}</Fact><Fact label="Out of scope" wide>{draft.out_of_scope || "Not provided"}</Fact><Fact label="Objective" wide>{draft.objective || "Not provided"}</Fact></> : null}
          {isLss ? <Fact label="Belt level">{draft.belt_level || "Not chosen"}</Fact> : null}
        </ReviewGroup>
        <ReviewGroup title="Plan" onEdit={editable ? () => setStep(3) : undefined}>
          <div data-wide="true"><dt>Milestones</dt><dd>{draft.milestone_plan.length ? <ol className={styles.planReview}>{draft.milestone_plan.map((item) => <li key={item.id}><strong>{item.title || "Untitled milestone"}</strong><span>{[item.owner_name || null, item.due_date ? `due ${formatDate(item.due_date)}` : null, `${Number(item.weight || 0)}%`].filter(Boolean).join(" · ")}</span>{item.benefits_start ? <em>Benefits start</em> : null}</li>)}</ol> : "No milestones yet"}</dd></div>
        </ReviewGroup>
        <ReviewGroup title="Measure" onEdit={editable ? () => setStep(4) : undefined}>
          <Fact label="Site">{catalog.sites.find((item) => item.id === draft.site_id)?.name ?? (draft.site_id === idea.site_id ? idea.site : null) ?? "Not set"}</Fact>
          <Fact label="Department">{catalog.departments.find((item) => item.id === draft.department_id)?.name ?? (draft.department_id === idea.department_id ? idea.department : null) ?? "Not set"}</Fact>
          <Fact label="KPI">{draft.kpi_name || "Not set"}</Fact>
          <Fact label="Baseline → target">{`${measure(idea.current_state, idea.baseline_uom) || "Not set"} → ${measure(idea.target_state, idea.target_uom) || "Not set"}`}</Fact>
          <Fact label="Benefit type">{benefitTypes.find((type) => type.value === draft.benefit_type)?.label ?? draft.benefit_type}</Fact>
          <Fact label="SQDCP">{draft.impact_areas.map((value) => impacts.find((impact) => impact.value === value)?.label ?? value).join(", ") || "None"}</Fact>
          <Fact label="Budget approved">{draft.budget_approved ? rupees(draft.budget_approved) : "Not set"}</Fact>
          <Fact label="Target benefit">{idea.estimated_annual_saving ? `${rupees(idea.estimated_annual_saving)} a year` : "KPI improvement only"}</Fact>
        </ReviewGroup>
      </div>
    </Section> : null}

    {editable ? <div className={styles.actionBar}>
      <SaveIndicator state={saveState} />
      <div>
        {step > 1 ? <button type="button" className={styles.secondary} onClick={() => setStep((step - 1) as Step)}><ArrowLeft size={16} aria-hidden="true" />Back</button> : null}
        {step < 5
          ? <button type="button" className={styles.primary} onClick={() => setStep((step + 1) as Step)}>Continue to {steps[step].label.toLowerCase()}<ArrowRight size={16} aria-hidden="true" /></button>
          : <button type="button" className={styles.primary} disabled={submitting || missing.length > 0} onClick={() => void submit()}><Send size={16} aria-hidden="true" />{submitting ? "Submitting" : "Submit and lock charter"}</button>}
      </div>
    </div> : null}
  </AdminShell>;
}

/* ---------- Pieces ---------- */

function Section({ title, intro, children }: { title: string; intro?: string; children: ReactNode }) {
  return <section className={styles.section}><h2>{title}</h2>{intro ? <p className={styles.intro}>{intro}</p> : null}{children}</section>;
}

function JourneyStep({ state, label, icon }: { state: "done" | "current" | "upcoming"; label: string; icon?: ReactNode }) {
  return <li data-state={state} aria-current={state === "current" ? "step" : undefined}><span aria-hidden="true">{state === "done" ? <Check size={13} /> : icon ?? (state === "current" ? <CircleDot size={13} /> : <Circle size={13} />)}</span>{label}</li>;
}

function PersonField({ label, hint, candidates, selectedId, fallbackName, onChange }: { label: string; hint?: string; candidates: Candidate[]; selectedId: string | null; fallbackName: string; onChange: (person: Candidate | null) => void }) {
  const selected = candidates.find((person) => person.user_id === selectedId) ?? null;
  const name = selected?.display_name ?? (fallbackName || null);
  return <div className={styles.field}>
    <span className={styles.label}>{label}</span>{hint ? <small className={styles.hint}>{hint}</small> : null}
    {name ? <div><span className={styles.chip} data-strong="true"><span aria-hidden="true">{initials(name)}</span>{name}<button type="button" aria-label={`Remove ${name} as ${label.toLowerCase()}`} onClick={() => onChange(null)}><X size={14} /></button></span></div>
      : <PeopleSearch candidates={candidates} exclude={[]} placeholder={`Search for the ${label.toLowerCase()}`} onPick={onChange} />}
  </div>;
}

function TeamField({ candidates, selected, extraNames, onChange }: { candidates: Candidate[]; selected: string[]; extraNames: string[]; onChange: (ids: string[], names: string[]) => void }) {
  const people = candidates.filter((person) => selected.includes(person.membership_id));
  const namesFor = (ids: string[], extras: string[]) => [...candidates.filter((person) => ids.includes(person.membership_id)).map((person) => person.display_name), ...extras];
  return <div className={styles.field}>
    <span className={styles.label}>Team</span><small className={styles.hint}>People who joined through a request are already here. Everyone added gets an invitation when the charter is submitted.</small>
    <div className={styles.teamBox}>
      {people.map((person) => <span key={person.membership_id} className={styles.chip}><span aria-hidden="true">{initials(person.display_name)}</span>{person.display_name}<button type="button" aria-label={`Remove ${person.display_name} from the team`} onClick={() => { const ids = selected.filter((id) => id !== person.membership_id); onChange(ids, namesFor(ids, extraNames)); }}><X size={14} /></button></span>)}
      {extraNames.map((name) => <span key={name} className={styles.chip} title="Named in an earlier draft, not linked to a workspace member"><span aria-hidden="true">{initials(name)}</span>{name}<button type="button" aria-label={`Remove ${name} from the team`} onClick={() => onChange(selected, namesFor(selected, extraNames.filter((value) => value !== name)))}><X size={14} /></button></span>)}
      <PeopleSearch candidates={candidates} exclude={selected} placeholder="Add people" inline onPick={(person) => { if (!person) return; const ids = [...selected, person.membership_id]; onChange(ids, namesFor(ids, extraNames)); }} />
    </div>
  </div>;
}

function PeopleSearch({ candidates, exclude, placeholder, inline = false, onPick }: { candidates: Candidate[]; exclude: string[]; placeholder: string; inline?: boolean; onPick: (person: Candidate | null) => void }) {
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState(false);
  const term = query.trim().toLocaleLowerCase();
  const matches = candidates.filter((person) => !exclude.includes(person.membership_id) && (!term || `${person.display_name} ${person.email}`.toLocaleLowerCase().includes(term))).slice(0, 8);
  return <div className={styles.search} data-inline={inline} onBlur={(event) => { if (!event.currentTarget.contains(event.relatedTarget as Node)) setOpen(false); }}>
    <Search size={15} aria-hidden="true" />
    <input type="search" value={query} placeholder={placeholder} aria-label={placeholder} onFocus={() => setOpen(true)} onChange={(event) => { setQuery(event.target.value); setOpen(true); }} onKeyDown={(event) => { if (event.key === "Escape") setOpen(false); if (event.key === "Enter" && matches[0]) { event.preventDefault(); onPick(matches[0]); setQuery(""); setOpen(false); } }} />
    {open ? <ul className={styles.results} role="listbox">
      {matches.length ? matches.map((person) => <li key={person.membership_id}><button type="button" role="option" aria-selected="false" onMouseDown={(event) => event.preventDefault()} onClick={() => { onPick(person); setQuery(""); setOpen(false); }}><span aria-hidden="true">{initials(person.display_name)}</span><span><strong>{person.display_name}</strong><small>{person.email}</small></span></button></li>)
        : <li className={styles.noResults}>No matching contributors</li>}
    </ul> : null}
  </div>;
}

function DateField({ label, value, onChange, fromIdea = false }: { label: string; value: string | null; onChange: (value: string | null) => void; fromIdea?: boolean }) {
  return <label className={styles.field}><span className={styles.label}>{label}{fromIdea ? <em className={styles.fromIdea}>From idea</em> : null}</span><input type="date" value={value ?? ""} onChange={(event) => onChange(event.target.value || null)} /></label>;
}

function TextField({ label, hint, value, onChange, placeholder, single = false }: { label: string; hint?: string; value: string; onChange: (value: string) => void; placeholder?: string; single?: boolean }) {
  return <label className={styles.field}><span className={styles.label}>{label}</span>{hint ? <small className={styles.hint}>{hint}</small> : null}
    {single ? <input value={value} onChange={(event) => onChange(event.target.value)} placeholder={placeholder} /> : <textarea rows={3} value={value} onChange={(event) => onChange(event.target.value)} placeholder={placeholder} />}
  </label>;
}

function FromIdea({ idea }: { idea: IdeaContext }) {
  const tiles: Array<[string, string]> = [
    ["Site", idea.site ?? "Not set"],
    ["Department", idea.department ?? "Not set"],
    ["SQDCP", idea.impacts.map((value) => impacts.find((impact) => impact.value === value)?.label ?? value).join(", ") || "None"],
    ["KPI", `${measure(idea.current_state, idea.baseline_uom) || "?"} → ${measure(idea.target_state, idea.target_uom) || "?"}`],
    ["Target benefit", idea.estimated_annual_saving ? `${rupees(idea.estimated_annual_saving)} / year` : "KPI only"],
  ];
  return <div className={styles.fromIdeaBlock}><p>From the approved idea</p><div className={styles.tiles}>{tiles.map(([label, value]) => <div key={label}><small>{label}</small><strong>{value}</strong></div>)}</div></div>;
}

function Differs({ show, idea }: { show: boolean; idea: string | null }) {
  return show ? <small className={styles.differs}>Differs from the idea{idea ? ` (${idea})` : ""}</small> : null;
}

function ReviewGroup({ title, onEdit, children }: { title: string; onEdit?: () => void; children: ReactNode }) {
  return <section className={styles.reviewGroup}><header><h3>{title}</h3>{onEdit ? <button type="button" onClick={onEdit}>Edit</button> : null}</header><dl>{children}</dl></section>;
}

function Fact({ label, wide = false, children }: { label: string; wide?: boolean; children: ReactNode }) {
  return <div data-wide={wide}><dt>{label}</dt><dd>{children}</dd></div>;
}

function SaveIndicator({ state }: { state: SaveState }) {
  const copy = { saved: [<Cloud key="i" size={15} />, "All changes saved"], saving: [<Cloud key="i" size={15} />, "Saving…"], unsaved: [<Cloud key="i" size={15} />, "Unsaved changes"], error: [<CloudOff key="i" size={15} />, "Not saved. Retrying on your next change."] }[state];
  return <span className={styles.saveState} data-state={state} role="status" aria-live="polite">{state === "saved" ? <CheckCircle2 size={15} aria-hidden="true" /> : copy[0]}{copy[1]}</span>;
}

/* ---------- Helpers ---------- */

/** Fill anything still empty from the idea. Returns whether a value was added, so it can be saved. */
function withIdeaDefaults(charter: Charter, idea: IdeaContext): { charter: Charter; changed: boolean } {
  if (charter.status === "submitted") return { charter: { ...charter, milestone_plan: charter.milestone_plan ?? [] }, changed: false };
  const next = { ...charter, milestone_plan: charter.milestone_plan ?? [] };
  const untouched = !charter.sponsor && !charter.in_scope && !charter.objective && !charter.start_date && !charter.kpi_name;
  if (!next.leader_user_id && !next.leader) { next.leader_user_id = idea.submitter_user_id; next.leader = idea.submitter_name; }
  if (!next.site_id && idea.site_id) next.site_id = idea.site_id;
  if (!next.department_id && idea.department_id) next.department_id = idea.department_id;
  if (!next.target_completion_date && idea.target_completion_date) next.target_completion_date = idea.target_completion_date;
  if (!next.impact_areas.length && idea.impacts.length) next.impact_areas = idea.impacts;
  if (!next.kpi_name && idea.kpi_hint) next.kpi_name = idea.kpi_hint.slice(0, 160);
  if (!next.budget_approved && idea.investment_required) next.budget_approved = idea.investment_required;
  if (untouched) next.benefit_type = idea.suggested_benefit_type;
  return { charter: next, changed: JSON.stringify(next) !== JSON.stringify(charter) };
}

function payloadFor(charter: Charter) {
  return {
    sponsor: charter.sponsor, leader: charter.leader, sponsor_user_id: charter.sponsor_user_id, leader_user_id: charter.leader_user_id,
    department_id: charter.department_id || null, site_id: charter.site_id || null, start_date: charter.start_date || null, target_completion_date: charter.target_completion_date || null,
    team_members: charter.team_members, team_membership_ids: charter.team_membership_ids, in_scope: charter.in_scope, out_of_scope: charter.out_of_scope, objective: charter.objective,
    milestone_plan: charter.milestone_plan.map((item) => ({ ...item, weight: Number(item.weight || 0) })),
    benefit_type: charter.benefit_type, kpi_name: charter.kpi_name, budget_approved: charter.budget_approved || null, impact_areas: charter.impact_areas, belt_level: charter.belt_level || null,
  };
}

function missingFields(charter: Charter, isKaizen: boolean, needsSite: boolean, needsDepartment: boolean): Array<{ label: string; step: Step }> {
  const checks: Array<[boolean, string, Step]> = [
    [Boolean(charter.leader), isKaizen ? "Team leader" : "Project leader", 1],
    [Boolean(charter.sponsor), isKaizen ? "OE Lead / Facilitator" : "Sponsor", 1],
    [Boolean(charter.start_date), "Start date", 2],
    [Boolean(charter.target_completion_date), isKaizen ? "Completion date" : "Target completion", 2],
    ...(!isKaizen ? [[Boolean(charter.in_scope.trim()), "In scope", 2], [Boolean(charter.out_of_scope.trim()), "Out of scope", 2], [Boolean(charter.objective.trim()), "Objective", 2]] as Array<[boolean, string, Step]> : []),
    ...planProblems(charter).map((problem) => [false, problem, 3] as [boolean, string, Step]),
    [!needsSite || Boolean(charter.site_id), "Site", 4],
    [!needsDepartment || Boolean(charter.department_id), "Department", 4],
    [Boolean(charter.kpi_name.trim()), "KPI or metric", 4],
  ];
  return checks.filter(([ok]) => !ok).map(([, label, step]) => ({ label, step }));
}

function sameSet(a: string[], b: string[]) { return a.length === b.length && a.every((value) => b.includes(value)); }
function measure(value: string, uom: string) { return [value, uom].filter(Boolean).join(" "); }
// Charter dates are calendar days; read them as local dates so no timezone shifts the day.
function formatDate(value: string) { return new Intl.DateTimeFormat("en-IN", { day: "numeric", month: "short", year: "numeric" }).format(new Date(`${value.slice(0, 10)}T00:00:00`)); }
function rupees(value: string) { return new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", notation: "compact", maximumFractionDigits: 1 }).format(Number(value)); }


/* ---------- Plan step ---------- */

type PlanKind = "lss" | "kaizen" | "project";
const templates: Record<PlanKind | "blank", { label: string; items: Array<[string, number, boolean]> }> = {
  lss: { label: "DMAIC", items: [["Define the problem and baseline", 10, false], ["Measure the current process", 20, false], ["Analyse root causes", 20, false], ["Improve and implement", 35, true], ["Control and sustain", 15, false]] },
  kaizen: { label: "Plan · Trial · Standardise", items: [["Plan the change", 20, false], ["Trial on the line", 40, false], ["Standardise and train", 40, true]] },
  project: { label: "Diagnose to sustain", items: [["Diagnose", 15, false], ["Design the solution", 20, false], ["Pilot", 25, false], ["Roll out", 25, true], ["Sustain and hand over", 15, false]] },
  blank: { label: "Blank", items: [["", 100, true]] },
};

function PlanEditor({ plan, owners, kind, moneyBenefits, start, target, onChange }: { plan: PlanItem[]; owners: Candidate[]; kind: PlanKind; moneyBenefits: boolean; start: string | null; target: string | null; onChange: (plan: PlanItem[]) => void }) {
  const total = plan.reduce((sum, item) => sum + Number(item.weight || 0), 0);
  const set = (index: number, patch: Partial<PlanItem>) => onChange(plan.map((item, i) => i === index ? { ...item, ...patch } : patch.benefits_start ? { ...item, benefits_start: false } : item));
  const move = (index: number, by: -1 | 1) => { const next = [...plan]; const [item] = next.splice(index, 1); next.splice(index + by, 0, item); onChange(next); };
  const applyTemplate = (key: PlanKind | "blank") => onChange(fromTemplate(templates[key].items, start, target, owners[0] ?? null));
  const spread = () => { const each = Math.floor(100 / plan.length); onChange(plan.map((item, i) => ({ ...item, weight: String(i === plan.length - 1 ? 100 - each * (plan.length - 1) : each) }))); };
  const add = () => onChange([...plan, { id: crypto.randomUUID(), title: "", owner_user_id: null, owner_name: "", due_date: target, weight: "0", benefits_start: false }]);
  const order: Array<PlanKind | "blank"> = [kind, ...(["lss", "kaizen", "project"] as PlanKind[]).filter((key) => key !== kind), "blank"];

  return <div className={styles.plan}>
    <div className={styles.templates}>
      <span>{plan.length ? "Replace with:" : "Start from:"}</span>
      {order.map((key) => <button key={key} type="button" data-suggested={key === kind} onClick={() => { if (!plan.length || window.confirm("Replace the current milestones with this template?")) applyTemplate(key); }}>{templates[key].label}{key === kind ? " · suggested" : ""}</button>)}
    </div>
    {plan.length ? <div className={styles.planTable} role="table" aria-label="Milestones">
      <div className={styles.planHead} role="row"><span role="columnheader">#</span><span role="columnheader">Milestone</span><span role="columnheader">Owner</span><span role="columnheader">Due</span><span role="columnheader">Weight</span><span role="columnheader"><span className={styles.visuallyHidden}>Actions</span></span></div>
      {plan.map((item, index) => <div key={item.id} className={styles.planRow} role="row" data-benefits={item.benefits_start}>
        <span className={styles.planIndex} role="cell">{index + 1}</span>
        <div role="cell" className={styles.planTitle}>
          <input aria-label={`Milestone ${index + 1} title`} value={item.title} maxLength={200} placeholder="What will be true when this is done?" onChange={(event) => set(index, { title: event.target.value })} />
          {moneyBenefits || item.benefits_start ? <label className={styles.benefitsToggle}><input type="radio" name="benefits-start" checked={item.benefits_start} onChange={() => set(index, { benefits_start: true })} />Benefits start here</label> : null}
        </div>
        <select role="cell" aria-label={`Milestone ${index + 1} owner`} value={item.owner_user_id ?? ""} onChange={(event) => { const person = owners.find((owner) => owner.user_id === event.target.value); set(index, { owner_user_id: person?.user_id ?? null, owner_name: person?.display_name ?? "" }); }}>
          <option value="">Unassigned</option>
          {owners.map((owner) => <option key={owner.user_id} value={owner.user_id}>{owner.display_name}</option>)}
        </select>
        <input role="cell" type="date" aria-label={`Milestone ${index + 1} due date`} value={item.due_date ?? ""} min={start ?? undefined} max={target ?? undefined} onChange={(event) => set(index, { due_date: event.target.value || null })} />
        <span role="cell" className={styles.weight}><input type="number" min="0" max="100" step="5" inputMode="numeric" aria-label={`Milestone ${index + 1} weight in percent`} value={item.weight} onChange={(event) => set(index, { weight: event.target.value })} />%</span>
        <span role="cell" className={styles.rowTools}>
          <button type="button" aria-label={`Move milestone ${index + 1} up`} disabled={index === 0} onClick={() => move(index, -1)}><ChevronUp size={15} /></button>
          <button type="button" aria-label={`Move milestone ${index + 1} down`} disabled={index === plan.length - 1} onClick={() => move(index, 1)}><ChevronDown size={15} /></button>
          <button type="button" aria-label={`Remove milestone ${index + 1}`} onClick={() => onChange(plan.filter((_, i) => i !== index))}><Trash2 size={15} /></button>
        </span>
      </div>)}
    </div> : <p className={styles.planEmpty}>Pick a template to start, or add milestones one by one.</p>}
    <div className={styles.planFooter}>
      <span className={styles.total} data-ok={total === 100}>{plan.length ? (total === 100 ? "Weights total 100%" : `Weights total ${total}%. They need to reach 100%.`) : ""}</span>
      <div>{plan.length > 1 && total !== 100 ? <button type="button" className={styles.secondary} onClick={spread}>Spread evenly</button> : null}<button type="button" className={styles.secondary} onClick={add}><Plus size={16} aria-hidden="true" />Add milestone</button></div>
    </div>
  </div>;
}

function fromTemplate(items: Array<[string, number, boolean]>, start: string | null, target: string | null, owner: Candidate | null): PlanItem[] {
  const from = start ? new Date(`${start}T00:00:00`) : new Date();
  const to = target ? new Date(`${target}T00:00:00`) : null;
  const span = to ? Math.max(0, to.getTime() - from.getTime()) : 0;
  return items.map(([title, weight, benefits], index) => {
    const due = to ? new Date(from.getTime() + (span * (index + 1)) / items.length) : null;
    return { id: crypto.randomUUID(), title, owner_user_id: owner?.user_id ?? null, owner_name: owner?.display_name ?? "", due_date: due ? isoDay(due) : null, weight: String(weight), benefits_start: benefits };
  });
}

function planProblems(charter: Charter): string[] {
  const plan = charter.milestone_plan;
  if (!plan.length) return ["At least one milestone"];
  const problems: string[] = [];
  if (plan.some((item) => !item.title.trim())) problems.push("Milestone titles");
  if (plan.some((item) => !item.due_date)) problems.push("Milestone due dates");
  if (plan.some((item) => item.due_date && ((charter.start_date && item.due_date < charter.start_date) || (charter.target_completion_date && item.due_date > charter.target_completion_date)))) problems.push("Due dates within the charter dates");
  if (plan.reduce((sum, item) => sum + Number(item.weight || 0), 0) !== 100) problems.push("Weights totalling 100%");
  const starts = plan.filter((item) => item.benefits_start).length;
  if (charter.benefit_type !== "kpi_only" && starts !== 1) problems.push("The milestone where benefits start");
  return problems;
}

function isoDay(value: Date) { return `${value.getFullYear()}-${String(value.getMonth() + 1).padStart(2, "0")}-${String(value.getDate()).padStart(2, "0")}`; }
