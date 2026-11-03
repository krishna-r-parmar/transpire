import Image from "next/image";
import Link from "next/link";
import styles from "./enterprise-footer.module.css";

type EnterpriseFooterProps = {
  topHref: string;
};

export function EnterpriseFooter({ topHref }: EnterpriseFooterProps) {
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
        </div>

        <nav className={styles.navigation} aria-label="Footer navigation">
          <Link href="/sign-in">Sign in</Link>
          <Link href="/privacy">Privacy Policy</Link>
          <a href={topHref}>Back to top ↑</a>
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
      </div>
    </footer>
  );
}
