"use client";

import { AdminShell } from "@/components/admin/admin-shell";
import { AuditLog } from "@/app/audit/audit-workspace";
import { useAdminSession } from "@/lib/use-admin-session";
import shared from "../admin.module.css";

export function AuditLogConsole() {
  const { session, loading } = useAdminSession();
  if (loading || !session) return <main className={shared.loading}>Loading administration</main>;
  return <AdminShell session={session} active="audit_log" title="Audit log" description="A permanent record of governed activity across this organisation: who changed what, and when.">
    <AuditLog session={session} />
  </AdminShell>;
}
