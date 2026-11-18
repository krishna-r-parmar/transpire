"use client";

import { useEffect, useState } from "react";
import { apiRequest } from "@/lib/api";

type Summary = {
  ideas: Array<{ status: string }>;
  approval_items: Array<{ stage_id: string }>;
  join_requests?: Array<{ id: string }>;
};

/** Inbox count: approvals, own ideas needing correction, and requests to join own ideas. Refreshed every minute. */
export function useApprovalCount() {
  const [count, setCount] = useState(0);

  useEffect(() => {
    const load = () => {
      void apiRequest("/ideas/home-summary")
        .then(async (response) => {
          if (!response.ok) return;
          const summary = (await response.json()) as Summary;
          setCount(
            summary.approval_items.length
              + summary.ideas.filter((idea) => idea.status === "needs_correction").length
              + (summary.join_requests?.length ?? 0),
          );
        })
        .catch(() => undefined);
    };
    load();
    const timer = window.setInterval(load, 60_000);
    window.addEventListener("transpire:inbox-changed", load);
    return () => { window.clearInterval(timer); window.removeEventListener("transpire:inbox-changed", load); };
  }, []);

  return count;
}
