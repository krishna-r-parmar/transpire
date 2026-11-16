"use client";

import { useEffect, useState } from "react";
import { apiRequest } from "@/lib/api";

type Summary = {
  ideas: Array<{ status: string }>;
  approval_items: Array<{ stage_id: string }>;
};

/** Count of approval items plus own ideas needing correction, refreshed every minute. */
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
              + summary.ideas.filter((idea) => idea.status === "needs_correction").length,
          );
        })
        .catch(() => undefined);
    };
    load();
    const timer = window.setInterval(load, 60_000);
    return () => window.clearInterval(timer);
  }, []);

  return count;
}
