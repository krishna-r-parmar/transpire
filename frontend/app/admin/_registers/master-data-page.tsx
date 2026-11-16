"use client";

import { Pencil, Plus, Power } from "lucide-react";
import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { AdminShell } from "@/components/admin/admin-shell";
import type { AdminRoute } from "@/components/admin/admin-nav";
import { SidePanel, StatusFilter, type StatusFilterValue } from "@/components/admin/side-panel";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { DismissibleNotice } from "@/components/ui/dismissible-notice";
import { SearchField } from "@/components/ui/search-field";
import { SelectField } from "@/components/ui/select-field";
import { StatusPill } from "@/components/ui/workspace";
import { apiRequest } from "@/lib/api";
import { useAdminSession } from "@/lib/use-admin-session";
import { useTenantRouter as useRouter } from "@/lib/use-tenant-router";
import shared from "../admin.module.css";
import styles from "@/components/admin/admin-register.module.css";

export type Kind = "site" | "department" | "category" | "subcategory" | "process_area";
export type Item = { id: string; kind: Kind; code: string; name: string; parent_id: string | null; site_ids: string[]; applies_to_all_sites: boolean; is_active: boolean; sort_order: number };
type Registers = Record<Kind, Item[]>;

const labels: Record<Kind, { singular: string; plural: string }> = {
  site: { singular: "Site", plural: "Sites" },
  department: { singular: "Department", plural: "Departments" },
  category: { singular: "Category", plural: "Categories" },
  subcategory: { singular: "Subcategory", plural: "Subcategories" },
  process_area: { singular: "Process area", plural: "Process areas" },
};

type PageConfig = { route: AdminRoute; description: string; empty: string; related: Kind[] };
const pages: Record<"site" | "department" | "category" | "process_area", PageConfig> = {
  site: { route: "sites", description: "Locations people choose when they submit an idea.", empty: "Add your first site so departments and ideas can be placed.", related: ["department"] },
  department: { route: "departments", description: "Teams within your sites. Each department can be available at every site or only some.", empty: "Add sites first, then the departments that work at them.", related: ["site"] },
  category: { route: "categories", description: "How ideas are classified. Each category holds its own subcategories.", empty: "Add the first category to start classifying ideas.", related: ["subcategory"] },
  process_area: { route: "process_areas", description: "The parts of your operation an idea improves.", empty: "Add the first process area people can choose.", related: [] },
};

const empty = (): Registers => ({ site: [], department: [], category: [], subcategory: [], process_area: [] });
const slugify = (value: string) => value.toLocaleLowerCase().trim().replace(/[^a-z0-9]+/g, "_").replace(/^_|_$/g, "");
const errorDetail = async (response: Response, fallback: string) => ((await response.json().catch(() => null)) as { detail?: string } | null)?.detail ?? fallback;

type Editor = { mode: "create" } | { mode: "edit"; item: Item } | { mode: "children"; item: Item } | null;

export function MasterDataPage({ kind }: { kind: keyof typeof pages }) {
  const router = useRouter();
  const { session, loading } = useAdminSession();
  const config = pages[kind];
  const [registers, setRegisters] = useState<Registers>(empty);
  const [loaded, setLoaded] = useState(false);
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState<StatusFilterValue>("active");
  const [siteFilter, setSiteFilter] = useState("");
  const [editor, setEditor] = useState<Editor>(null);
  const [deactivating, setDeactivating] = useState<Item | null>(null);
  const [busy, setBusy] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  const flash = (text: string, isError = false) => { setMessage(isError ? "" : text); setError(isError ? text : ""); };

  const load = useCallback(async () => {
    const kinds = [kind, ...config.related];
    try {
      const responses = await Promise.all(kinds.map((entry) => apiRequest(`/admin/configuration/master-data/${entry}`)));
      if (responses.some((response) => response.status === 401)) return router.replace("/sign-in");
      if (responses.some((response) => response.status === 403)) return router.replace("/home");
      const next = empty();
      await Promise.all(kinds.map(async (entry, index) => { if (responses[index].ok) next[entry] = await responses[index].json() as Item[]; }));
      setRegisters(next);
      if (responses.some((response) => !response.ok)) setError(`Some ${labels[kind].plural.toLowerCase()} could not be loaded. Retry in a moment.`);
    } catch { setError("TRANSPIRE could not reach the configuration service. Check the connection, then retry."); }
    finally { setLoaded(true); }
  }, [config.related, kind, router]);

  useEffect(() => {
    if (!session) return;
    const timer = window.setTimeout(() => void load(), 0);
    return () => window.clearTimeout(timer);
  }, [load, session]);

  const items = registers[kind];
  const sites = registers.site;
  const siteName = useMemo(() => new Map(sites.map((site) => [site.id, site.name])), [sites]);

  const scopeLabel = (item: Item) => item.applies_to_all_sites ? "All sites" : item.site_ids.map((id) => siteName.get(id) ?? "Unknown site").join(", ") || "No sites";
  const departmentsAtSite = (site: Item) => registers.department.filter((department) => department.is_active && (department.applies_to_all_sites || department.site_ids.includes(site.id))).length;
  const children = (item: Item) => registers.subcategory.filter((child) => child.parent_id === item.id);

  const counts = { active: items.filter((item) => item.is_active).length, inactive: items.filter((item) => !item.is_active).length, all: items.length };
  const visible = useMemo(() => {
    const term = query.trim().toLocaleLowerCase();
    return items.filter((item) => (status === "all" || item.is_active === (status === "active"))
      && (!siteFilter || item.applies_to_all_sites || item.site_ids.includes(siteFilter))
      && (!term || `${item.name} ${item.code}`.toLocaleLowerCase().includes(term)));
  }, [items, query, siteFilter, status]);

  const save = async (event: FormEvent<HTMLFormElement>, target: Kind, existing?: Item, parentId?: string) => {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(form);
    const scope = target === "department" ? { site_ids: data.getAll("site_ids"), applies_to_all_sites: data.get("applies_to_all_sites") === "true" } : {};
    setBusy("save"); flash("");
    try {
      const response = existing
        ? await apiRequest(`/admin/configuration/master-data/${target}/${existing.id}`, { method: "PATCH", body: JSON.stringify({ name: data.get("name"), ...scope }) })
        : await apiRequest(`/admin/configuration/master-data/${target}`, { method: "POST", body: JSON.stringify({ name: data.get("name"), code: data.get("code"), parent_id: parentId ?? null, site_ids: [], applies_to_all_sites: false, ...scope }) });
      if (!response.ok) return flash(await errorDetail(response, `${labels[target].singular} could not be saved.`), true);
      flash(`${labels[target].singular} ${existing ? "updated" : "added"}.`);
      if (target === kind) setEditor(null); else form.reset();
      await load();
    } catch { flash("Configuration is temporarily unavailable.", true); }
    finally { setBusy(""); }
  };

  const setActive = async (item: Item, isActive: boolean) => {
    setBusy(`toggle:${item.id}`); flash("");
    try {
      const response = await apiRequest(`/admin/configuration/master-data/${item.kind}/${item.id}`, { method: "PATCH", body: JSON.stringify({ is_active: isActive }) });
      if (!response.ok) return flash(await errorDetail(response, "Status could not be changed."), true);
      flash(`${labels[item.kind].singular} ${isActive ? "reactivated" : "deactivated"}.`);
      await load();
    } catch { flash("Configuration is temporarily unavailable.", true); }
    finally { setBusy(""); }
  };

  if (loading || !session) return <main className={shared.loading}>Loading administration</main>;

  const singular = labels[kind].singular;
  return <AdminShell session={session} active={config.route} title={labels[kind].plural} description={config.description}
    actions={<button type="button" className={shared.primary} onClick={() => setEditor({ mode: "create" })} disabled={kind === "department" && !sites.some((site) => site.is_active)}><Plus size={16} aria-hidden="true" />Add {singular.toLowerCase()}</button>}>
    {message || error ? <div className={styles.notices}>
      {message ? <DismissibleNotice onDismiss={() => setMessage("")}>{message}</DismissibleNotice> : null}
      {error ? <DismissibleNotice tone="error" onDismiss={() => setError("")}>{error}</DismissibleNotice> : null}
    </div> : null}

    <section className={styles.surface} aria-label={`${labels[kind].plural} register`}>
      <div className={styles.toolbar}>
        <SearchField id={`${kind}-search`} label={`Search ${labels[kind].plural.toLowerCase()}`} value={query} onChange={setQuery} placeholder="Search name or code" resultCount={visible.length} />
        <div className={styles.toolbarFilters}>
          {kind === "department" ? <SelectField id="department-site-filter" name="site_filter" label="Site" value={siteFilter} onChange={setSiteFilter} options={[{ value: "", label: "All sites" }, ...sites.map((site) => ({ value: site.id, label: site.name }))]} /> : null}
          <StatusFilter value={status} onChange={setStatus} counts={counts} />
        </div>
      </div>
      {!loaded ? <p className={styles.empty}>Loading {labels[kind].plural.toLowerCase()}</p>
        : !items.length ? <div className={styles.empty}><p>{config.empty}</p></div>
        : <div className={styles.tableWrap}><table className={styles.table}>
          <thead><tr>
            <th scope="col">Name</th><th scope="col">Code</th>
            {kind === "site" ? <th scope="col">Departments</th> : null}
            {kind === "department" ? <th scope="col">Available at</th> : null}
            {kind === "category" ? <th scope="col">Subcategories</th> : null}
            <th scope="col">Status</th><th scope="col"><span className={shared.srOnly}>Actions</span></th>
          </tr></thead>
          <tbody>{visible.map((item) => <tr key={item.id} data-inactive={!item.is_active}>
            <td><strong>{item.name}</strong></td>
            <td><span className={styles.code}>{item.code}</span></td>
            {kind === "site" ? <td className={styles.numeric}>{departmentsAtSite(item)}</td> : null}
            {kind === "department" ? <td className={styles.scope}>{scopeLabel(item)}</td> : null}
            {kind === "category" ? <td className={styles.numeric}>{children(item).filter((child) => child.is_active).length}</td> : null}
            <td>{item.is_active ? <StatusPill tone="success">Active</StatusPill> : <StatusPill>Inactive</StatusPill>}</td>
            <td><div className={styles.actions}>
              {kind === "category" ? <button type="button" onClick={() => setEditor({ mode: "children", item })}>Subcategories</button> : null}
              <button type="button" onClick={() => setEditor({ mode: "edit", item })}><Pencil size={14} aria-hidden="true" />Edit</button>
              {item.is_active
                ? <button type="button" data-tone="danger" disabled={busy !== ""} onClick={() => setDeactivating(item)}><Power size={14} aria-hidden="true" />Deactivate</button>
                : <button type="button" disabled={busy !== ""} onClick={() => void setActive(item, true)}><Power size={14} aria-hidden="true" />Reactivate</button>}
            </div></td>
          </tr>)}</tbody>
        </table>
        {!visible.length ? <p className={styles.empty}>No {labels[kind].plural.toLowerCase()} match these filters.</p> : null}
        </div>}
      {loaded && items.length ? <p className={styles.footerNote}>Deactivated records stay on existing ideas but can no longer be chosen.</p> : null}
    </section>

    <SidePanel open={editor?.mode === "create" || editor?.mode === "edit"} onClose={() => setEditor(null)}
      title={editor?.mode === "edit" ? `Edit ${editor.item.name}` : `Add ${singular.toLowerCase()}`}
      description={editor?.mode === "edit" ? "The code stays fixed so existing ideas and reports keep matching." : "Codes are permanent identifiers used in reports and exports."}>
      {editor?.mode === "create" || editor?.mode === "edit"
        ? <RecordForm key={editor.mode === "edit" ? editor.item.id : "new"} kind={kind} item={editor.mode === "edit" ? editor.item : undefined} sites={sites.filter((site) => site.is_active)} busy={busy === "save"} onCancel={() => setEditor(null)} onSubmit={(event, item) => void save(event, kind, item)} />
        : null}
    </SidePanel>

    <SidePanel open={editor?.mode === "children"} onClose={() => setEditor(null)} title={editor?.mode === "children" ? `${editor.item.name} subcategories` : "Subcategories"} description="Subcategories narrow an idea's classification within this category.">
      {editor?.mode === "children" ? <>
        {children(editor.item).length ? <ul className={styles.childList}>{children(editor.item).map((child) => <li key={child.id} data-inactive={!child.is_active}>
          <span><strong>{child.name}</strong><span className={styles.code}>{child.code}</span></span>
          <div className={styles.actions}><button type="button" data-tone={child.is_active ? "danger" : undefined} disabled={busy !== ""} onClick={() => void setActive(child, !child.is_active)}>{child.is_active ? "Deactivate" : "Reactivate"}</button></div>
        </li>)}</ul> : <p className={shared.muted}>No subcategories yet.</p>}
        <p className={styles.subheading}>Add subcategory</p>
        <RecordForm kind="subcategory" sites={[]} busy={busy === "save"} onSubmit={(event) => void save(event, "subcategory", undefined, editor.item.id)} />
      </> : null}
    </SidePanel>

    <ConfirmDialog open={Boolean(deactivating)} title={`Deactivate ${deactivating?.name ?? ""}?`} description="It stays on existing ideas and reports, but people can no longer choose it. You can reactivate it later." confirmLabel="Deactivate" busyLabel="Deactivating" busy={busy.startsWith("toggle")} onClose={() => setDeactivating(null)} onConfirm={async () => { if (deactivating) await setActive(deactivating, false); setDeactivating(null); }} />
  </AdminShell>;
}

function RecordForm({ kind, item, sites, busy, onSubmit, onCancel }: { kind: Kind; item?: Item; sites: Item[]; busy: boolean; onSubmit: (event: FormEvent<HTMLFormElement>, item?: Item) => void; onCancel?: () => void }) {
  const [allSites, setAllSites] = useState(item?.applies_to_all_sites ?? false);
  const [siteIds, setSiteIds] = useState<string[]>(item?.site_ids ?? []);
  const singular = labels[kind].singular;
  const invalidScope = kind === "department" && !allSites && siteIds.length === 0;
  return <form className={styles.panelForm} onSubmit={(event) => onSubmit(event, item)}>
    <div className={shared.field}><label htmlFor={`${kind}-name`}>{singular} name</label><input id={`${kind}-name`} name="name" required minLength={2} defaultValue={item?.name}
      onBlur={item ? undefined : (event) => { const code = event.currentTarget.form?.elements.namedItem("code") as HTMLInputElement | null; if (code && !code.value) code.value = slugify(event.currentTarget.value); }} /></div>
    {item
      ? <div className={styles.readonly}><span>Code</span><code className={styles.code}>{item.code}</code></div>
      : <div className={shared.field}><label htmlFor={`${kind}-code`}>Code</label><input id={`${kind}-code`} name="code" required minLength={2} pattern="[a-z0-9]+(?:_[a-z0-9]+)*" placeholder="e.g. quality_assurance" /><small>Lowercase letters, numbers and underscores. It cannot be changed later.</small></div>}
    {kind === "department" ? <fieldset className={styles.siteScope}>
      <legend>Available at</legend>
      <label data-selected={allSites}><input type="checkbox" name="applies_to_all_sites" value="true" checked={allSites} onChange={(event) => setAllSites(event.target.checked)} />All sites, including future ones</label>
      {!allSites ? sites.map((site) => <label key={site.id} data-selected={siteIds.includes(site.id)}><input type="checkbox" name="site_ids" value={site.id} checked={siteIds.includes(site.id)} onChange={(event) => setSiteIds((current) => event.target.checked ? [...current, site.id] : current.filter((id) => id !== site.id))} />{site.name}</label>) : null}
    </fieldset> : null}
    <div className={styles.panelFooter}>
      {onCancel ? <button type="button" className={styles.secondary} onClick={onCancel}>Cancel</button> : null}
      <button type="submit" className={shared.primary} disabled={busy || invalidScope}>{busy ? "Saving" : item ? "Save changes" : `Add ${singular.toLowerCase()}`}</button>
    </div>
  </form>;
}
