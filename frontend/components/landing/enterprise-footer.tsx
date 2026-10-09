import Image from "next/image";
import styles from "./enterprise-footer.module.css";

type EnterpriseFooterProps = {
  impactHref: string;
  impactLabel?: string;
  journeyHref: string;
  journeyLabel?: string;
  platformHref: string;
  topHref: string;
};

export function EnterpriseFooter({ impactHref, impactLabel = "Impact", journeyHref, journeyLabel = "How ideas move", platformHref, topHref }: EnterpriseFooterProps) {
  return (
    <footer className={styles.footer}>
      <div className={styles.main}>
        <div className={styles.brandBlock}>
          <Image
            src="/brand/transpire-logo.png"
            alt="TRANSPIRE"
            width={1400}
            height={371}
            sizes="220px"
          />
          <p className={styles.motto}>Ideate. Transform. Inspire.<br />Transform ideas. Inspire progress.</p>
          <p className={styles.description}>
            A connected system for ideas, governance, implementation, and measurable improvement.
          </p>
        </div>

        <nav className={styles.navigation} aria-label="Footer navigation">
          <div>
            <h2>Platform</h2>
            <a href={journeyHref}>{journeyLabel}</a>
            <a href={platformHref}>Designed to adapt</a>
            <a href={impactHref}>{impactLabel}</a>
          </div>
          <div>
            <h2>Access</h2>
            <a href="/sign-in">Sign in</a>
            <span>Contact your TRANSPIRE administrator</span>
          </div>
          <div>
            <h2>Enterprise</h2>
            <span>Tenant-aware by design</span>
            <span>Private by organisation</span>
            <span>Built for Operational Excellence</span>
          </div>
        </nav>
      </div>

      <div className={styles.bottom}>
        <Image
          src="/brand/group-logo.png"
          alt="Dishman Carbogen Amcis Ltd."
          width={3299}
          height={1094}
          sizes="190px"
        />
        <p>© {new Date().getFullYear()} Dishman Carbogen Amcis Ltd. All rights reserved.</p>
        <a href={topHref}>Back to top ↑</a>
      </div>
    </footer>
  );
}
