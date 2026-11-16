import type { Metadata } from "next";
import { AuditLogConsole } from "./audit-log-console";

export const metadata: Metadata = {
  title: "Audit log | TRANSPIRE Administration",
  description: "Review governed activity across this organisation.",
};

export default function Page() {
  return <AuditLogConsole />;
}
