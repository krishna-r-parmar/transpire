import type { Metadata } from "next";
import { IdeaSummary } from "./idea-summary";

export const metadata: Metadata = {
  title: "Idea summary | TRANSPIRE",
  description: "A read-only summary of an idea shared in the Idea Bank.",
};

export default async function IdeaSummaryPage({ params }: { params: Promise<{ ideaId: string }> }) {
  const { ideaId } = await params;
  return <IdeaSummary ideaId={ideaId} />;
}
