import { Check, LockKeyhole } from "lucide-react";
import Image from "next/image";
import { TenantLink as Link } from "@/components/app/tenant-link";
import type { ReactNode } from "react";
import styles from "./recovery-shell.module.css";

type RecoveryShellProps = {
  pageId: string;
  eyebrow: string;
  title: string;
  description: string;
  children: ReactNode;
  visualLabel?: string;
  visualTitle?: string;
  visualSteps?: string[];
};

export function RecoveryShell({
  pageId,
  eyebrow,
  title,
  description,
  children,
  visualLabel = "Secure account recovery",
  visualTitle = "Account recovery, without compromising organisational trust.",
  visualSteps = [
    "Request a private reset link",
    "Confirm through your work email",
    "Return with secure access restored",
  ],
}: RecoveryShellProps) {
  return (
    <main className={styles.page} id={pageId}>
      <section className={styles.formSide} aria-labelledby={`${pageId}-heading`}>
        <header className={styles.header}>
          <Link href="/" className={styles.brand} aria-label="Return to TRANSPIRE home">
            <Image
              src="/brand/transpire-logo.png"
              alt="TRANSPIRE, Ideate. Transform. Inspire."
              width={1400}
              height={371}
              priority
            />
          </Link>
          <Link href="/sign-in">Back to sign in</Link>
        </header>

        <div className={styles.formShell}>
          <div className={styles.intro}>
            <p>{eyebrow}</p>
            <h1 id={`${pageId}-heading`}>{title}</h1>
            <span>{description}</span>
          </div>
          {children}
        </div>

        <p className={styles.legal}>Protected organisational access · Privacy and security controls apply</p>
      </section>

      <aside className={styles.visual} aria-label={visualLabel}>
        <div className={styles.visualTexture} aria-hidden="true" />
        <div className={styles.visualCopy}>
          <span className={styles.lock}><LockKeyhole aria-hidden="true" size={20} /></span>
          <p>{visualTitle}</p>
          <ol>
            {visualSteps.map((step) => (
              <li key={step}><Check aria-hidden="true" size={15} /><span>{step}</span></li>
            ))}
          </ol>
        </div>
        <div className={styles.motto}>
          <span>Ideate. Transform. Inspire.</span>
          <strong>Transform ideas. Inspire progress.</strong>
        </div>
      </aside>
    </main>
  );
}
