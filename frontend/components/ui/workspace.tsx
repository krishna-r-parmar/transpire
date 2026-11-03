import { useId, type ReactNode } from "react";
import { TenantLink as Link } from "@/components/app/tenant-link";
import styles from "./workspace.module.css";

type Tone = "neutral" | "info" | "success" | "warning" | "danger";

type SectionCardProps = {
  icon?: ReactNode;
  title: string;
  description?: string;
  meta?: ReactNode;
  actions?: ReactNode;
  tinted?: boolean;
  flush?: boolean;
  className?: string;
  children: ReactNode;
};

export function SectionCard({ icon, title, description, meta, actions, tinted = false, flush = false, className, children }: SectionCardProps) {
  const headingId = useId();
  return <section className={[styles.card, className].filter(Boolean).join(" ")} data-tone={tinted ? "tinted" : undefined} aria-labelledby={headingId}>
    <header className={styles.cardHead}>
      {icon ? <span className={styles.cardIcon} aria-hidden="true">{icon}</span> : null}
      <div className={styles.cardTitle}><h2 id={headingId}>{title}</h2>{description ? <p>{description}</p> : null}</div>
      {meta ? <span className={styles.cardMeta}>{meta}</span> : null}
      {actions ? <div className={styles.cardActions}>{actions}</div> : null}
    </header>
    <div className={styles.cardBody} data-flush={flush}>{children}</div>
  </section>;
}

export type SummaryItem = { icon: ReactNode; value: ReactNode; label: string; note?: string; tone?: Tone; href?: string };

export function SummaryStrip({ items, label = "Summary" }: { items: SummaryItem[]; label?: string }) {
  return <section className={styles.summary} aria-label={label}>
    {items.map((item) => {
      const content = <><span className={styles.summaryIcon} aria-hidden="true">{item.icon}</span><span><strong>{item.value}</strong><span className={styles.summaryLabel}>{item.label}</span>{item.note ? <span className={styles.summaryNote}>{item.note}</span> : null}</span></>;
      return item.href
        ? <Link key={item.label} className={styles.summaryItem} href={item.href} data-tone={item.tone}>{content}</Link>
        : <div key={item.label} className={styles.summaryItem} data-tone={item.tone}>{content}</div>;
    })}
  </section>;
}

export function StatusPill({ tone = "neutral", icon, children }: { tone?: Tone; icon?: ReactNode; children: ReactNode }) {
  return <span className={styles.status} data-tone={tone}>{icon}{children}</span>;
}
