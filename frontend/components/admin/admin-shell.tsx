"use client";

import Image from "next/image";
import { TenantLink as Link } from "@/components/app/tenant-link";
import type { ReactNode } from "react";
import { AppMenu } from "@/components/app/app-menu";
import { DesktopNavigation } from "@/components/app/desktop-navigation";
import type { SessionIdentity } from "@/lib/api";
import styles from "./admin-shell.module.css";

type AdminShellProps = {
  session: SessionIdentity;
  active: "tenants" | "people" | "configuration" | "submit" | "ideas" | "projects" | "profile" | "notifications" | "audit";
  eyebrow: string;
  title: string;
  description: string;
  children: ReactNode;
};

export function AdminShell({
  session,
  active,
  eyebrow,
  title,
  description,
  children,
}: AdminShellProps) {
  return (
    <div className={styles.app}>
      <header className={styles.topbar}>
        <Link href="/home" aria-label="TRANSPIRE home">
          <Image src="/brand/transpire-logo.png" alt="TRANSPIRE" width={1400} height={371} priority />
        </Link>
        <DesktopNavigation session={session} active={active} />
        <AppMenu session={session} active={active} />
      </header>

      <main className={styles.main}>
        <header className={styles.pageHeader}>
          <p>{eyebrow}</p>
          <h1>{title}</h1>
          <span>{description}</span>
        </header>
        {children}
      </main>
    </div>
  );
}
