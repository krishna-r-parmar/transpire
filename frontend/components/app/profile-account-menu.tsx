"use client";

import { Building2, ChevronDown, FileClock, LogOut, Pencil } from "lucide-react";
import { TenantLink as Link } from "@/components/app/tenant-link";
import { useTenantRouter as useRouter } from "@/lib/use-tenant-router";
import { useEffect, useRef, useState } from "react";
import { apiRequest, type SessionIdentity } from "@/lib/api";
import { ProfileAvatar } from "./profile-avatar";
import styles from "./profile-account-menu.module.css";

export function ProfileAccountMenu({ session, active }: { session: SessionIdentity; active: boolean }) {
  const router = useRouter();
  const root = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const editLink = useRef<HTMLAnchorElement>(null);
  const [open, setOpen] = useState(false);
  const [signingOut, setSigningOut] = useState(false);
  const [displayName, setDisplayName] = useState(session.user.display_name);
  const [workspaces, setWorkspaces] = useState<Array<{ id: string; slug: string; name: string }>>([]);

  useEffect(() => {
    const updateName = (event: Event) => setDisplayName((event as CustomEvent<{ displayName: string }>).detail.displayName);
    window.addEventListener("transpire:profile-updated", updateName);
    return () => window.removeEventListener("transpire:profile-updated", updateName);
  }, []);

  useEffect(() => {
    if (!open) return;
    if (!workspaces.length) {
      void apiRequest("/auth/workspaces")
        .then(async (response) => response.ok ? await response.json() as Array<{ id: string; slug: string; name: string }> : [])
        .then(setWorkspaces)
        .catch(() => undefined);
    }
    editLink.current?.focus();
    const close = (event: PointerEvent) => { if (!root.current?.contains(event.target as Node)) setOpen(false); };
    const escape = (event: KeyboardEvent) => { if (event.key === "Escape") { setOpen(false); trigger.current?.focus(); } };
    document.addEventListener("pointerdown", close);
    window.addEventListener("keydown", escape);
    return () => { document.removeEventListener("pointerdown", close); window.removeEventListener("keydown", escape); };
  }, [open, workspaces.length]);

  const signOut = async () => {
    setSigningOut(true);
    try { await apiRequest("/auth/logout", { method: "POST" }); }
    finally { router.replace("/sign-in"); }
  };

  return <div className={styles.account} ref={root}>
    <button ref={trigger} className={styles.trigger} type="button" data-active={active} aria-haspopup="menu" aria-expanded={open} onClick={() => setOpen((current) => !current)}>
      <ProfileAvatar name={displayName} />
      <span><strong>{displayName}</strong><small>{session.user.email}</small></span>
      <ChevronDown aria-hidden="true" size={15} />
    </button>
    <div className={styles.menu} role="menu" data-open={open}>
      <div><ProfileAvatar name={displayName} /><p><strong>{displayName}</strong><small>{session.user.email}</small></p></div>
      <Link ref={editLink} href="/profile" role="menuitem" onClick={() => setOpen(false)}><Pencil aria-hidden="true" size={15} /><span><strong>Edit profile</strong><small>Photo, name, and preferences</small></span></Link>
      <Link href="/profile#audit-log" role="menuitem" onClick={() => setOpen(false)}><FileClock aria-hidden="true" size={15} /><span><strong>Audit log</strong><small>{session.roles.includes("tenant_admin") ? "Tenant activity history" : "Your activity history"}</small></span></Link>
      {workspaces.length > 1 ? <div className={styles.workspaces}><span><Building2 size={14} />Switch organisation</span>{workspaces.map((workspace) => workspace.id === session.tenant.id ? <strong key={workspace.id}>{workspace.name}<small>Current workspace</small></strong> : <a key={workspace.id} href={`/t/${encodeURIComponent(workspace.slug)}/sign-in`}>{workspace.name}<small>Continue through its sign-in policy</small></a>)}</div> : null}
      <button type="button" role="menuitem" onClick={() => void signOut()} disabled={signingOut}><LogOut aria-hidden="true" size={15} /><span><strong>{signingOut ? "Signing out" : "Sign out"}</strong><small>End this TRANSPIRE session</small></span></button>
    </div>
  </div>;
}
