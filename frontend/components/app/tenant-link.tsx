"use client";

import NextLink, { type LinkProps } from "next/link";
import { usePathname } from "next/navigation";
import { forwardRef, type AnchorHTMLAttributes, type ReactNode } from "react";
import { isTenantScopedPath, tenantPath, tenantSlugFromPathname } from "@/lib/tenant-routing";

type TenantLinkProps = LinkProps &
  Omit<AnchorHTMLAttributes<HTMLAnchorElement>, keyof LinkProps> & {
    children: ReactNode;
  };

export const TenantLink = forwardRef<HTMLAnchorElement, TenantLinkProps>(function TenantLink(
  { href, ...props },
  ref,
) {
  const pathname = usePathname();
  const tenantSlug = tenantSlugFromPathname(pathname);
  const resolvedHref =
    tenantSlug && typeof href === "string" && isTenantScopedPath(href)
      ? tenantPath(tenantSlug, href)
      : href;

  return <NextLink ref={ref} href={resolvedHref} {...props} />;
});
