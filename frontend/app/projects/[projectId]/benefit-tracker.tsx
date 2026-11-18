"use client";

import { AlertTriangle, Check, Clock3, Flag, Send, ShieldCheck, Undo2 } from "lucide-react";
import { useCallback, useState } from "react";
import { apiRequest } from "@/lib/api";
import styles from "./benefit-tracker.module.css";

export type BenefitMonth = {
  month: string; plan: string; achieved: string; has_actual?: boolean; line_of_sight: string; kpi_actual: string | null;
  status: string; notes?: string; finance_approved: boolean; finance_status?: string; finance_comment?: string;
};
export type BenefitTracking = {
  state: "waiting" | "open" | "unplanned"; milestone_title: string | null; milestone_due: string | null; milestone_status: string | null;
  annual_target: string; kpi_only: boolean; kpi_name: string; kpi_baseline: string; kpi_target: string; can_record: boolean; can_validate: boolean;
};
type TrackerProject = { id: string; benefit_periods: BenefitMonth[]; benefits?: BenefitTracking | null };

const deliveryStates = [{ value: "", label: "Not set" }, { value: "on_track", label: "On track" }, { value: "delayed", label: "Delayed" }, { value: "achieved", label: "Achieved" }];

/** Month-on-month benefits, recorded in delivery once the benefits milestone is complete. Amounts in ₹ lakhs. */
export function BenefitTracker<P extends TrackerProject>({ project, onChange, onOpenMilestones }: { project: P; onChange: (project: P) => void; onOpenMilestones: () => void }) {
  const tracking = project.benefits;
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [challenging, setChallenging] = useState<string | null>(null);
  const [comment, setComment] = useState("");

  const send = useCallback(async (key: string, method: string, path: string, body?: unknown) => {
    setBusy(key); setError("");
    try {
      const response = await apiRequest(`/projects/${project.id}${path}`, { method, body: body === undefined ? undefined : JSON.stringify(body) });
      const payload = await response.json().catch(() => null) as P | { detail?: unknown } | null;
      if (!response.ok) throw new Error(typeof (payload as { detail?: unknown } | null)?.detail === "string" ? (payload as { detail: string }).detail : "That didn't save. Try again.");
      onChange(payload as P);
      return true;
    } catch (caught) { setError(caught instanceof Error ? caught.message : "That didn't save. Try again."); return false; }
    finally { setBusy(""); }
  }, [onChange, project.id]);

  if (!tracking) return null;
  const months = project.benefit_periods;
  const thisMonth = new Date().toISOString().slice(0, 7);
  const toDate = months.filter((month) => month.month <= thisMonth);
  const ytmPlan = sum(toDate.map((month) => month.plan));
  const ytmActual = sum(months.map((month) => month.achieved));
  const validated = sum(months.filter((month) => month.finance_status === "validated").map((month) => month.achieved));
  const los = sum(months.map((month) => month.line_of_sight));
  const money = !tracking.kpi_only;

  return <section className={styles.tracker} aria-labelledby="benefits-heading">
    <header className={styles.head}>
      <div><h2 id="benefits-heading">Benefits</h2><p>{money ? "Amounts are in ₹ lakhs. Each month is sent to Finance once its actual is recorded." : "This project measures its KPI only. Record the KPI each month."}</p></div>
    </header>

    {money ? <div className={styles.tiles}>
      <Tile label="Annual target" value={lakhs(tracking.annual_target)} note="From the approved idea" />
      <Tile label="Plan to date" value={lakhs(ytmPlan)} note={toDate.length ? `${toDate.length} of ${months.length} months` : "Starts with the first month"} />
      <Tile label="Achieved" value={lakhs(ytmActual)} note={ytmPlan > 0 ? `${Math.round((ytmActual / ytmPlan) * 100)}% of plan to date` : "Nothing recorded yet"} tone={ytmPlan > 0 && ytmActual >= ytmPlan ? "success" : undefined} />
      <Tile label="Finance validated" value={lakhs(validated)} note={ytmActual > 0 ? `${Math.round((validated / ytmActual) * 100)}% of achieved` : "None yet"} />
      <Tile label="Line of sight" value={lakhs(los)} note="Expected but not yet realised" />
    </div> : <div className={styles.tiles}><Tile label="KPI" value={tracking.kpi_name || "Not named"} note={[tracking.kpi_baseline && `from ${tracking.kpi_baseline}`, tracking.kpi_target && `to ${tracking.kpi_target}`].filter(Boolean).join(" ") || undefined} /></div>}

    {error ? <p className={styles.error} role="alert">{error}</p> : null}

    {tracking.state === "unplanned" ? <div className={styles.waiting}>
      <Flag size={20} aria-hidden="true" />
      <div><strong>No milestone marks when benefits start</strong><p>Choose the milestone after which savings begin, for example go-live. Monthly tracking opens when it&apos;s complete.</p></div>
      {tracking.can_record ? <button type="button" className={styles.primary} onClick={onOpenMilestones}>Go to milestones</button> : null}
    </div> : null}

    {tracking.state === "waiting" ? <div className={styles.waiting}>
      <Clock3 size={20} aria-hidden="true" />
      <div><strong>Benefits start after &ldquo;{tracking.milestone_title}&rdquo;</strong><p>{tracking.milestone_due ? `It's due ${formatMonthDay(tracking.milestone_due)}. ` : ""}Twelve months of tracking open when it&apos;s marked complete, with the target spread across them as a starting plan.</p></div>
      <button type="button" className={styles.secondary} onClick={onOpenMilestones}>View milestone</button>
    </div> : null}

    {tracking.state === "open" ? <div className={styles.tableWrap}>
      <table>
        <thead><tr>
          <th scope="col">Month</th>
          {money ? <><th scope="col" className={styles.num}>Plan</th><th scope="col" className={styles.num}>Actual</th><th scope="col" className={styles.num}>To date<br /><small>plan · actual</small></th><th scope="col" className={styles.num}>Line of sight</th></> : null}
          <th scope="col" className={styles.num}>KPI{tracking.kpi_name ? <><br /><small title={tracking.kpi_name}>{tracking.kpi_name}</small></> : null}</th>
          <th scope="col">Delivery</th>
          <th scope="col">Finance</th>
        </tr></thead>
        <tbody>
          {months.map((month, index) => {
            const locked = !tracking.can_record || month.finance_status === "submitted" || month.finance_status === "validated";
            const future = month.month > thisMonth;
            const ytm = months.slice(0, index + 1);
            const save = (field: string, raw: string, current: string | null) => {
              const value = raw.trim() === "" ? null : raw.trim();
              if ((value ?? null) === (current === null || current === "" ? null : String(Number(current)))) return;
              void send(`${month.month}-${field}`, "PATCH", `/benefits/${month.month}`, { [field]: value === null ? (field === "plan" ? 0 : null) : Number(value) });
            };
            return <tr key={month.month} data-current={month.month === thisMonth} data-future={future} data-finance={month.finance_status}>
              <th scope="row">{formatMonth(month.month)}{month.month === thisMonth ? <em>This month</em> : null}</th>
              {money ? <>
                <td className={styles.num}><Amount label={`${formatMonth(month.month)} plan`} value={month.plan} disabled={locked} onSave={(value) => save("plan", value, month.plan)} /></td>
                <td className={styles.num}><Amount label={`${formatMonth(month.month)} actual`} value={month.has_actual === false ? "" : month.achieved} disabled={locked || future} placeholder={future ? "" : "Enter"} onSave={(value) => save("actual", value, month.has_actual === false ? null : month.achieved)} /></td>
                <td className={styles.num}><span className={styles.ytm}>{lakhs(sum(ytm.map((item) => item.plan)))}<span>{lakhs(sum(ytm.map((item) => item.achieved)))}</span></span></td>
                <td className={styles.num}><Amount label={`${formatMonth(month.month)} line of sight`} value={Number(month.line_of_sight) ? month.line_of_sight : ""} disabled={locked} onSave={(value) => save("line_of_sight", value, Number(month.line_of_sight) ? month.line_of_sight : null)} /></td>
              </> : null}
              <td className={styles.num}><Amount label={`${formatMonth(month.month)} KPI`} value={month.kpi_actual ?? ""} disabled={locked || future} step="any" onSave={(value) => save("kpi_actual", value, month.kpi_actual)} /></td>
              <td><select aria-label={`${formatMonth(month.month)} delivery status`} value={month.status} disabled={locked || future || Boolean(busy)} onChange={(event) => void send(`${month.month}-status`, "PATCH", `/benefits/${month.month}`, { status: event.target.value })} data-status={month.status}>{deliveryStates.map((state) => <option key={state.value} value={state.value}>{state.label}</option>)}</select></td>
              <td className={styles.finance}>
                <FinanceCell
                  month={month}
                  canRecord={tracking.can_record}
                  canValidate={tracking.can_validate}
                  busy={busy.startsWith(month.month)}
                  onSubmit={() => void send(`${month.month}-submit`, "POST", `/benefits/${month.month}/submit`)}
                  onValidate={() => void send(`${month.month}-review`, "POST", `/benefits/${month.month}/review`, { decision: "validate" })}
                  onChallenge={() => { setChallenging(month.month); setComment(""); }}
                />
                {challenging === month.month ? <form className={styles.challenge} onSubmit={(event) => { event.preventDefault(); void send(`${month.month}-review`, "POST", `/benefits/${month.month}/review`, { decision: "challenge", comment }).then((ok) => { if (ok) setChallenging(null); }); }}>
                  <label>What needs to change?<textarea rows={2} maxLength={1000} value={comment} onChange={(event) => setComment(event.target.value)} placeholder="Share the meter readings that support this figure." /></label>
                  <div><button type="submit" className={styles.danger} disabled={!comment.trim() || Boolean(busy)}>Challenge</button><button type="button" className={styles.secondary} onClick={() => setChallenging(null)}>Cancel</button></div>
                </form> : null}
              </td>
            </tr>;
          })}
        </tbody>
      </table>
    </div> : null}
  </section>;
}

function FinanceCell({ month, canRecord, canValidate, busy, onSubmit, onValidate, onChallenge }: { month: BenefitMonth; canRecord: boolean; canValidate: boolean; busy: boolean; onSubmit: () => void; onValidate: () => void; onChallenge: () => void }) {
  const status = month.finance_status ?? (month.finance_approved ? "validated" : "open");
  if (status === "validated") return <span className={styles.pill} data-tone="success"><ShieldCheck size={14} aria-hidden="true" />Validated</span>;
  if (status === "submitted") return <div className={styles.financeActions}>
    <span className={styles.pill} data-tone="info"><Clock3 size={14} aria-hidden="true" />With Finance</span>
    {canValidate ? <><button type="button" className={styles.small} disabled={busy} onClick={onValidate}><Check size={14} aria-hidden="true" />Validate</button><button type="button" className={styles.smallGhost} disabled={busy} onClick={onChallenge}><Undo2 size={14} aria-hidden="true" />Challenge</button></> : null}
  </div>;
  const hasActual = month.has_actual !== false;
  return <div className={styles.financeActions}>
    {status === "challenged" ? <span className={styles.pill} data-tone="warning" title={month.finance_comment}><AlertTriangle size={14} aria-hidden="true" />Challenged</span> : null}
    {canRecord ? <button type="button" className={styles.smallGhost} disabled={busy || !hasActual} title={hasActual ? undefined : "Record the actual first"} onClick={onSubmit}><Send size={14} aria-hidden="true" />{status === "challenged" ? "Send again" : "Send to Finance"}</button> : <span className={styles.muted}>Not sent</span>}
    {status === "challenged" && month.finance_comment ? <small className={styles.comment}>{month.finance_comment}</small> : null}
  </div>;
}

/** A number field that saves when you leave it. */
function Amount({ label, value, disabled, placeholder, step = "0.01", onSave }: { label: string; value: string; disabled: boolean; placeholder?: string; step?: string; onSave: (value: string) => void }) {
  const shown = value === "" ? "" : String(Number(value));
  return <input key={shown} className={styles.amount} type="number" inputMode="decimal" step={step} aria-label={label} defaultValue={shown} disabled={disabled} placeholder={placeholder} onBlur={(event) => onSave(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter") (event.target as HTMLInputElement).blur(); }} />;
}

function Tile({ label, value, note, tone }: { label: string; value: string; note?: string; tone?: "success" }) {
  return <div className={styles.tile} data-tone={tone}><small>{label}</small><strong>{value}</strong>{note ? <span>{note}</span> : null}</div>;
}

function sum(values: Array<string | number>) { return values.reduce<number>((total, value) => total + Number(value || 0), 0); }
function lakhs(value: string | number) { return `₹${Number(value).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} L`; }
function formatMonth(value: string) { return new Intl.DateTimeFormat("en-IN", { month: "short", year: "numeric" }).format(new Date(`${value}-01T00:00:00`)); }
function formatMonthDay(value: string) { return new Intl.DateTimeFormat("en-IN", { day: "numeric", month: "short", year: "numeric" }).format(new Date(`${value.slice(0, 10)}T00:00:00`)); }
