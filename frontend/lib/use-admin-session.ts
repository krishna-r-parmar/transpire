"use client";

import { useEffect } from "react";
import { useTenantRouter as useRouter } from "@/lib/use-tenant-router";
import { useSession } from "@/lib/use-session";
import { isWorkspaceAdmin, isWorkspaceOwner } from "@/lib/roles";

/** Session for an administration page; people without the required access are sent back to Home. */
export function useAdminSession(access: "tenant" | "owner" | "platform" = "tenant") {
  const router = useRouter();
  const { session, loading } = useSession();
  const allowed = session
    ? access === "platform" ? session.user.is_platform_admin
      : access === "owner" ? isWorkspaceOwner(session.roles)
        : isWorkspaceAdmin(session.roles)
    : false;

  useEffect(() => {
    if (session && !allowed) router.replace("/home");
  }, [allowed, router, session]);

  return { session: allowed ? session : null, loading: loading || Boolean(session && !allowed) };
}
