import type { Metadata } from "next";
import { EnterpriseFooter } from "@/components/landing/enterprise-footer";
import { ForgotPasswordForm } from "./forgot-password-form";

export const metadata: Metadata = {
  title: "Forgot password | TRANSPIRE",
  description: "Request secure password recovery for your TRANSPIRE workspace.",
};

export default function ForgotPasswordPage() {
  return (
    <>
      <ForgotPasswordForm />
      <EnterpriseFooter
        journeyHref="/#movement"
        platformHref="/#platform"
        impactHref="/#impact"
        topHref="#forgot-password-top"
      />
    </>
  );
}
