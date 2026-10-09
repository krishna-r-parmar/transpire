import type { Metadata } from "next";
import { SSORecovery } from "./sso-recovery";

export const metadata: Metadata = {
  title: "Restricted SSO recovery | TRANSPIRE",
  description: "Repair a Microsoft SSO connection using a restricted recovery session.",
};

export default async function SSORecoveryPage({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const query = await searchParams;
  const token = typeof query.token === "string" ? query.token : "";
  return <SSORecovery token={token} />;
}
