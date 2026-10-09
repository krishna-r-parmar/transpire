import type { Metadata } from "next";
import { IdeaSubmission } from "../idea-submission";

export const metadata: Metadata = {
  title: "Submit an Idea | TRANSPIRE",
  description: "Capture and submit an operational improvement idea.",
};

export default async function NewIdeaCardFlowPage({ searchParams }: { searchParams: Promise<{ resume?: string }> }) {
  const { resume } = await searchParams;
  return <IdeaSubmission resumeIdeaId={resume} />;
}
