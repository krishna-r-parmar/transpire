import type { Metadata } from "next";
import { IdeaBank } from "./idea-bank";

export const metadata: Metadata = {
  title: "Idea Bank | TRANSPIRE",
  description: "Explore submitted improvement ideas across your organisation.",
};

export default function IdeasPage() {
  return <IdeaBank />;
}
