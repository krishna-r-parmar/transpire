import type { Metadata } from "next";
import { DirectoryConsole } from "./directory-console";

export const metadata: Metadata = {
  title: "HR directory | TRANSPIRE Administration",
  description: "The employee directory fed by the HR system, and its daily file runs.",
};

export default function Page() {
  return <DirectoryConsole />;
}
