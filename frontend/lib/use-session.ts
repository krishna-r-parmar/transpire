"use client";

import { useTenantRouter as useRouter } from "@/lib/use-tenant-router";
import { useEffect, useState } from "react";
import { apiRequest, type SessionIdentity } from "@/lib/api";

export function useSession() {
  const router = useRouter();
  const [session, setSession] = useState<SessionIdentity | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  useEffect(() => {
    let active = true;
    apiRequest("/auth/session")
      .then(async (response) => {
        if (!active) return;
        if (response.status === 401) {
          router.replace("/sign-in");
          return;
        }
        if (!response.ok) throw new Error("Session service unavailable");
        const identity = (await response.json()) as SessionIdentity;
        if (active) setSession(identity);
      })
      .catch(() => {
        if (active) setError(true);
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [router]);

  return { session, loading, error };
}
