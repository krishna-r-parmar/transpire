import type { Metadata } from "next";
import { UserGroupsConsole } from "./groups-console";

export const metadata: Metadata = {
  title: "User groups | TRANSPIRE Administration",
  description: "Named groups of people used to approve workflow steps or to be asked for comments.",
};

export default function Page() {
  return <UserGroupsConsole />;
}
