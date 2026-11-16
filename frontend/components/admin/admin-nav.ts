import { Building2, Eye, FileClock, GitBranch, KeyRound, Layers3, MapPin, Network, Users, Workflow, type LucideIcon } from "lucide-react";
import type { SessionIdentity } from "@/lib/api";

export type AdminRoute = "sites" | "departments" | "categories" | "process_areas" | "workflow" | "idea_bank_policy" | "people" | "sign_in" | "audit_log" | "tenants";

export type AdminPage = { route: AdminRoute; href: string; label: string; Icon: LucideIcon };
export type AdminGroup = { label: string; pages: AdminPage[]; platform?: boolean };

/** The administration information architecture: one page per register or policy. */
export const adminGroups: AdminGroup[] = [
  { label: "Organisation", pages: [
    { route: "sites", href: "/admin/sites", label: "Sites", Icon: MapPin },
    { route: "departments", href: "/admin/departments", label: "Departments", Icon: Network },
  ] },
  { label: "Idea setup", pages: [
    { route: "categories", href: "/admin/categories", label: "Categories", Icon: Layers3 },
    { route: "process_areas", href: "/admin/process-areas", label: "Process areas", Icon: Workflow },
  ] },
  { label: "Governance", pages: [
    { route: "workflow", href: "/admin/approval-workflow", label: "Approval workflow", Icon: GitBranch },
    { route: "idea_bank_policy", href: "/admin/idea-bank-visibility", label: "Idea Bank visibility", Icon: Eye },
  ] },
  { label: "Access", pages: [
    { route: "people", href: "/admin/people", label: "People", Icon: Users },
    { route: "sign_in", href: "/admin/sign-in", label: "Microsoft sign-in", Icon: KeyRound },
    { route: "audit_log", href: "/admin/audit-log", label: "Audit log", Icon: FileClock },
  ] },
  { label: "Platform", platform: true, pages: [
    { route: "tenants", href: "/admin/tenants", label: "Tenants", Icon: Building2 },
  ] },
];

export const isAdminRoute = (route: string): route is AdminRoute => adminGroups.some((group) => group.pages.some((page) => page.route === route));

export function visibleAdminGroups(session: SessionIdentity) {
  const tenantAdmin = session.roles.includes("tenant_admin");
  return adminGroups.filter((group) => group.platform ? session.user.is_platform_admin : tenantAdmin);
}

/** First admin page this person can open; null when they have no administration access. */
export function adminHome(session: SessionIdentity) {
  return visibleAdminGroups(session)[0]?.pages[0]?.href ?? null;
}

export function adminBreadcrumb(route: AdminRoute) {
  const group = adminGroups.find((candidate) => candidate.pages.some((page) => page.route === route));
  const page = group?.pages.find((candidate) => candidate.route === route);
  return group && page ? ["Administration", group.label, page.label] : ["Administration"];
}
