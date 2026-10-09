import type { Metadata } from "next";
import { TenantConsole } from "./tenant-console";

export const metadata: Metadata = {
  title: "Tenant administration | TRANSPIRE",
};

export default function TenantAdministrationPage() {
  return <TenantConsole />;
}
