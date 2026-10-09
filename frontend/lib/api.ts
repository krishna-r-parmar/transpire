import { tenantSlugFromPathname } from "@/lib/tenant-routing";

const CONFIGURED_API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";
const CSRF_COOKIE_NAME =
  process.env.NEXT_PUBLIC_CSRF_COOKIE_NAME ?? "transpire_csrf";

function apiBaseUrl() {
  if (typeof window === "undefined") return CONFIGURED_API_BASE_URL;
  const configured = new URL(CONFIGURED_API_BASE_URL);
  return configured.toString().replace(/\/$/, "");
}

const GLOBAL_API_PATHS = new Set([
  "/auth/sign-in",
  "/auth/select-workspace",
  "/auth/password-reset/request",
  "/auth/invitations/inspect",
  "/auth/invitations/accept",
]);

function tenantApiPath(path: string) {
  if (GLOBAL_API_PATHS.has(path) || path.startsWith("/auth/sso/global/") || typeof window === "undefined") return path;
  const tenantSlug = tenantSlugFromPathname(window.location.pathname);
  if (!tenantSlug) throw new Error("Tenant shortname is missing from the application URL.");
  return `/t/${encodeURIComponent(tenantSlug)}${path}`;
}

export type SessionIdentity = {
  user: {
    id: string;
    email: string;
    display_name: string;
    is_platform_admin: boolean;
  };
  tenant: {
    id: string;
    slug: string;
    name: string;
  };
  roles: string[];
  expires_at: string;
};

export async function apiRequest(path: string, init?: RequestInit) {
  const headers = new Headers(init?.headers);
  if (init?.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const method = (init?.method ?? "GET").toUpperCase();
  if (typeof document !== "undefined" && !["GET", "HEAD", "OPTIONS"].includes(method)) {
    const csrfToken = document.cookie
      .split("; ")
      .find((entry) => entry.startsWith(`${CSRF_COOKIE_NAME}=`))
      ?.split("=")[1];
    if (csrfToken) headers.set("X-CSRF-Token", decodeURIComponent(csrfToken));
  }

  return fetch(`${apiBaseUrl()}${tenantApiPath(path)}`, {
    ...init,
    credentials: "include",
    headers,
  });
}

export function apiUrl(path: string) {
  return `${apiBaseUrl()}${tenantApiPath(path)}`;
}
