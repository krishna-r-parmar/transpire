import type { Metadata } from "next";
import { PeopleConsole } from "./people-console";

export const metadata: Metadata = {
  title: "People | TRANSPIRE Administration",
  description: "Invite and manage people in your organisation's TRANSPIRE workspace.",
};

export default function PeoplePage() {
  return <PeopleConsole />;
}
