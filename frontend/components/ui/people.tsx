import styles from "./people.module.css";

export function initials(name: string | null | undefined) {
  const parts = (name ?? "").trim().split(/\s+/).filter(Boolean);
  return (parts.length > 1 ? `${parts[0][0]}${parts.at(-1)?.[0] ?? ""}` : parts[0]?.slice(0, 2) ?? "?").toUpperCase();
}

/** Owner first, then up to `max` teammates as overlapping initials, with a readable summary beside them. */
export function PeopleStack({ owner, team, max = 3 }: { owner: string | null; team: string[]; max?: number }) {
  const others = team.filter((name) => name !== owner);
  const shown = [owner, ...others].filter((name): name is string => Boolean(name)).slice(0, max + 1);
  const extra = others.length + (owner ? 1 : 0) - shown.length;
  const summary = owner
    ? others.length ? `${owner} + ${others.length} ${others.length === 1 ? "teammate" : "teammates"}` : owner
    : others.length ? `${others.length} team ${others.length === 1 ? "member" : "members"}` : "No team yet";
  return <span className={styles.stack} title={[owner ? `Owner: ${owner}` : null, others.length ? `Team: ${others.join(", ")}` : null].filter(Boolean).join("\n")}>
    <span className={styles.faces} aria-hidden="true">
      {shown.map((name, index) => <span key={`${name}-${index}`} data-owner={index === 0 && Boolean(owner)}>{initials(name)}</span>)}
      {extra > 0 ? <span>+{extra}</span> : null}
    </span>
    <span className={styles.summary}>{summary}</span>
  </span>;
}
