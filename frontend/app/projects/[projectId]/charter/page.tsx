import type { Metadata } from "next";
import { CharterEditor } from "./charter-editor";

export const metadata: Metadata = {
  title: "Project charter | TRANSPIRE",
  description: "Complete and submit the charter for an approved idea.",
};

export default async function ProjectCharterPage({ params }: { params: Promise<{ projectId: string }> }) {
  const { projectId } = await params;
  return <CharterEditor projectId={projectId} />;
}
