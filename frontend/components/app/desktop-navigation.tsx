"use client";

import { Building2, FolderKanban, Home, Lightbulb, ListFilter, Settings2, Users } from "lucide-react";
import { TenantLink as Link } from "@/components/app/tenant-link";
import type { SessionIdentity } from "@/lib/api";
import { ApprovalNotificationsLink } from "./approval-notifications-link";
import { ProfileAccountMenu } from "./profile-account-menu";
import styles from "./desktop-navigation.module.css";

type ActiveRoute = "home" | "people" | "tenants" | "configuration" | "submit" | "ideas" | "projects" | "profile" | "notifications" | "audit";

export function DesktopNavigation({ session, active }: { session: SessionIdentity; active: ActiveRoute }) {
  return <nav className={styles.navigation} aria-label="Primary application navigation">
    <Link className={styles.route} href="/home" data-active={active === "home"}><Home size={15} />Home</Link>
    <Link className={styles.route} href="/ideas/new/v2" data-active={active === "submit"}><Lightbulb size={15} />Submit an idea</Link>
    <Link className={styles.route} href="/ideas" data-active={active === "ideas"}><ListFilter size={15} />Idea Bank</Link>
    <Link className={styles.route} href="/projects" data-active={active === "projects"}><FolderKanban size={15} />Projects</Link>
    {session.roles.includes("tenant_admin") ? <Link className={styles.route} href="/admin/people" data-active={active === "people"}><Users size={15} />People</Link> : null}
    {session.roles.includes("tenant_admin") ? <Link className={styles.route} href="/admin/configuration" data-active={active === "configuration"}><Settings2 size={15} />Configuration</Link> : null}
    {session.user.is_platform_admin ? <Link className={styles.route} href="/admin/tenants" data-active={active === "tenants"}><Building2 size={15} />Tenants</Link> : null}
    <ApprovalNotificationsLink active={active === "notifications"} />
    <ProfileAccountMenu session={session} active={active === "profile"} />
  </nav>;
}
