import type { Metadata } from "next";
import { HomeWorkspace } from "./home-workspace";

export const metadata: Metadata = {
  title: "Home | TRANSPIRE",
  description: "Your TRANSPIRE organisational improvement workspace.",
};

export default function HomePage() {
  return <HomeWorkspace />;
}
