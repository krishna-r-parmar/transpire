"use client";

import { useRouter as useNextRouter } from "next/navigation";
import { useCallback, useMemo } from "react";
import { currentTenantPath, isTenantScopedPath } from "@/lib/tenant-routing";

type NextRouter = ReturnType<typeof useNextRouter>;
type PushOptions = Parameters<NextRouter["push"]>[1];
type ReplaceOptions = Parameters<NextRouter["replace"]>[1];
type PrefetchOptions = Parameters<NextRouter["prefetch"]>[1];

function resolveTenantHref(href: string) {
  if (!isTenantScopedPath(href)) return href;
  return currentTenantPath(href);
}

export function useTenantRouter() {
  const router = useNextRouter();
  const nextPush = router.push;
  const nextReplace = router.replace;
  const nextPrefetch = router.prefetch;
  const push = useCallback(
    (href: string, options?: PushOptions) =>
      nextPush(resolveTenantHref(href), options),
    [nextPush],
  );
  const replace = useCallback(
    (href: string, options?: ReplaceOptions) =>
      nextReplace(resolveTenantHref(href), options),
    [nextReplace],
  );
  const prefetch = useCallback(
    (href: string, options?: PrefetchOptions) =>
      nextPrefetch(resolveTenantHref(href), options),
    [nextPrefetch],
  );

  return useMemo(
    () => ({ ...router, push, replace, prefetch }),
    [prefetch, push, replace, router],
  );
}
