import type { Metadata } from "next";
import { EnterpriseFooter } from "@/components/landing/enterprise-footer";
import { InvitationAcceptance } from "./invitation-acceptance";

export const metadata: Metadata = {
  title: "Accept invitation | TRANSPIRE",
  description: "Join your organisation's secure TRANSPIRE workspace.",
};

export default async function AcceptInvitationPage({
  searchParams,
}: {
  searchParams: Promise<{ token?: string | string[] }>;
}) {
  const tokenValue = (await searchParams).token;
  const token = typeof tokenValue === "string" ? tokenValue : "";

  return (
    <>
      <InvitationAcceptance token={token} />
      <EnterpriseFooter
        journeyHref="/#movement"
        platformHref="/#platform"
        impactHref="/#impact"
        topHref="#accept-invitation-top"
      />
    </>
  );
}
