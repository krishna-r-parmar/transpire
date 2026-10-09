import type { Metadata } from "next";
import { ProjectWorkspace } from "./project-workspace";

export const metadata: Metadata = {
  title: "Project workspace | TRANSPIRE",
  description: "Review project delivery, benefits, charter baselines, team, and activity.",
};

export default async function ProjectWorkspacePage({
  params,
}: {
  params: Promise<{ projectId: string }>;
}) {
  const { projectId } = await params;
  return <ProjectWorkspace projectId={projectId} />;
}
