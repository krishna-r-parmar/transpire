import type { Metadata } from "next";
import { redirect } from "next/navigation";
import { EnterpriseFooter } from "@/components/landing/enterprise-footer";
import { tenantPath } from "@/lib/tenant-routing";
import { SignInPortal } from "./sign-in-portal";

export const metadata: Metadata = {
  title: "Sign in | TRANSPIRE",
  description: "Sign in securely to your organisation's TRANSPIRE workspace.",
};

type SignInPageProps = {
  params?: Promise<{ tenantSlug?: string }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
};

export default async function SignInPage({ params, searchParams }: SignInPageProps) {
  const tenantSlug = (await params)?.tenantSlug;
  const query = await searchParams;
  const containsCredentials = Object.keys(query).some((key) => {
    const normalizedKey = key.toLowerCase();
    return normalizedKey === "email" || normalizedKey === "password";
  });

  if (containsCredentials) {
    redirect(tenantSlug ? tenantPath(tenantSlug, "/sign-in") : "/sign-in");
  }

  return (
    <>
      <SignInPortal
        returnedWithSSOError={query.sso_error === "1"}
        selectingSSOWorkspace={query.sso_select === "1"}
      />
      <EnterpriseFooter
        journeyHref="/#movement"
        platformHref="/#platform"
        impactHref="/#impact"
        topHref="#sign-in-top"
      />
    </>
  );
}
