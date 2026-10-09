import type { Metadata } from "next";
import { ProfileWorkspace } from "./profile-workspace";

export const metadata: Metadata = {
  title: "Profile | TRANSPIRE",
  description: "Manage your TRANSPIRE identity, preferences, and improvement contribution history.",
};

export default function ProfilePage() {
  return <ProfileWorkspace />;
}
