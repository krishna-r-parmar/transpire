import type { Metadata } from "next";
import { redirect } from "next/navigation";
import { EnterpriseFooter } from "@/components/landing/enterprise-footer";
import { ResetPasswordForm } from "./reset-password-form";

export const metadata: Metadata = {
  title: "Reset password | TRANSPIRE",
  description: "Create a new password for your TRANSPIRE workspace.",
};

type ResetPasswordPageProps = {
  params?: Promise<{ tenantSlug?: string }>;
  searchParams: Promise<{ token?: string }>;
};

export default async function ResetPasswordPage({ params, searchParams }: ResetPasswordPageProps) {
  if (!(await params)?.tenantSlug) redirect("/sign-in");
  const { token = "" } = await searchParams;
  return (
    <>
      <ResetPasswordForm token={token} />
      <EnterpriseFooter
        journeyHref="/#movement"
        platformHref="/#platform"
        impactHref="/#impact"
        topHref="#reset-password-top"
      />
    </>
  );
}
