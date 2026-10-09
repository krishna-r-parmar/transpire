import type { Metadata } from "next";
import { IdeaDetail } from "./idea-detail";

export const metadata: Metadata = {
  title: "Idea details | TRANSPIRE",
  description: "Review an idea, its approval route, and its implementation charter.",
};

export default async function IdeaDetailPage({ params }: { params: Promise<{ ideaId: string }> }) {
  const { ideaId } = await params;
  return <IdeaDetail ideaId={ideaId} />;
}
