import type { Metadata } from "next";
import { WorkflowConsole } from "./workflow-console";

export const metadata: Metadata = {
  title: "Approval workflow | TRANSPIRE Administration",
  description: "Build and publish the approval route new ideas follow.",
};

export default function Page() {
  return <WorkflowConsole />;
}
