"use client";

import {
  ArrowLeft,
  ArrowRight,
  Check,
  CheckCircle2,
  CircleDollarSign,
  Clock3,
  FileText,
  Gauge,
  Info,
  Lightbulb,
  LockKeyhole,
  Pencil,
  Route,
  RotateCcw,
  Save,
  ShieldCheck,
  Sparkles,
  Target,
  UserCircle2,
  WalletCards,
} from "lucide-react";
import { TenantLink as Link } from "@/components/app/tenant-link";
import { useTenantRouter as useRouter } from "@/lib/use-tenant-router";
import { FormEvent, ReactNode, useEffect, useMemo, useRef, useState } from "react";
import { AdminShell } from "@/components/admin/admin-shell";
import { DismissibleNotice } from "@/components/ui/dismissible-notice";
import { SelectField } from "@/components/ui/select-field";
import { apiRequest } from "@/lib/api";
import { useSession } from "@/lib/use-session";
import styles from "./submission.module.css";

type Item = {
  id: string;
  code: string;
  name: string;
  parent_id: string | null;
  site_ids: string[];
  applies_to_all_sites: boolean;
  guidance: Record<string, string>;
};
type ApprovalStage = {
  key: string;
  name: string;
  approver_role: string;
  assignee_name: string | null;
  assignee_email: string | null;
  assignee_status: "active" | "pending" | null;
  sla_hours: number;
  required: boolean;
};
type ApprovalContract = {
  id: string;
  name: string;
  description: string;
  version: number;
  stages: ApprovalStage[];
};
type Catalog = {
  sites: Item[];
  departments: Item[];
  categories: Item[];
  subcategories: Item[];
  process_areas: Item[];
  approval_contract: ApprovalContract | null;
};
type IdeaRecord = { id: string; reference: string; status: string; draft_step: number };
type EditableIdea = {
  id: string; reference: string; status: "draft" | "needs_correction"; updated_at: string; correction_reason: string | null; draft_step: number;
  idea_type: "kaizen" | "project"; project_category: string | null; project_subtype: string | null;
  site_id: string | null; department_id: string | null; category_id: string | null; subcategory_id: string | null; process_area_id: string | null;
  title: string; problem_statement: string; business_case: string; current_state: string; baseline_uom: string; target_state: string; target_uom: string; target_completion_date: string | null;
  impacts: string[]; estimated_annual_saving: string | null; cost_avoidance: string | null; investment_required: string | null;
};
type FormState = {
  idea_type: "kaizen" | "project";
  project_category: string;
  project_subtype: string;
  site_id: string;
  department_id: string;
  category_id: string;
  subcategory_id: string;
  process_area_id: string;
  title: string;
  problem_statement: string;
  business_case: string;
  current_state: string;
  baseline_uom: string;
  target_state: string;
  target_uom: string;
  target_completion_date: string;
  impacts: string[];
  estimated_annual_saving: string;
  cost_avoidance: string;
  investment_required: string;
};

const emptyCatalog: Catalog = {
  sites: [],
  departments: [],
  categories: [],
  subcategories: [],
  process_areas: [],
  approval_contract: null,
};
const initialForm: FormState = {
  idea_type: "kaizen",
  project_category: "",
  project_subtype: "",
  site_id: "",
  department_id: "",
  category_id: "",
  subcategory_id: "",
  process_area_id: "",
  title: "",
  problem_statement: "",
  business_case: "",
  current_state: "",
  baseline_uom: "",
  target_state: "",
  target_uom: "",
  target_completion_date: "",
  impacts: [],
  estimated_annual_saving: "",
  cost_avoidance: "",
  investment_required: "",
};
const impacts = [
  { key: "safety", label: "S", name: "Safety", description: "Risk, ergonomics, and safe work" },
  { key: "quality", label: "Q", name: "Quality", description: "Defects, compliance, and consistency" },
  { key: "delivery", label: "D", name: "Delivery", description: "Lead time, flow, and reliability" },
  { key: "cost", label: "C", name: "Cost", description: "Waste, spend, and avoidable loss" },
  { key: "productivity", label: "P", name: "Productivity", description: "Capacity, effort, and output" },
];
const projectSubtypes: Record<string, string[]> = {
  "Lean Six Sigma": ["DMAIC", "DMADV"],
  "Improvement Project": ["Operational", "Cross-functional"],
  "Capex Project": ["Replacement", "Expansion", "Compliance"],
};
const stepCopy = [
  { label: "Type & category", short: "Frame the opportunity" },
  { label: "Idea details", short: "Explain the case" },
  { label: "Impact", short: "Estimate the value" },
  { label: "Review & submit", short: "Confirm the route" },
];
export function IdeaSubmission({ resumeIdeaId }: { resumeIdeaId?: string }) {
  const router = useRouter();
  const { session, loading } = useSession();
  const [catalog, setCatalog] = useState<Catalog>(emptyCatalog);
  const [form, setForm] = useState<FormState>(initialForm);
  const [step, setStep] = useState(1);
  const [draft, setDraft] = useState<IdeaRecord | null>(null);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [fieldErrors, setFieldErrors] = useState<Partial<Record<keyof FormState, boolean>>>({});
  const [submitted, setSubmitted] = useState<IdeaRecord | null>(null);
  const [fxRate, setFxRate] = useState<{ rate: string; rate_date: string; source: string } | null>(null);
  const [fxUnavailable, setFxUnavailable] = useState(false);
  const [resumeLoading, setResumeLoading] = useState(Boolean(resumeIdeaId));
  const [correctionReason, setCorrectionReason] = useState("");
  const feedbackRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!session) return;
    const timer = window.setTimeout(() => {
      apiRequest("/ideas/submission-catalog")
        .then(async (response) => {
          if (response.status === 401) return router.replace("/sign-in");
          if (!response.ok) throw new Error();
          setCatalog((await response.json()) as Catalog);
        })
        .catch(() =>
          setError(
            "The submission catalogue could not be loaded. Confirm the backend is available, then reload this page.",
          ),
        );
    }, 0);
    return () => window.clearTimeout(timer);
  }, [router, session]);

  useEffect(() => {
    if (!session) return;
    apiRequest("/ideas/exchange-rate")
      .then(async (response) => {
        if (!response.ok) throw new Error();
        setFxRate(await response.json() as { rate: string; rate_date: string; source: string });
      })
      .catch(() => setFxUnavailable(true));
  }, [session]);

  useEffect(() => {
    if (!session || !resumeIdeaId) return;
    apiRequest(`/ideas/${resumeIdeaId}/edit`)
      .then(async (response) => {
        const body = await response.json().catch(() => null) as EditableIdea | { detail?: string } | null;
        if (!response.ok) throw new Error((body as { detail?: string } | null)?.detail ?? "This idea can no longer be edited.");
        const editable = body as EditableIdea;
        setForm(toFormState(editable));
        setDraft({ id: editable.id, reference: editable.reference, status: editable.status, draft_step: editable.draft_step });
        setStep(editable.draft_step);
        setCorrectionReason(editable.correction_reason ?? "");
      })
      .catch((reason: Error) => setError(reason.message))
      .finally(() => setResumeLoading(false));
  }, [resumeIdeaId, session]);

  const update = <K extends keyof FormState>(key: K, value: FormState[K]) => {
    setForm((current) => ({ ...current, [key]: value }));
    setFieldErrors((current) => {
      if (!current[key]) return current;
      const next = { ...current };
      delete next[key];
      return next;
    });
  };
  const showError = (text: string, fieldId?: string) => {
    setMessage("");
    setError(text);
    window.requestAnimationFrame(() => {
      const target = fieldId ? document.getElementById(fieldId) : feedbackRef.current;
      target?.focus({ preventScroll: true });
      target?.scrollIntoView({ behavior: "smooth", block: "center" });
    });
  };
  const departments = useMemo(
    () =>
      catalog.departments.filter(
        (item) =>
          !form.site_id ||
          item.applies_to_all_sites ||
          item.site_ids.includes(form.site_id) ||
          item.parent_id === form.site_id,
      ),
    [catalog.departments, form.site_id],
  );
  const subcategories = useMemo(
    () => catalog.subcategories.filter((item) => item.parent_id === form.category_id),
    [catalog.subcategories, form.category_id],
  );
  const selectedSite = catalog.sites.find((item) => item.id === form.site_id);
  const selectedDepartment = catalog.departments.find((item) => item.id === form.department_id);
  const selectedCategory = catalog.categories.find((item) => item.id === form.category_id);
  const selectedSubcategory = catalog.subcategories.find((item) => item.id === form.subcategory_id);
  const benefit = Number(form.estimated_annual_saving) + Number(form.cost_avoidance);
  const payback = Number(form.investment_required) > 0 && benefit > 0
    ? (Number(form.investment_required) / benefit) * 12
    : null;
  const asUsd = (value: string) => value && fxRate
    ? new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 2 }).format(Number(value) * Number(fxRate.rate))
    : null;

  const selectSubcategory = (id: string) => {
    const guidance = catalog.subcategories.find((item) => item.id === id)?.guidance;
    setFieldErrors((current) => ({ ...current, subcategory_id: false }));
    setForm((current) => ({
      ...current,
      subcategory_id: id,
      title: current.title || guidance?.title_template || "",
      problem_statement: current.problem_statement || guidance?.problem || "",
      business_case: current.business_case || guidance?.business_case || "",
    }));
  };

  const payload = () => ({
    ...form,
    draft_step: step,
    site_id: form.site_id || null,
    department_id: form.department_id || null,
    category_id: form.category_id || null,
    subcategory_id: form.subcategory_id || null,
    process_area_id: form.process_area_id || null,
    target_completion_date: form.target_completion_date || null,
    estimated_annual_saving: form.estimated_annual_saving || null,
    cost_avoidance: form.cost_avoidance || null,
    investment_required: form.investment_required || null,
  });

  const saveDraft = async () => {
    setBusy("save");
    setError("");
    setMessage("");
    try {
      const response = await apiRequest(draft ? `/ideas/${draft.id}` : "/ideas", {
        method: draft ? "PUT" : "POST",
        body: JSON.stringify(payload()),
      });
      if (!response.ok) {
        const body = (await response.json().catch(() => null)) as { detail?: string } | null;
        throw new Error(body?.detail ?? "The draft could not be saved.");
      }
      const record = (await response.json()) as IdeaRecord;
      setDraft(record);
      setMessage(`Draft ${record.reference} saved. You can continue editing this idea.`);
      return record;
    } catch (reason) {
      showError(reason instanceof Error ? reason.message : "The draft could not be saved.");
      return null;
    } finally {
      setBusy("");
    }
  };

  const submit = async () => {
    setBusy("submit");
    setError("");
    setMessage("");
    try {
      let record = draft;
      if (!record) {
        const created = await apiRequest("/ideas", {
          method: "POST",
          body: JSON.stringify(payload()),
        });
        if (!created.ok) {
          const body = (await created.json().catch(() => null)) as { detail?: string } | null;
          throw new Error(body?.detail ?? "The draft could not be prepared.");
        }
        record = (await created.json()) as IdeaRecord;
        setDraft(record);
      }
      const correcting = record.status === "needs_correction";
      const response = await apiRequest(`/ideas/${record.id}/${correcting ? "resubmit" : "submit"}`, {
        method: "POST",
        body: JSON.stringify(payload()),
      });
      if (!response.ok) {
        const body = (await response.json().catch(() => null)) as { detail?: string } | null;
        throw new Error(body?.detail ?? `The idea could not be ${correcting ? "resubmitted" : "submitted"}.`);
      }
      setSubmitted((await response.json()) as IdeaRecord);
    } catch (reason) {
      showError(reason instanceof Error ? reason.message : "The idea could not be submitted.");
    } finally {
      setBusy("");
    }
  };

  const goToStep = (target: number) => {
    setError("");
    setFieldErrors({});
    setStep(target);
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  const back = () => {
    if (step === 1) router.push("/ideas");
    else goToStep(step - 1);
  };

  const next = () => {
    if (step === 1) {
      const missing: Partial<Record<keyof FormState, boolean>> = {};
      if (form.idea_type === "project" && !form.project_category) missing.project_category = true;
      if (form.idea_type === "project" && !form.project_subtype) missing.project_subtype = true;
      if (!form.category_id) missing.category_id = true;
      if (!form.subcategory_id) missing.subcategory_id = true;
      if (Object.keys(missing).length) {
        setFieldErrors(missing);
        const firstId = missing.project_category ? "project-category" : missing.project_subtype ? "project-subtype" : missing.category_id ? "category" : "subcategory";
        return showError("Complete the highlighted classification fields before continuing.", firstId);
      }
    }
    if (step === 2) {
      const missing: Partial<Record<keyof FormState, boolean>> = {};
      if (!form.title.trim()) missing.title = true;
      if (!form.problem_statement.trim()) missing.problem_statement = true;
      if (!form.business_case.trim()) missing.business_case = true;
      if (Object.keys(missing).length) {
        setFieldErrors(missing);
        const firstId = missing.title ? "idea-title" : missing.problem_statement ? "problem-statement" : "business-case";
        return showError("Complete the highlighted idea details before continuing.", firstId);
      }
    }
    if (step === 3 && !form.impacts.length) {
      setFieldErrors({ impacts: true });
      return showError("Select at least one SQDCP impact before reviewing the idea.", "impact-safety");
    }
    goToStep(Math.min(4, step + 1));
  };

  if (loading || !session || resumeLoading) {
    return <main className={styles.loading}>Preparing your idea workspace…</main>;
  }

  if (submitted) {
    return (
      <AdminShell
        session={session}
        active="submit"
        eyebrow={draft?.status === "needs_correction" ? "Idea resubmitted" : "Idea submitted"}
        title={draft?.status === "needs_correction" ? "Your correction is back in review." : "Your observation is now in motion."}
        description={`${submitted.reference} has been ${draft?.status === "needs_correction" ? "returned to its captured approval route" : "recorded against the published approval contract"}.`}
      >
        <section className={styles.success}>
          <CheckCircle2 size={30} />
          <div>
            <p className={styles.successEyebrow}>{draft?.status === "needs_correction" ? "Correction submitted" : "Contribution recorded"}</p>
            <h2>{draft?.status === "needs_correction" ? "The next approval round has started." : "Thank you for making improvement visible."}</h2>
            <p>
              {draft?.status === "needs_correction" ? "Earlier decisions and comments remain visible. Reviewers now act on a new round using the workflow version captured at first submission." : "Your idea is now available according to your organisation’s Idea Bank policy. Its approval route was fixed at submission, so future workflow changes will not alter this record."}
            </p>
            <div>
              <Link href="/ideas">Open Idea Bank</Link>
              <Link href="/ideas/new/v2">Submit another idea</Link>
            </div>
          </div>
        </section>
      </AdminShell>
    );
  }

  const showContinue = step < 4;
  const nextDestination = step < 4 ? stepCopy[step].label : "";
  const backDestination = step > 1 ? stepCopy[step - 2].label : "";

  return (
    <AdminShell
      session={session}
      active="submit"
      eyebrow={draft?.status === "needs_correction" ? "Correction requested" : draft ? "Draft idea" : "Idea submission"}
      title={draft?.status === "needs_correction" ? "Address the feedback and return the idea to review." : draft ? `Continue ${draft.reference}` : "Turn something worth noticing into action."}
      description={draft?.status === "needs_correction" ? "Update the submitted case with the requested clarification. The original approval history remains unchanged." : "Build a clear improvement case with the context, evidence, and expected value reviewers need to act confidently."}
    >
      {draft?.status === "needs_correction" ? <section className={styles.correctionBanner}><RotateCcw size={20} /><div><p>Approver feedback</p><h2>Correction required before approval can continue</h2><span>{correctionReason || "Review the approval timeline for the requested correction, update the idea, and resubmit it."}</span></div><Link href={`/ideas/${draft.id}?section=approval`}>View approval history</Link></section> : null}
      <nav className={styles.stepNavigation} aria-label="Idea submission progress">
        <ol className={styles.steps}>
          {stepCopy.map((item, index) => {
            const number = index + 1;
            return (
              <li
                key={item.label}
                data-active={step === number}
                data-complete={step > number}
                aria-current={step === number ? "step" : undefined}
              >
                <span>{step > number ? <Check size={14} /> : number}</span>
                <div><strong>{item.label}</strong><small>{item.short}</small></div>
              </li>
            );
          })}
        </ol>
        <p>Step {step} of 4 · {stepCopy[step - 1].short}</p>
      </nav>

      <div ref={feedbackRef} className={styles.toastStack} tabIndex={-1}>
        {error ? <DismissibleNotice tone="error" onDismiss={() => setError("")}>{error}</DismissibleNotice> : null}
        {message ? <DismissibleNotice onDismiss={() => setMessage("")}>{message}</DismissibleNotice> : null}
      </div>

      <form className={styles.form} onSubmit={(event: FormEvent) => event.preventDefault()}>
        {step === 1 ? (
          <section aria-labelledby="step-one-title">
            <SectionHeading
              id="step-one-title"
              icon={<Lightbulb size={20} />}
              eyebrow="Frame the opportunity"
              title="Start with context and classification."
              description="The choices here determine which guidance appears and help the organisation route, compare, and learn from similar ideas."
            />

            <FormSection
              icon={<UserCircle2 size={18} />}
              title="Submission context"
              description="Your identity and workspace are attached automatically. Select the operational location where the opportunity was observed."
            >
              <div className={styles.contextGrid}>
                <ReadOnlyFact label="Submitted by" value={session.user.display_name} meta={session.user.email} />
                <ReadOnlyFact label="Workspace" value={session.tenant.name} meta="Current tenant" />
                <div className={styles.selectWithHelp}>
                  <SelectField
                    id="site"
                    name="site_id"
                    label="Site"
                    value={form.site_id}
                    onChange={(value) =>
                      setForm((current) => ({ ...current, site_id: value, department_id: "" }))
                    }
                    options={[
                      { value: "", label: catalog.sites.length ? "Select a site" : "No sites configured", description: "Optional until employee-profile integration" },
                      ...catalog.sites.map((item) => ({ value: item.id, label: item.name, description: item.code })),
                    ]}
                  />
                  <small>Choose where the current condition occurs.</small>
                </div>
                <div className={styles.selectWithHelp}>
                  <SelectField
                    id="department"
                    name="department_id"
                    label="Department"
                    value={form.department_id}
                    onChange={(value) => update("department_id", value)}
                    disabled={!departments.length}
                    options={[
                      { value: "", label: departments.length ? "Select a department" : "No departments available", description: form.site_id ? "Scoped to the selected site" : "Choose a site to narrow the list" },
                      ...departments.map((item) => ({ value: item.id, label: item.name })),
                    ]}
                  />
                  <small>Use the team that owns or experiences the process.</small>
                </div>
              </div>
            </FormSection>

            <FormSection
              icon={<Target size={18} />}
              title="Improvement type"
              description="Choose the delivery shape, not the perceived importance. Both types can create substantial value."
            >
              <div className={styles.typeChoice} role="radiogroup" aria-label="Improvement type">
                <button
                  type="button"
                  role="radio"
                  aria-checked={form.idea_type === "kaizen"}
                  data-active={form.idea_type === "kaizen"}
                  onClick={() => update("idea_type", "kaizen")}
                >
                  <span className={styles.choiceIcon}><Sparkles size={19} /></span>
                  <span className={styles.choiceCopy}>
                    <strong>Kaizen</strong>
                    <small>A focused, practical improvement that can usually be tested and adopted within the existing process.</small>
                    <em>Best for: quick changes, local waste removal, standard-work improvements</em>
                  </span>
                  <span className={styles.choiceState}>{form.idea_type === "kaizen" ? <Check size={15} /> : null}</span>
                </button>
                <button
                  type="button"
                  role="radio"
                  aria-checked={form.idea_type === "project"}
                  data-active={form.idea_type === "project"}
                  onClick={() => update("idea_type", "project")}
                >
                  <span className={styles.choiceIcon}><Route size={19} /></span>
                  <span className={styles.choiceCopy}>
                    <strong>Project</strong>
                    <small>A structured improvement requiring coordinated delivery, formal analysis, investment, or cross-functional ownership.</small>
                    <em>Best for: DMAIC, capital, compliance, or multi-team change</em>
                  </span>
                  <span className={styles.choiceState}>{form.idea_type === "project" ? <Check size={15} /> : null}</span>
                </button>
              </div>
              {form.idea_type === "project" ? (
                <div className={styles.progressiveBlock}>
                  <div><Route size={17} /><p><strong>Project detail required</strong><span>These fields clarify the expected delivery method and governance.</span></p></div>
                  <div className={styles.grid}>
                    <SelectField
                      id="project-category"
                      name="project_category"
                      label="Project category"
                      value={form.project_category}
                      onChange={(value) => {
                        setForm((current) => ({ ...current, project_category: value, project_subtype: "" }));
                        setFieldErrors((current) => ({ ...current, project_category: false, project_subtype: false }));
                      }}
                      invalid={Boolean(fieldErrors.project_category)}
                      options={[{ value: "", label: "Select a project category", description: "Choose the governing delivery approach" }, ...Object.keys(projectSubtypes).map((value) => ({ value, label: value }))]}
                    />
                    <SelectField
                      id="project-subtype"
                      name="project_subtype"
                      label="Project subtype"
                      value={form.project_subtype}
                      onChange={(value) => update("project_subtype", value)}
                      invalid={Boolean(fieldErrors.project_subtype)}
                      disabled={!form.project_category}
                      options={[{ value: "", label: form.project_category ? "Select a project subtype" : "Choose a category first", description: "Refine the project route" }, ...(projectSubtypes[form.project_category] ?? []).map((value) => ({ value, label: value }))]}
                    />
                  </div>
                </div>
              ) : null}
            </FormSection>

            <FormSection
              icon={<Gauge size={18} />}
              title="Improvement classification"
              description="Category and subcategory connect the idea to TRANSPIRE’s shared Operational Excellence catalogue and unlock relevant writing guidance."
              required
            >
              <div className={styles.grid}>
                <div className={styles.selectWithHelp}>
                  <SelectField
                    id="category"
                    name="category_id"
                    label="Category"
                    value={form.category_id}
                    onChange={(value) => {
                      setForm((current) => ({ ...current, category_id: value, subcategory_id: "" }));
                      setFieldErrors((current) => ({ ...current, category_id: false, subcategory_id: false }));
                    }}
                    invalid={Boolean(fieldErrors.category_id)}
                    options={[{ value: "", label: "Select a category", description: "Choose the broad improvement theme" }, ...catalog.categories.map((item) => ({ value: item.id, label: item.name, description: item.guidance.source === "URS" ? "TRANSPIRE starter catalogue" : undefined }))]}
                  />
                  <small>Start with the broadest theme that describes the opportunity.</small>
                </div>
                <div className={styles.selectWithHelp}>
                  <SelectField
                    id="subcategory"
                    name="subcategory_id"
                    label="Subcategory"
                    value={form.subcategory_id}
                    onChange={selectSubcategory}
                    invalid={Boolean(fieldErrors.subcategory_id)}
                    disabled={!form.category_id}
                    options={[{ value: "", label: subcategories.length ? "Select a subcategory" : "Choose a category first", description: "This selection supplies tailored guidance" }, ...subcategories.map((item) => ({ value: item.id, label: item.name, description: item.guidance.kpi }))]}
                  />
                  <small>Choose the closest operational pattern; you can refine the narrative next.</small>
                </div>
              </div>
              {selectedSubcategory ? <GuidancePanel item={selectedSubcategory} /> : (
                <aside className={styles.guidanceEmpty}><Info size={18} /><div><strong>Guidance will appear here</strong><p>Select a subcategory to see a title structure, typical problem pattern, business-case prompt, and KPI.</p></div></aside>
              )}
            </FormSection>
          </section>
        ) : null}

        {step === 2 ? (
          <section aria-labelledby="step-two-title">
            <SectionHeading
              id="step-two-title"
              icon={<FileText size={20} />}
              eyebrow="Build the case"
              title="Make the opportunity easy to understand."
              description="Write for someone who does not work beside the process every day. Use observable facts, explain the consequence, and define what better looks like."
            />

            <FormSection icon={<Lightbulb size={18} />} title="Idea headline" description="Use a concise outcome-oriented title. The selected subcategory may have provided a starter structure; every word remains editable." required>
              <Field label="Idea title" hint="Name the process or condition and the intended improvement." example="Example: Reduce tooling wait time during weekly line changeovers" required invalid={Boolean(fieldErrors.title)} count={`${form.title.length} / 120`}>
                <input id="idea-title" aria-invalid={Boolean(fieldErrors.title)} value={form.title} maxLength={120} placeholder="Describe the improvement in one clear line" onChange={(event) => update("title", event.target.value)} />
              </Field>
            </FormSection>

            <FormSection icon={<FileText size={18} />} title="Current problem and improvement case" description="Separate what is happening now from why the organisation should act. This gives reviewers both operational evidence and decision context." required>
              <aside className={styles.fiveWOneH}>
                <div><Sparkles size={18} /><p><strong>Use 5W1H to make the problem observable</strong><span>A strong statement can be verified by another person.</span></p></div>
                <ul>
                  <li><b>What</b><span>condition or failure</span></li>
                  <li><b>When</b><span>timing or frequency</span></li>
                  <li><b>Where</b><span>process or location</span></li>
                  <li><b>Who</b><span>people affected</span></li>
                  <li><b>Which</b><span>pattern or variant</span></li>
                  <li><b>How</b><span>scale or consequence</span></li>
                </ul>
              </aside>
              <div className={styles.grid}>
                <Field label="Problem statement" hint="Describe the current condition without jumping directly to a solution." example="Example: During weekly changeovers, operators wait 18–25 minutes for verified tooling, delaying every first-off inspection." required invalid={Boolean(fieldErrors.problem_statement)} count={`${form.problem_statement.length} / 600`}>
                  <textarea id="problem-statement" aria-invalid={Boolean(fieldErrors.problem_statement)} rows={8} value={form.problem_statement} maxLength={600} placeholder="What is happening, where, how often, and with what effect?" onChange={(event) => update("problem_statement", event.target.value)} />
                </Field>
                <Field label="Business case and proposed improvement" hint="Explain the proposed direction, expected benefit, and why the opportunity deserves attention." example="Include the operational benefit, risk reduction, customer effect, or capacity released." required invalid={Boolean(fieldErrors.business_case)} count={`${form.business_case.length} / 600`}>
                  <textarea id="business-case" aria-invalid={Boolean(fieldErrors.business_case)} rows={8} value={form.business_case} maxLength={600} placeholder="What should change, why is it worthwhile, and how might success be demonstrated?" onChange={(event) => update("business_case", event.target.value)} />
                </Field>
              </div>
            </FormSection>

            <FormSection icon={<Target size={18} />} title="Baseline and target condition" description="Quantify the gap when data is available. A useful target is specific enough to evaluate after implementation.">
              <div className={styles.grid}>
                <Field label="Current state / baseline" hint="State the present measure, rate, duration, or observed condition." example="Example: Average wait 22 minutes; first-pass yield 88%">
                  <div className={styles.measureInput}><input value={form.current_state} placeholder="Describe the measurable starting point" onChange={(event) => update("current_state", event.target.value)} /><input aria-label="Baseline unit of measure" value={form.baseline_uom} maxLength={40} placeholder="UoM, e.g. min, %, kg" onChange={(event) => update("baseline_uom", event.target.value)} /></div>
                </Field>
                <Field label="Target state" hint="Describe the intended future condition using the same measure where possible." example="Example: Average wait under 5 minutes; first-pass yield 93%">
                  <div className={styles.measureInput}><input value={form.target_state} placeholder="Describe what successful improvement looks like" onChange={(event) => update("target_state", event.target.value)} /><input aria-label="Target unit of measure" value={form.target_uom} maxLength={40} placeholder="UoM, e.g. min, %, kg" onChange={(event) => update("target_uom", event.target.value)} /></div>
                </Field>
              </div>
            </FormSection>

          </section>
        ) : null}

        {step === 3 ? (
          <section aria-labelledby="step-three-title">
            <SectionHeading
              id="step-three-title"
              icon={<CircleDollarSign size={20} />}
              eyebrow="Expected impact"
              title="Connect the idea to measurable value."
              description="Select every affected SQDCP dimension and provide the best available estimates. Early estimates may be directional, but their basis should remain understandable."
            />

            <FormSection icon={<Gauge size={18} />} title="SQDCP impact" description="Select all dimensions the idea is expected to improve. Reviewers use these signals to compare value beyond financial return." required>
              <fieldset className={styles.impactSet} data-invalid={Boolean(fieldErrors.impacts)}>
                <legend className={styles.visuallyHidden}>SQDCP impact dimensions</legend>
                {impacts.map((impact) => {
                  const active = form.impacts.includes(impact.key);
                  return (
                    <button id={`impact-${impact.key}`} key={impact.key} type="button" aria-pressed={active} data-active={active} onClick={() => update("impacts", active ? form.impacts.filter((value) => value !== impact.key) : [...form.impacts, impact.key])}>
                      <span>{impact.label}</span>
                      <div><strong>{impact.name}</strong><small>{impact.description}</small></div>
                      <i>{active ? <Check size={14} /> : null}</i>
                    </button>
                  );
                })}
              </fieldset>
            </FormSection>

            <FormSection icon={<WalletCards size={18} />} title="Financial estimate" description="Use annualised values in Indian rupees. Enter zero only when the value has been assessed and is genuinely zero; otherwise leave the field blank.">
              <div className={styles.gridThree}>
                <Field label="Estimated annual saving" hint="Recurring reduction in operating cost after implementation." example="₹ per year">
                  <div className={styles.moneyInput}><span>₹</span><input aria-label="Estimated annual saving in rupees" type="number" min="0" inputMode="decimal" value={form.estimated_annual_saving} placeholder="0" onChange={(event) => update("estimated_annual_saving", event.target.value)} /></div>{asUsd(form.estimated_annual_saving) ? <small className={styles.usdValue}>≈ {asUsd(form.estimated_annual_saving)} USD</small> : null}
                </Field>
                <Field label="Annual cost avoidance" hint="Expected future cost prevented by implementing the idea." example="₹ per year">
                  <div className={styles.moneyInput}><span>₹</span><input aria-label="Annual cost avoidance in rupees" type="number" min="0" inputMode="decimal" value={form.cost_avoidance} placeholder="0" onChange={(event) => update("cost_avoidance", event.target.value)} /></div>{asUsd(form.cost_avoidance) ? <small className={styles.usdValue}>≈ {asUsd(form.cost_avoidance)} USD</small> : null}
                </Field>
                <Field label="Investment required" hint="One-time expenditure needed to implement the improvement." example="₹ one time">
                  <div className={styles.moneyInput}><span>₹</span><input aria-label="Investment required in rupees" type="number" min="0" inputMode="decimal" value={form.investment_required} placeholder="0" onChange={(event) => update("investment_required", event.target.value)} /></div>{asUsd(form.investment_required) ? <small className={styles.usdValue}>≈ {asUsd(form.investment_required)} USD</small> : null}
                </Field>
              </div>
              <p className={styles.fxNote}>{fxRate ? `USD equivalents use the ${fxRate.source} rate dated ${new Date(`${fxRate.rate_date}T00:00:00`).toLocaleDateString()}. The dated rate is fixed when the idea is submitted.` : fxUnavailable ? "USD conversion is temporarily unavailable. INR estimates can still be saved and submitted." : "Loading the latest INR to USD reference rate…"}</p>
              <div className={styles.payback} data-calculated={payback !== null}>
                <CircleDollarSign size={20} />
                <div><span>Indicative payback</span><strong>{payback === null ? "Add investment and annual benefit to calculate" : `${payback.toFixed(1)} months`}</strong><small>Calculated as investment ÷ annual saving and avoidance × 12. Final validation belongs to the approval process.</small></div>
              </div>
            </FormSection>

            <FormSection icon={<ShieldCheck size={18} />} title="Evidence readiness" description="Attachments will be introduced with secure storage and malware scanning. For now, include the essential evidence or measurement basis in the narrative before submitting.">
              <div className={styles.evidenceNote}><Info size={18} /><p><strong>Prepare useful supporting evidence</strong><span>Before the attachment capability is enabled, retain photographs, process maps, calculations, or baseline reports against the idea reference shown after saving.</span></p></div>
            </FormSection>
          </section>
        ) : null}

        {step === 4 ? (
          <section aria-labelledby="step-four-title">
            <SectionHeading
              id="step-four-title"
              icon={<Check size={20} />}
              eyebrow="Review & submit"
              title="Confirm the story and its approval route."
              description="Review this as the first approver will see it. Correct unclear context now; submission fixes the published workflow version to this idea."
            />

            <div className={styles.readyBanner} data-ready={Boolean(catalog.approval_contract)}>
              {catalog.approval_contract ? <CheckCircle2 size={24} /> : <Info size={24} />}
              <div><strong>{catalog.approval_contract ? "Ready to submit" : "Approval contract unavailable"}</strong><p>{catalog.approval_contract ? `This idea will enter ${catalog.approval_contract.name}, version ${catalog.approval_contract.version}, when submitted.` : "A Tenant Admin must publish an approval contract before this idea can be submitted. You can still save the draft."}</p></div>
            </div>

            <ReviewGroup title="Submitter and classification" description="Identity, workspace, location, and catalogue context." onEdit={() => goToStep(1)}>
              <div className={styles.reviewGrid}>
                <ReviewFact label="Submitted by" value={session.user.display_name} meta={session.user.email} />
                <ReviewFact label="Workspace" value={session.tenant.name} />
                <ReviewFact label="Idea type" value={titleCase(form.idea_type)} meta={form.idea_type === "project" ? [form.project_category, form.project_subtype].filter(Boolean).join(" · ") : "Focused improvement"} />
                <ReviewFact label="Location" value={[selectedSite?.name, selectedDepartment?.name].filter(Boolean).join(" · ") || "Not provided"} />
                <ReviewFact label="Category" value={selectedCategory?.name ?? "Not provided"} />
                <ReviewFact label="Subcategory" value={selectedSubcategory?.name ?? "Not provided"} />
              </div>
            </ReviewGroup>

            <ReviewGroup title="Idea details" description="The operational story reviewers will evaluate." onEdit={() => goToStep(2)}>
              <div className={styles.reviewTitle}><span>Idea title</span><strong>{form.title}</strong><small>{draft?.reference ?? "Reference assigned when the draft is first saved"}</small></div>
              <div className={styles.reviewNarrative}>
                <ReviewFact label="Problem statement" value={form.problem_statement} />
                <ReviewFact label="Business case and proposed improvement" value={form.business_case} />
              </div>
              <div className={styles.reviewGrid}>
                <ReviewFact label="Current state / baseline" value={[form.current_state, form.baseline_uom].filter(Boolean).join(" · ") || "Not provided"} />
                <ReviewFact label="Target state" value={[form.target_state, form.target_uom].filter(Boolean).join(" · ") || "Not provided"} />
              </div>
            </ReviewGroup>

            <ReviewGroup title="Expected impact" description="SQDCP dimensions and directional financial value." onEdit={() => goToStep(3)}>
              <div className={styles.reviewImpacts}>{form.impacts.map((key) => { const impact = impacts.find((item) => item.key === key); return impact ? <span key={key}><b>{impact.label}</b>{impact.name}</span> : null; })}</div>
              <div className={styles.reviewGrid}>
                <ReviewFact label="Estimated annual saving" value={formatCurrency(form.estimated_annual_saving)} meta={asUsd(form.estimated_annual_saving) ?? undefined} />
                <ReviewFact label="Annual cost avoidance" value={formatCurrency(form.cost_avoidance)} meta={asUsd(form.cost_avoidance) ?? undefined} />
                <ReviewFact label="Investment required" value={formatCurrency(form.investment_required)} meta={asUsd(form.investment_required) ?? undefined} />
                <ReviewFact label="Indicative payback" value={payback === null ? "Not calculated" : `${payback.toFixed(1)} months`} />
              </div>
            </ReviewGroup>

            <ReviewGroup title="Approval workflow" description="The published contract that will be fixed to this idea at submission.">
              {catalog.approval_contract ? (
                <div className={styles.workflowHeader}>
                  <div><Route size={20} /><p><strong>{catalog.approval_contract.name} · Version {catalog.approval_contract.version}</strong><span>{catalog.approval_contract.description || "The organisation’s published idea approval contract."}</span></p></div>
                  <ol className={styles.workflow}>
                    {catalog.approval_contract.stages.map((stage, index) => (
                      <li key={stage.key}>
                        <span className={styles.stageNumber}>{index + 1}</span>
                        <div><strong>{stage.name}</strong><p>{stage.assignee_name ?? `Assigned by role: ${titleCase(stage.approver_role)}`}</p><small>{stage.assignee_email ?? "Resolved when the stage begins"}</small></div>
                        <div className={styles.stageMeta}><span data-status={stage.assignee_status ?? "role"}>{stage.assignee_status ? titleCase(stage.assignee_status) : "Role based"}</span><small><Clock3 size={13} />{formatSla(stage.sla_hours)}</small></div>
                      </li>
                    ))}
                  </ol>
                  <p className={styles.workflowOutcome}><Check size={16} />All required stages complete → idea approved for the next operational action.</p>
                </div>
              ) : <div className={styles.missingWorkflow}><Info size={18} /><p>No published approval workflow is currently available. Save this idea as a draft and contact a Tenant Admin.</p></div>}
            </ReviewGroup>
          </section>
        ) : null}

        <footer className={styles.actions}>
          <button type="button" className={styles.secondary} onClick={back}>
            <ArrowLeft size={16} />{step === 1 ? "Cancel" : `Back to ${backDestination}`}
          </button>
          <div>
            <button type="button" className={styles.secondary} onClick={() => void saveDraft()} disabled={Boolean(busy)}>
              <Save size={16} />{busy === "save" ? "Saving…" : draft ? "Save changes" : "Save draft"}
            </button>
            {showContinue ? (
              <button type="button" className={styles.primary} onClick={next}>
                Continue to {nextDestination}<ArrowRight size={16} />
              </button>
            ) : (
              <button type="button" className={styles.primary} onClick={() => void submit()} disabled={Boolean(busy) || !catalog.approval_contract}>
                {busy === "submit" ? (draft?.status === "needs_correction" ? "Resubmitting…" : "Submitting…") : (draft?.status === "needs_correction" ? "Resubmit correction" : "Submit idea")}<ArrowRight size={16} />
              </button>
            )}
          </div>
        </footer>
      </form>
    </AdminShell>
  );
}

function SectionHeading({ id, icon, eyebrow, title, description }: { id: string; icon: ReactNode; eyebrow: string; title: string; description: string }) {
  return <header className={styles.sectionHeading}><span>{icon}</span><div><p>{eyebrow}</p><h2 id={id}>{title}</h2><small>{description}</small></div></header>;
}

function FormSection({ icon, title, description, required = false, children }: { icon: ReactNode; title: string; description: string; required?: boolean; children: ReactNode }) {
  return <section className={styles.formSection}><header><span>{icon}</span><div><div><h3>{title}</h3>{required ? <b>Required section</b> : null}</div><p>{description}</p></div></header><div className={styles.sectionBody}>{children}</div></section>;
}

function Field({ label, hint, example, count, required = false, invalid = false, children }: { label: string; hint?: string; example?: string; count?: string; required?: boolean; invalid?: boolean; children: ReactNode }) {
  return <label className={styles.field} data-invalid={invalid}><span><strong>{label}</strong>{required ? <b>Required</b> : <em>Optional</em>}</span>{hint ? <small>{hint}</small> : null}{children}<span className={styles.fieldMeta}>{example ? <i>{example}</i> : <i />}{count ? <em>{count}</em> : null}</span></label>;
}

function ReadOnlyFact({ label, value, meta }: { label: string; value: string; meta?: string }) {
  return <div className={styles.readOnlyFact}><span>{label}<LockKeyhole size={13} /></span><strong>{value}</strong>{meta ? <small>{meta}</small> : null}</div>;
}

function GuidancePanel({ item }: { item: Item }) {
  const guidance = item.guidance;
  return <aside className={styles.guidance}><div className={styles.guidanceLead}><Sparkles size={19} /><div><strong>Starter guidance for {item.name}</strong><p>TRANSPIRE has pre-filled empty narrative fields from this pattern. Treat the content as a prompt and replace it with evidence from your situation.</p></div></div><dl><div><dt>Title structure</dt><dd>{guidance.title_template || "Describe the process and intended improvement"}</dd></div><div><dt>Typical problem</dt><dd>{guidance.problem || "Explain the observable current condition"}</dd></div><div><dt>Business-case direction</dt><dd>{guidance.business_case || "Connect the change to measurable operational value"}</dd></div><div><dt>Typical KPI</dt><dd>{guidance.kpi || "Select the measure that best demonstrates improvement"}</dd></div></dl></aside>;
}

function ReviewGroup({ title, description, onEdit, children }: { title: string; description: string; onEdit?: () => void; children: ReactNode }) {
  return <section className={styles.reviewGroup}><header><div><h3>{title}</h3><p>{description}</p></div>{onEdit ? <button type="button" onClick={onEdit}><Pencil size={14} />Edit section</button> : null}</header><div>{children}</div></section>;
}

function ReviewFact({ label, value, meta }: { label: string; value: string; meta?: string }) {
  return <div className={styles.reviewFact}><span>{label}</span><strong>{value}</strong>{meta ? <small>{meta}</small> : null}</div>;
}

function titleCase(value: string) {
  return value.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function formatCurrency(value: string) {
  if (!value) return "Not provided";
  return new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 0 }).format(Number(value));
}

function formatSla(hours: number) {
  if (hours % 24 === 0) return `${hours / 24} business-day target`;
  return `${hours}-hour target`;
}

function toFormState(idea: EditableIdea): FormState {
  return {
    idea_type: idea.idea_type,
    project_category: idea.project_category ?? "",
    project_subtype: idea.project_subtype ?? "",
    site_id: idea.site_id ?? "",
    department_id: idea.department_id ?? "",
    category_id: idea.category_id ?? "",
    subcategory_id: idea.subcategory_id ?? "",
    process_area_id: idea.process_area_id ?? "",
    title: idea.title,
    problem_statement: idea.problem_statement,
    business_case: idea.business_case,
    current_state: idea.current_state,
    baseline_uom: idea.baseline_uom,
    target_state: idea.target_state,
    target_uom: idea.target_uom,
    target_completion_date: idea.target_completion_date ?? "",
    impacts: idea.impacts,
    estimated_annual_saving: idea.estimated_annual_saving === null ? "" : String(idea.estimated_annual_saving),
    cost_avoidance: idea.cost_avoidance === null ? "" : String(idea.cost_avoidance),
    investment_required: idea.investment_required === null ? "" : String(idea.investment_required),
  };
}
