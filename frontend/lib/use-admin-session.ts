"use client";

import { useEffect } from "react";
import { useTenantRouter as useRouter } from "@/lib/use-tenant-router";
import { useSession } from "@/lib/use-session";

/** Session for an administration page; people without the required access are sent back to Home. */
export function useAdminSession(access: "tenant" | "platform" = "tenant") {
  const router = useRouter();
  const { session, loading } = useSession();
  const allowed = session ? (access === "platform" ? session.user.is_platform_admin : session.roles.includes("tenant_admin")) : false;

  useEffect(() => {
    if (session && !allowed) router.replace("/home");
  }, [allowed, router, session]);

  return { session: allowed ? session : null, loading: loading || Boolean(session && !allowed) };
}
