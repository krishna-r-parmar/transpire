"use client";

import { AlertTriangle, CheckCircle2, CloudDownload, KeyRound, Pencil, PlugZap, Server, ShieldCheck } from "lucide-react";
import { FormEvent, useCallback, useEffect, useState } from "react";
import { SidePanel } from "@/components/admin/side-panel";
import { StatusPill } from "@/components/ui/workspace";
import { apiRequest } from "@/lib/api";
import shared from "../admin.module.css";
import styles from "./directory.module.css";

type Source = { enabled: boolean; host: string; port: number; username: string; auth_method: "password" | "private_key"; has_secret: boolean; remote_path: string; trusted_fingerprint: string | null; presented_fingerprint: string | null; key_awaiting_trust: boolean; last_run_at: string | null; last_status: string | null; last_message: string | null };
type ActionResult = { ok: boolean; message: string; source: Source };
type Form = { enabled: boolean; host: string; port: number; username: string; auth_method: "password" | "private_key"; secret: string; remote_path: string };

const stamp = new Intl.DateTimeFormat("en-IN", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" });

async function detail(response: Response, fallback: string) {
  const payload = await response.json().catch(() => null) as { detail?: string | Array<{ msg: string }> } | null;
  return Array.isArray(payload?.detail) ? payload.detail[0]?.msg ?? fallback : payload?.detail ?? fallback;
}

/** The workspace's SFTP server for the daily HR report: connection, trust, and ad-hoc runs. */
export function SftpCard({ isOwner, onRun }: { isOwner: boolean; onRun: () => Promise<void> }) {
  const [source, setSource] = useState<Source | null>(null);
  const [form, setForm] = useState<Form | null>(null);
  const [busy, setBusy] = useState("");
  const [result, setResult] = useState<{ ok: boolean; message: string } | null>(null);

  const load = useCallback(async () => {
    const response = await apiRequest("/admin/directory/sftp").catch(() => null);
    if (response?.ok) setSource(await response.json() as Source);
  }, []);
  useEffect(() => { const timer = window.setTimeout(() => void load(), 0); return () => window.clearTimeout(timer); }, [load]);

  const act = async (path: string, label: string, body?: object) => {
    setBusy(label); setResult(null);
    try {
      const response = await apiRequest(`/admin/directory/sftp/${path}`, { method: "POST", body: body ? JSON.stringify(body) : undefined });
      if (!response.ok) { setResult({ ok: false, message: await detail(response, "That did not work.") }); return; }
      const payload = await response.json() as ActionResult | Source;
      if ("source" in payload) { setSource(payload.source); setResult({ ok: payload.ok, message: payload.message }); }
      else { setSource(payload); setResult({ ok: true, message: "Key trusted. TRANSPIRE will only send credentials to this server." }); }
      if (path === "fetch") await onRun();
    } catch {
      setResult({ ok: false, message: "The SFTP service is temporarily unavailable." });
    } finally { setBusy(""); }
  };

  const save = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!form) return;
    setBusy("save"); setResult(null);
    try {
      const response = await apiRequest("/admin/directory/sftp", { method: "PUT", body: JSON.stringify({ ...form, secret: form.secret || null }) });
      if (!response.ok) { setResult({ ok: false, message: await detail(response, "The connection could not be saved.") }); return; }
      const saved = await response.json() as Source;
      setSource(saved); setForm(null);
      setResult({ ok: true, message: saved.trusted_fingerprint ? "Connection saved." : "Connection saved. Next, check the server and trust its key." });
    } finally { setBusy(""); }
  };

  if (!source) return <section className={styles.card}><h2><Server size={17} aria-hidden="true" />HR file from SFTP</h2><p>Loading the connection</p></section>;
  const configured = Boolean(source.host);
  const ready = configured && Boolean(source.trusted_fingerprint) && source.has_secret;

  return <section className={styles.card} aria-labelledby="sftp-title">
    <div className={styles.cardHead}>
      <h2 id="sftp-title"><Server size={17} aria-hidden="true" />HR file from SFTP</h2>
      {configured ? source.enabled ? <StatusPill tone="success">Daily fetch on</StatusPill> : <StatusPill>Daily fetch off</StatusPill> : null}
    </div>
    {configured ? <dl className={styles.connection}>
      <div><dt>Server</dt><dd><code>{source.host}:{source.port}</code></dd></div>
      <div><dt>Path</dt><dd><code>{source.remote_path || "(home folder)"}</code></dd></div>
      <div><dt>Sign-in</dt><dd>{source.username || "—"} · {source.auth_method === "password" ? "password" : "private key"}{source.has_secret ? "" : " (not set)"}</dd></div>
      <div><dt>Server key</dt><dd>{source.trusted_fingerprint ? <span className={styles.trusted}><ShieldCheck size={14} aria-hidden="true" /><code>{source.trusted_fingerprint}</code></span> : "Not trusted yet"}</dd></div>
      {source.last_run_at ? <div><dt>Last run</dt><dd>{stamp.format(new Date(source.last_run_at))} · {source.last_message}</dd></div> : null}
    </dl> : <p>Not set up. {isOwner ? "Add the server address, sign-in and path your HR team gave you." : "A Workspace Owner can set it up."} TRANSPIRE only reads files there; it never changes anything.</p>}

    {source.key_awaiting_trust && source.presented_fingerprint ? <div className={styles.keyCheck} role="status">
      <AlertTriangle size={16} aria-hidden="true" />
      <div>
        <strong>{source.trusted_fingerprint ? "The server\u2019s key is different from the trusted one." : "Confirm the server\u2019s identity."}</strong>
        <p>The server presented <code>{source.presented_fingerprint}</code>. Ask the customer&apos;s IT team to confirm this fingerprint before you trust it. Credentials are never sent to an untrusted server.</p>
        {isOwner ? <button type="button" className={styles.secondary} disabled={busy !== ""} onClick={() => void act("trust-key", "trust", { fingerprint: source.presented_fingerprint })}><ShieldCheck size={15} aria-hidden="true" />Trust this key</button> : null}
      </div>
    </div> : null}

    {result ? <p className={styles.result} data-ok={result.ok} role="status">{result.ok ? <CheckCircle2 size={15} aria-hidden="true" /> : <AlertTriangle size={15} aria-hidden="true" />}{result.message}</p> : null}

    <div className={styles.cardActions}>
      {ready ? <button type="button" className={shared.primary} disabled={busy !== ""} onClick={() => void act("fetch", "fetch")}><CloudDownload size={16} aria-hidden="true" />{busy === "fetch" ? "Fetching" : "Fetch now"}</button> : null}
      {ready ? <button type="button" className={styles.secondary} disabled={busy !== ""} onClick={() => void act("test", "test")}><PlugZap size={15} aria-hidden="true" />{busy === "test" ? "Testing" : "Test connection"}</button> : null}
      {isOwner && configured ? <button type="button" className={styles.secondary} disabled={busy !== ""} onClick={() => void act("check-key", "check")}><KeyRound size={15} aria-hidden="true" />{busy === "check" ? "Checking" : "Check server key"}</button> : null}
      {isOwner ? <button type="button" className={styles.secondary} disabled={busy !== ""} onClick={() => setForm({ enabled: source.enabled, host: source.host, port: source.port, username: source.username, auth_method: source.auth_method, secret: "", remote_path: source.remote_path })}><Pencil size={15} aria-hidden="true" />{configured ? "Edit connection" : "Set up connection"}</button> : null}
    </div>

    <SidePanel open={Boolean(form)} onClose={() => setForm(null)} title="SFTP connection" description="Where TRANSPIRE fetches this workspace's HR report. Changing the server means checking and trusting its key again.">
      {form ? <form className={shared.form} onSubmit={(event) => void save(event)}>
        <div className={styles.twoCol}>
          <div className={shared.field}><label htmlFor="sftp-host">Server IP or host name</label><input id="sftp-host" required value={form.host} onChange={(event) => setForm({ ...form, host: event.target.value })} placeholder="203.0.113.10" autoComplete="off" /></div>
          <div className={shared.field}><label htmlFor="sftp-port">Port</label><input id="sftp-port" type="number" min={1} max={65535} required value={form.port} onChange={(event) => setForm({ ...form, port: Number(event.target.value) })} /></div>
        </div>
        <div className={shared.field}><label htmlFor="sftp-path">Path</label><input id="sftp-path" value={form.remote_path} onChange={(event) => setForm({ ...form, remote_path: event.target.value })} placeholder="/outbound/hrms" autoComplete="off" /><small className={styles.sub}>A folder (the newest .xlsx or .csv is used) or one file.</small></div>
        <div className={shared.field}><label htmlFor="sftp-user">Username</label><input id="sftp-user" required value={form.username} onChange={(event) => setForm({ ...form, username: event.target.value })} autoComplete="off" /></div>
        <fieldset className={styles.authChoice}>
          <legend>Sign in with</legend>
          {(["password", "private_key"] as const).map((method) => <label key={method} data-checked={form.auth_method === method}><input type="radio" name="auth" checked={form.auth_method === method} onChange={() => setForm({ ...form, auth_method: method, secret: "" })} />{method === "password" ? "Password" : "Private key"}</label>)}
        </fieldset>
        <div className={shared.field}>
          <label htmlFor="sftp-secret">{form.auth_method === "password" ? "Password" : "Private key (OpenSSH or PEM)"}</label>
          {form.auth_method === "password"
            ? <input id="sftp-secret" type="password" value={form.secret} onChange={(event) => setForm({ ...form, secret: event.target.value })} placeholder={source.has_secret && source.auth_method === "password" ? "Stored. Leave empty to keep it" : ""} autoComplete="new-password" />
            : <textarea id="sftp-secret" className={styles.keyInput} value={form.secret} onChange={(event) => setForm({ ...form, secret: event.target.value })} placeholder={source.has_secret && source.auth_method === "private_key" ? "Stored. Leave empty to keep it" : "-----BEGIN OPENSSH PRIVATE KEY-----"} spellCheck={false} />}
          <small className={styles.sub}>Encrypted at rest and never shown again.</small>
        </div>
        <label className={styles.toggle}><input type="checkbox" checked={form.enabled} onChange={(event) => setForm({ ...form, enabled: event.target.checked })} /><span><strong>Fetch automatically every day</strong><small>Turns on only after the server&apos;s key is trusted. You can always use Fetch now.</small></span></label>
        <button type="submit" className={shared.primary} disabled={busy !== ""}>{busy === "save" ? "Saving" : "Save connection"}</button>
      </form> : null}
    </SidePanel>
  </section>;
}
