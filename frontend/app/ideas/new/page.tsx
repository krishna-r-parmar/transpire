import { redirect } from "next/navigation";
import { tenantPath } from "@/lib/tenant-routing";

export default async function NewIdeaPage({ params }: { params?: Promise<{ tenantSlug?: string }> }) {
  const tenantSlug = (await params)?.tenantSlug;
  redirect(tenantSlug ? tenantPath(tenantSlug, "/ideas/new/v2") : "/sign-in");
}
