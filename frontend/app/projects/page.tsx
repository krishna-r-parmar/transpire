import type { Metadata } from "next";
import { ProjectsPortfolio } from "./projects-portfolio";

export const metadata: Metadata = {
  title: "Projects | TRANSPIRE",
  description: "Track implementation, benefits, and completion across your organisation.",
};

export default function ProjectsPage() {
  return <ProjectsPortfolio />;
}
