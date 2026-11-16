import type { Metadata } from "next";
import { IdeaBankPolicyConsole } from "./policy-console";

export const metadata: Metadata = {
  title: "Idea Bank visibility | TRANSPIRE Administration",
  description: "Decide how much of each idea the Idea Bank shares.",
};

export default function Page() {
  return <IdeaBankPolicyConsole />;
}
