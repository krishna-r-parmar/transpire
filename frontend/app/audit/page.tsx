import type { Metadata } from "next";
import { redirect } from "next/navigation";
import { tenantPath } from "@/lib/tenant-routing";

export const metadata: Metadata = {
  title: "Audit Log | TRANSPIRE",
  description: "Review accountable activity across the TRANSPIRE idea lifecycle.",
};

export default async function AuditPage({ params }: { params?: Promise<{ tenantSlug?: string }> }) {
  const tenantSlug = (await params)?.tenantSlug;
  redirect(tenantSlug ? tenantPath(tenantSlug, "/profile#audit-log") : "/sign-in");
}
