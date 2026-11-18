"use client";

import { ArrowLeft, Bell, ChevronsUpDown, Compass, FileClock, FolderKanban, Home, Inbox, ListFilter, LogOut, Menu, Moon, PanelLeftClose, PanelLeftOpen, Pencil, Plus, Settings2, Sun, X } from "lucide-react";
import Image from "next/image";
import { BetaTag } from "@/components/ui/beta-tag";
import { useEffect, useRef, useState, useSyncExternalStore, type ReactNode } from "react";
import { TenantLink as Link } from "@/components/app/tenant-link";
import { useTenantRouter as useRouter } from "@/lib/use-tenant-router";
import { apiRequest, type SessionIdentity } from "@/lib/api";
import { adminHome, isAdminRoute, visibleAdminGroups, type AdminRoute } from "@/components/admin/admin-nav";
import { canContribute, isWorkspaceAdmin } from "@/lib/roles";
import { GuidedTour, startTour, useTour } from "@/components/ui/guided-tour";
import { platformTourSteps, PLATFORM_TOUR_VERSION } from "./platform-tour";
import { useApprovalCount } from "./use-approval-count";
import { ProfileAvatar } from "./profile-avatar";
import { setTheme, useTheme } from "@/lib/theme";
import styles from "./app-sidebar.module.css";

export type AppRoute = "home" | "submit" | "ideas" | "projects" | "profile" | "notifications" | AdminRoute;

type Workspace = { id: string; slug: string; name: string };

const sidebarEvent = "transpire-sidebar-change";

function subscribe(callback: () => void) {
  window.addEventListener(sidebarEvent, callback);
  return () => window.removeEventListener(sidebarEvent, callback);
}

const getCollapsed = () => document.documentElement.dataset.sidebar === "collapsed";

export function AppSidebar({ session, active }: { session: SessionIdentity; active: AppRoute }) {
  const collapsed = useSyncExternalStore(subscribe, getCollapsed, () => false);
  const approvalCount = useApprovalCount();
  const [drawerOpen, setDrawerOpen] = useState(false);
  const closeButton = useRef<HTMLButtonElement>(null);
  const adminMode = isAdminRoute(active);
  const adminHref = adminHome(session);
  // The submit form runs its own tour, so the platform tour never opens on top of it.
  const tour = useTour("platform", PLATFORM_TOUR_VERSION, !adminMode && active !== "submit");

  useEffect(() => {
    if (!drawerOpen) return;
    closeButton.current?.focus();
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const onKeyDown = (event: KeyboardEvent) => { if (event.key === "Escape") setDrawerOpen(false); };
    window.addEventListener("keydown", onKeyDown);
    return () => { document.body.style.overflow = previousOverflow; window.removeEventListener("keydown", onKeyDown); };
  }, [drawerOpen]);

  const toggleCollapsed = () => {
    const next = collapsed ? "expanded" : "collapsed";
    document.documentElement.dataset.sidebar = next;
    try { window.localStorage.setItem("transpire-sidebar", next); } catch { /* The choice still applies to this page. */ }
    window.dispatchEvent(new Event(sidebarEvent));
  };

  const badge = approvalCount ? <span className={styles.badge} aria-hidden="true">{approvalCount > 99 ? "99+" : approvalCount}</span> : null;

  return <>
    <div className={styles.mobileBar}>
      <button type="button" className={styles.iconButton} onClick={() => setDrawerOpen(true)} aria-label="Open navigation" aria-expanded={drawerOpen} aria-controls="app-sidebar"><Menu size={20} aria-hidden="true" /></button>
      <Link className={styles.mobileLogo} href="/home" aria-label="TRANSPIRE home"><Image src="/brand/transpire-logo.png" alt="TRANSPIRE" width={1400} height={371} priority /><BetaTag /></Link>
      <Link className={styles.iconButton} href="/notifications" aria-label={approvalCount ? `Inbox, ${approvalCount} need your action` : "Inbox"}><Bell size={19} aria-hidden="true" />{badge}</Link>
    </div>
    <button type="button" className={styles.backdrop} data-open={drawerOpen} onClick={() => setDrawerOpen(false)} aria-label="Close navigation" tabIndex={drawerOpen ? 0 : -1} />

    <aside className={styles.sidebar} id="app-sidebar" data-open={drawerOpen} aria-label="Application" onClick={(event) => { if ((event.target as HTMLElement).closest("a")) setDrawerOpen(false); }}>
      <div className={styles.top}>
        <Link className={styles.logo} href="/home" aria-label="TRANSPIRE home">
          <Image className={styles.logoFull} src="/brand/transpire-logo.png" alt="" width={1400} height={371} priority />
          <Image className={styles.logoMark} src="/brand/transpire-icon-192.png" alt="" width={192} height={192} />
          <BetaTag className={styles.logoBeta} />
        </Link>
        <button type="button" className={`${styles.iconButton} ${styles.collapse}`} onClick={toggleCollapsed} aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"} title={collapsed ? "Expand sidebar" : "Collapse sidebar"}>
          {collapsed ? <PanelLeftOpen size={18} aria-hidden="true" /> : <PanelLeftClose size={18} aria-hidden="true" />}
        </button>
        <button ref={closeButton} type="button" className={`${styles.iconButton} ${styles.close}`} onClick={() => setDrawerOpen(false)} aria-label="Close navigation"><X size={20} aria-hidden="true" /></button>
      </div>

      <p className={styles.org} title={session.tenant.name}><span>{session.tenant.name}</span></p>

      {adminMode ? <>
        <Link className={styles.back} href="/home" title="Back to workspace"><ArrowLeft size={18} aria-hidden="true" /><span>Back to workspace</span></Link>
        <nav className={styles.nav} aria-label="Administration">
          {visibleAdminGroups(session).map((group) => <NavGroup key={group.label} label={group.label}>
            {group.pages.map(({ route, href, label, Icon }) => <NavItem key={route} href={href} icon={<Icon size={18} />} label={label} active={active === route} />)}
          </NavGroup>)}
        </nav>
      </> : <>
        {canContribute(session.roles) ? <Link className={styles.submit} data-tour="nav-submit" href="/ideas/new/v2" data-active={active === "submit"} title="Submit an idea"><Plus size={18} aria-hidden="true" /><span>Submit an idea</span></Link> : null}
        <nav className={styles.nav} aria-label="Primary">
          <NavGroup label="Workspace">
            <NavItem href="/home" icon={<Home size={18} />} label="Home" tour="nav-home" active={active === "home"} />
            <NavItem href="/ideas" icon={<ListFilter size={18} />} label="Idea Bank" tour="nav-ideas" active={active === "ideas"} />
            <NavItem href="/projects" icon={<FolderKanban size={18} />} label="Projects" tour="nav-projects" active={active === "projects"} />
            <NavItem href="/notifications" icon={<Inbox size={18} />} label="Inbox" tour="nav-inbox" active={active === "notifications"} badge={badge} ariaLabel={approvalCount ? `Inbox, ${approvalCount} need your action` : undefined} />
          </NavGroup>
          {adminHref ? <NavGroup label="Manage">
            <NavItem href={adminHref} icon={<Settings2 size={18} />} label="Administration" tour="nav-admin" active={false} />
          </NavGroup> : null}
        </nav>
      </>}

      <AccountMenu session={session} active={active === "profile"} />
    </aside>
    <GuidedTour open={tour.open} onClose={tour.close} label="TRANSPIRE tour" steps={platformTourSteps({ workspaceName: session.tenant.name, canSubmit: canContribute(session.roles), hasAdministration: Boolean(adminHref) })} />
  </>;
}

function NavGroup({ label, children }: { label: string; children: ReactNode }) {
  return <div className={styles.group}><p>{label}</p><ul>{children}</ul></div>;
}

function NavItem({ href, icon, label, active, badge, ariaLabel, tour }: { href: string; icon: ReactNode; label: string; active: boolean; badge?: ReactNode; ariaLabel?: string; tour?: string }) {
  return <li data-tour={tour}>
    <Link className={styles.item} href={href} data-active={active} aria-current={active ? "page" : undefined} aria-label={ariaLabel} title={label}>
      <span className={styles.itemIcon} aria-hidden="true">{icon}</span><span className={styles.itemLabel}>{label}</span>{badge}
    </Link>
  </li>;
}

function AccountMenu({ session, active }: { session: SessionIdentity; active: boolean }) {
  const router = useRouter();
  const root = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const firstItem = useRef<HTMLAnchorElement>(null);
  const [open, setOpen] = useState(false);
  const [signingOut, setSigningOut] = useState(false);
  const [displayName, setDisplayName] = useState(session.user.display_name);
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const theme = useTheme();

  useEffect(() => {
    const updateName = (event: Event) => setDisplayName((event as CustomEvent<{ displayName: string }>).detail.displayName);
    window.addEventListener("transpire:profile-updated", updateName);
    return () => window.removeEventListener("transpire:profile-updated", updateName);
  }, []);

  useEffect(() => {
    if (!open) return;
    if (!workspaces.length) {
      void apiRequest("/auth/workspaces")
        .then(async (response) => response.ok ? await response.json() as Workspace[] : [])
        .then(setWorkspaces)
        .catch(() => undefined);
    }
    firstItem.current?.focus();
    const close = (event: PointerEvent) => { if (!root.current?.contains(event.target as Node)) setOpen(false); };
    const escape = (event: KeyboardEvent) => { if (event.key === "Escape") { event.stopPropagation(); setOpen(false); trigger.current?.focus(); } };
    document.addEventListener("pointerdown", close);
    window.addEventListener("keydown", escape, true);
    return () => { document.removeEventListener("pointerdown", close); window.removeEventListener("keydown", escape, true); };
  }, [open, workspaces.length]);

  const signOut = async () => {
    setSigningOut(true);
    try { await apiRequest("/auth/logout", { method: "POST" }); }
    finally { router.replace("/sign-in"); }
  };

  return <div className={styles.account} ref={root}>
    <button ref={trigger} type="button" data-tour="account" className={styles.accountTrigger} data-active={active} aria-haspopup="menu" aria-expanded={open} onClick={() => setOpen((current) => !current)} title={displayName}>
      <ProfileAvatar name={displayName} />
      <span className={styles.accountText}><strong>{displayName}</strong><small>{session.user.email}</small></span>
      <ChevronsUpDown className={styles.accountChevron} size={15} aria-hidden="true" />
    </button>
    <div className={styles.menu} role="menu" data-open={open}>
      <Link ref={firstItem} href="/profile" role="menuitem" onClick={() => setOpen(false)}><Pencil size={15} aria-hidden="true" />Edit profile</Link>
      <Link href={isWorkspaceAdmin(session.roles) ? "/admin/audit-log" : "/profile#audit-log"} role="menuitem" onClick={() => setOpen(false)}><FileClock size={15} aria-hidden="true" />{isWorkspaceAdmin(session.roles) ? "Audit log" : "Your activity"}</Link>
      <button type="button" role="menuitem" onClick={() => { setOpen(false); startTour("platform"); }}><Compass size={15} aria-hidden="true" />Take the tour</button>
      {workspaces.length > 1 ? <div className={styles.workspaces}>
        <span>Switch organisation</span>
        {workspaces.map((workspace) => workspace.id === session.tenant.id
          ? <strong key={workspace.id}>{workspace.name}<small>Current</small></strong>
          : <a key={workspace.id} role="menuitem" href={`/t/${encodeURIComponent(workspace.slug)}/sign-in`}>{workspace.name}</a>)}
      </div> : null}
      <button type="button" role="menuitemcheckbox" aria-checked={theme === "dark"} onClick={() => setTheme(theme === "dark" ? "light" : "dark")}>{theme === "dark" ? <Sun size={15} aria-hidden="true" /> : <Moon size={15} aria-hidden="true" />}{theme === "dark" ? "Light mode" : "Dark mode"}</button>
      <button type="button" role="menuitem" onClick={() => void signOut()} disabled={signingOut}><LogOut size={15} aria-hidden="true" />{signingOut ? "Signing out" : "Sign out"}</button>
    </div>
  </div>;
}
