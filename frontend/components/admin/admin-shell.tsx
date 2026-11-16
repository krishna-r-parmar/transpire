"use client";

import type { ReactNode } from "react";
import { AppSidebar, type AppRoute } from "@/components/app/app-sidebar";
import { adminBreadcrumb, isAdminRoute } from "./admin-nav";
import type { SessionIdentity } from "@/lib/api";
import styles from "./admin-shell.module.css";

type AppFrameProps = {
  session: SessionIdentity;
  active: AppRoute;
  children: ReactNode;
};

/** Sidebar plus a single main column. Pages that compose their own heading (Home) use this directly. */
export function AppFrame({ session, active, children }: AppFrameProps) {
  return (
    <div className={styles.app} data-area={isAdminRoute(active) ? "admin" : "workspace"}>
      <AppSidebar session={session} active={active} />
      <main className={styles.main} id="main-content">{children}</main>
    </div>
  );
}

type AdminShellProps = AppFrameProps & {
  /** Area label above the title. Administration pages show their breadcrumb instead. */
  eyebrow?: string;
  title: string;
  description: string;
  actions?: ReactNode;
};

/** Focused page: one heading, one line of purpose, and the page's own actions. Global navigation lives in the sidebar. */
export function AdminShell({ session, active, eyebrow, title, description, actions, children }: AdminShellProps) {
  return (
    <AppFrame session={session} active={active}>
      <header className={styles.pageHeader}>
        <div>
          {isAdminRoute(active)
            ? <nav className={styles.breadcrumb} aria-label="Breadcrumb"><ol>{adminBreadcrumb(active).map((crumb) => <li key={crumb}>{crumb}</li>)}</ol></nav>
            : eyebrow ? <p>{eyebrow}</p> : null}
          <h1>{title}</h1>
          <span>{description}</span>
        </div>
        {actions ? <div className={styles.pageActions}>{actions}</div> : null}
      </header>
      {children}
    </AppFrame>
  );
}
