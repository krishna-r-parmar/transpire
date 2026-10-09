import type { Metadata } from "next";
import { NotificationsWorkspace } from "./notifications-workspace";

export const metadata: Metadata = {
  title: "Approval Notifications | TRANSPIRE",
  description: "Review ideas awaiting your decision and follow your own approval journeys.",
};

export default function NotificationsPage() {
  return <NotificationsWorkspace />;
}
