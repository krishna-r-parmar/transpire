import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";

export function proxy(request: NextRequest) {
  return NextResponse.redirect(new URL("/sign-in", request.url));
}

export const config = {
  matcher: [
    "/admin/:path*",
    "/audit/:path*",
    "/home/:path*",
    "/ideas/:path*",
    "/notifications/:path*",
    "/profile/:path*",
    "/projects/:path*",
  ],
};
