const TENANT_SLUG_PATTERN = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;
const TENANT_ROUTE_ROOTS = [
  "/admin",
  "/audit",
  "/forgot-password",
  "/home",
  "/ideas",
  "/notifications",
  "/profile",
  "/projects",
  "/reset-password",
  "/sign-in",
] as const;

export function tenantSlugFromPathname(pathname: string): string | null {
  const match = pathname.match(/^\/t\/([^/]+)(?:\/|$)/);
  if (!match) return null;
  let slug: string;
  try {
    slug = decodeURIComponent(match[1]).toLowerCase();
  } catch {
    return null;
  }
  return TENANT_SLUG_PATTERN.test(slug) ? slug : null;
}

export function tenantPath(tenantSlug: string, path: string): string {
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  return `/t/${encodeURIComponent(tenantSlug)}${normalizedPath}`;
}

export function isTenantScopedPath(path: string): boolean {
  return TENANT_ROUTE_ROOTS.some(
    (root) =>
      path === root ||
      path.startsWith(`${root}/`) ||
      path.startsWith(`${root}?`) ||
      path.startsWith(`${root}#`),
  );
}

export function currentTenantPath(path: string): string {
  if (!isTenantScopedPath(path)) return path;
  if (typeof window === "undefined") return path;
  const slug = tenantSlugFromPathname(window.location.pathname);
  return slug ? tenantPath(slug, path) : path;
}
