"use client";

import { Bell, Building2, FileClock, FolderKanban, Home, Lightbulb, ListFilter, LogOut, Menu, Pencil, PlusCircle, Settings2, UserRound, Users, X } from "lucide-react";
import { TenantLink as Link } from "@/components/app/tenant-link";
import { useTenantRouter as useRouter } from "@/lib/use-tenant-router";
import { useEffect, useRef, useState } from "react";
import { apiRequest, type SessionIdentity } from "@/lib/api";
import { ProfileAvatar } from "./profile-avatar";
import styles from "./app-menu.module.css";

type AppMenuProps = {
  session: SessionIdentity;
  active: "home" | "people" | "tenants" | "configuration" | "submit" | "ideas" | "projects" | "profile" | "notifications" | "audit";
};

export function AppMenu({ session, active }: AppMenuProps) {
  const router = useRouter();
  const closeButton = useRef<HTMLButtonElement>(null);
  const [open, setOpen] = useState(false);
  const [signingOut, setSigningOut] = useState(false);
  const [workspaces, setWorkspaces] = useState<Array<{ id: string; slug: string; name: string }>>([]);

  useEffect(() => {
    if (!open) return;
    if (!workspaces.length) {
      void apiRequest("/auth/workspaces")
        .then(async (response) => response.ok ? await response.json() as Array<{ id: string; slug: string; name: string }> : [])
        .then(setWorkspaces)
        .catch(() => undefined);
    }
    closeButton.current?.focus();
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    window.addEventListener("keydown", onKeyDown);
    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", onKeyDown);
    };
  }, [open, workspaces.length]);

  const signOut = async () => {
    setSigningOut(true);
    try {
      await apiRequest("/auth/logout", { method: "POST" });
    } finally {
      router.replace("/sign-in");
    }
  };

  return (
    <>
      <button className={styles.trigger} type="button" onClick={() => setOpen(true)} aria-label="Open application menu" aria-expanded={open} aria-controls="application-menu">
        <Menu aria-hidden="true" size={20} /><span>Menu</span>
      </button>
      <button className={styles.backdrop} type="button" data-open={open} aria-label="Close application menu" onClick={() => setOpen(false)} tabIndex={open ? 0 : -1} />
      <aside
        className={styles.drawer}
        id="application-menu"
        data-open={open}
        aria-hidden={!open}
        inert={!open}
      >
        <header><div><span>TRANSPIRE workspace</span><strong>{session.tenant.name}</strong></div><button ref={closeButton} type="button" onClick={() => setOpen(false)} aria-label="Close application menu"><X aria-hidden="true" size={20} /></button></header>
        <nav aria-label="Application navigation">
          <Link href="/home" data-active={active === "home"} onClick={() => setOpen(false)}><Home aria-hidden="true" size={18} /><span><strong>Home</strong><small>Your improvement workspace</small></span></Link>
          <Link href="/ideas/new/v2" data-active={active === "submit"} onClick={() => setOpen(false)}><PlusCircle aria-hidden="true" size={18} /><span><strong>Submit an idea</strong><small>Capture an improvement</small></span></Link>
          <Link href="/ideas" data-active={active === "ideas"} onClick={() => setOpen(false)}><ListFilter aria-hidden="true" size={18} /><span><strong>Idea Bank</strong><small>Explore shared ideas</small></span></Link>
          <Link href="/projects" data-active={active === "projects"} onClick={() => setOpen(false)}><FolderKanban aria-hidden="true" size={18} /><span><strong>Projects</strong><small>Track delivery and benefits</small></span></Link>
          <Link href="/notifications" data-active={active === "notifications"} onClick={() => setOpen(false)}><Bell aria-hidden="true" size={18} /><span><strong>Approval notifications</strong><small>Items needing attention</small></span></Link>
          {session.roles.includes("tenant_admin") ? <Link href="/admin/people" data-active={active === "people"} onClick={() => setOpen(false)}><Users aria-hidden="true" size={18} /><span><strong>People</strong><small>Members and invitations</small></span></Link> : null}
          {session.roles.includes("tenant_admin") ? <Link href="/admin/configuration" data-active={active === "configuration"} onClick={() => setOpen(false)}><Settings2 aria-hidden="true" size={18} /><span><strong>Configuration</strong><small>Organisation and workflow</small></span></Link> : null}
          {session.user.is_platform_admin ? <Link href="/admin/tenants" data-active={active === "tenants"} onClick={() => setOpen(false)}><Building2 aria-hidden="true" size={18} /><span><strong>Tenants</strong><small>Organisation lifecycle</small></span></Link> : null}
          <div className={styles.profileGroup} data-active={active === "profile"}>
            <div><UserRound aria-hidden="true" size={18} /><span><strong>Profile</strong><small>Your identity and preferences</small></span></div>
            <div>
              <Link href="/profile" onClick={() => setOpen(false)}><Pencil aria-hidden="true" size={15} />Edit profile</Link>
              <Link href="/profile#audit-log" onClick={() => setOpen(false)}><FileClock aria-hidden="true" size={15} />Audit log</Link>
              <button type="button" onClick={signOut} disabled={signingOut}><LogOut aria-hidden="true" size={15} />{signingOut ? "Signing out" : "Sign out"}</button>
            </div>
          </div>
        </nav>
        <footer>
          {workspaces.length > 1 ? <div className={styles.workspaceSwitch}><span>Switch organisation</span>{workspaces.map((workspace) => workspace.id === session.tenant.id ? <strong key={workspace.id}>{workspace.name}<small>Current</small></strong> : <a key={workspace.id} href={`/t/${encodeURIComponent(workspace.slug)}/sign-in`}>{workspace.name}<small>Use its sign-in policy</small></a>)}</div> : null}
          <div className={styles.person}><ProfileAvatar name={session.user.display_name} /><p><strong>{session.user.display_name}</strong><small>{session.user.email}</small></p></div>
          <p className={styles.motto}><Lightbulb aria-hidden="true" size={15} /> Ideate. Transform. Inspire.</p>
        </footer>
      </aside>
    </>
  );
}
