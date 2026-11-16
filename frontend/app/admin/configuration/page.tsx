import { redirect } from "next/navigation";
import { tenantPath } from "@/lib/tenant-routing";

type Props = {
  params?: Promise<{ tenantSlug?: string }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
};

/** Configuration is now split into separate administration pages; keep old links and SSO callbacks working. */
export default async function ConfigurationPage({ params, searchParams }: Props) {
  const tenantSlug = (await params)?.tenantSlug;
  const sso = (await searchParams).sso;
  const target = sso === "validated" ? "/admin/sign-in?sso=validated" : sso ? "/admin/sign-in" : "/admin/sites";
  redirect(tenantSlug ? tenantPath(tenantSlug, target) : target);
}
