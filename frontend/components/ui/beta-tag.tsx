import styles from "./beta-tag.module.css";

export function BetaTag({ className }: { className?: string }) {
  return (
    <span className={className ? `${styles.tag} ${className}` : styles.tag} title="TRANSPIRE is in beta">
      Beta
    </span>
  );
}
