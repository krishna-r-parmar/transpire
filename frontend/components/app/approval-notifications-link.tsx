"use client";

import { Bell } from "lucide-react";
import { TenantLink as Link } from "@/components/app/tenant-link";
import { useEffect, useState } from "react";
import { apiRequest } from "@/lib/api";
import styles from "./approval-notifications-link.module.css";

type Summary = {
  ideas: Array<{ status: string }>;
  approval_items: Array<{ stage_id: string }>;
};

export function ApprovalNotificationsLink({ active }: { active: boolean }) {
  const [count, setCount] = useState(0);

  useEffect(() => {
    const load = () => {
      void apiRequest("/ideas/home-summary")
        .then(async (response) => {
          if (!response.ok) return;
          const summary = (await response.json()) as Summary;
          setCount(
            summary.approval_items.length
              + summary.ideas.filter((idea) => idea.status === "needs_correction").length,
          );
        })
        .catch(() => undefined);
    };
    load();
    const timer = window.setInterval(load, 60_000);
    return () => window.clearInterval(timer);
  }, []);

  return <Link className={styles.link} href="/notifications" data-active={active} aria-label={count ? `Approval notifications, ${count} requiring attention` : "Approval notifications"}>
    <Bell aria-hidden="true" size={18} />
    {count ? <span>{count > 99 ? "99+" : count}</span> : null}
  </Link>;
}
