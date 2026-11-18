import type { Metadata } from "next";
import { NotificationsWorkspace } from "./notifications-workspace";

export const metadata: Metadata = {
  title: "Inbox | TRANSPIRE",
  description: "Approval decisions and corrections waiting on you, plus your ideas in review.",
};

export default function NotificationsPage() {
  return <NotificationsWorkspace />;
}
