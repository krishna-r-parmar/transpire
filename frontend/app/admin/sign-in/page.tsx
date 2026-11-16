import type { Metadata } from "next";
import { SignInConsole } from "./sso-console";

export const metadata: Metadata = {
  title: "Microsoft sign-in | TRANSPIRE Administration",
  description: "Connect Microsoft Entra ID and move this organisation to single sign-on.",
};

export default async function Page({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const query = await searchParams;
  return <SignInConsole returnedFromSSOValidation={query.sso === "validated"} />;
}
