import type { Metadata } from "next";
import { ConfigurationConsole } from "./configuration-console";

export const metadata: Metadata = {
  title: "Configuration | TRANSPIRE Administration",
  description: "Configure organisation structures, idea classification, and approval contracts.",
};

export default async function ConfigurationPage({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  const query = await searchParams;
  return <ConfigurationConsole returnedFromSSOValidation={query.sso === "validated"} />;
}
