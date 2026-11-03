import type { Metadata } from "next";
import Image from "next/image";
import Link from "next/link";
import { Reveal } from "@/components/landing/reveal";
import { EnterpriseFooter } from "@/components/landing/enterprise-footer";
import { AmbientBulbVideo } from "@/components/landing/ambient-bulb-video";
import { HeroVideo } from "./hero-video";
import { ThemeToggle } from "./theme-toggle";
import styles from "./landing.module.css";

export const metadata: Metadata = {
  title: "TRANSPIRE | Ideate. Transform. Inspire.",
  description: "TRANSPIRE combines transformation and inspiration to move employee ideas into measurable organisational improvement.",
};

const triad = [
  ["Ideate.", "Write down what you see in a couple of minutes, with prompts that help the idea land."],
  ["Transform.", "Reviewers and experts shape it into an approved project with a clear owner."],
  ["Inspire.", "The result goes into the Idea Bank, so the next team starts further ahead."],
];

const roles = [
  ["Contributors", "Share what you notice", "Submit ideas, follow their progress, and see the difference they made."],
  ["Reviewers", "Decide with context", "Every idea arrives structured, with evidence and expected value attached."],
  ["OpEx leads", "Run the programme", "Configure approvals, track projects, and report realised benefit."],
];

const principles = [
  ["Guided idea capture", "Turn an observation into a structured improvement case with context, classification, evidence, and expected value."],
  ["Configurable governance", "Publish controlled approval contracts that reflect how each organisation evaluates and advances ideas."],
  ["A shared Idea Bank", "Make organisational learning discoverable while tenant-defined visibility protects sensitive detail."],
  ["Tenant-ready foundations", "Give each organisation an isolated workspace, its own configuration, and room to scale on one platform."],
];

export default function LandingPage() {
  return (
    <div className={styles.page} id="top">
      <a className={styles.skipLink} href="#main-content">Skip to content</a>

      <header className={styles.header}>
        <Link className={styles.brand} href="/" aria-label="TRANSPIRE home">
          <Image src="/brand/transpire-logo.png" alt="TRANSPIRE, Ideate. Transform. Inspire." width={1400} height={371} priority />
        </Link>
        <nav className={styles.nav} aria-label="Primary navigation">
          <a href="#how">How it works</a>
          <a href="#who">Who it&apos;s for</a>
          <a href="#platform">Platform</a>
        </nav>
        <ThemeToggle />
        <Link className={styles.signIn} href="/sign-in" scroll>Sign in</Link>
        <details className={styles.mobileMenu}>
          <summary aria-label="Open navigation"><span /><span /></summary>
          <nav aria-label="Mobile navigation">
            <a href="#how">How it works</a>
            <a href="#who">Who it&apos;s for</a>
            <a href="#platform">Platform</a>
            <Link href="/sign-in" scroll>Sign in to TRANSPIRE</Link>
          </nav>
        </details>
      </header>

      <main id="main-content">
        <section className={styles.hero} aria-labelledby="hero-heading">
          <div className={styles.glow} aria-hidden="true" />
          <div className={styles.heroInner}>
            <div className={styles.heroCopy}>
              <p className={styles.kicker}>Ideate. Transform. Inspire.</p>
              <h1 id="hero-heading">
                Every improvement starts with someone who{" "}
                <span className={styles.mark}>
                  noticed.
                  <svg viewBox="0 0 300 40" preserveAspectRatio="none" aria-hidden="true">
                    <path d="M4 30 C 80 34, 160 30, 230 18 S 280 6, 292 4" />
                    <path d="M274 2 L294 3 L286 20" />
                  </svg>
                </span>
              </h1>
              <p className={styles.lead}>TRANSPIRE gives that observation a place to go, people to shape it, and a visible path to real change.</p>
              <div className={styles.actions}>
                <Link className={styles.primaryAction} href="/sign-in" scroll>Share an idea <span aria-hidden="true">↗</span></Link>
                <a className={styles.secondaryAction} href="#how">See how it works</a>
              </div>
            </div>
            <AmbientBulbVideo className={styles.bulb} />
          </div>
        </section>

        <section className={styles.triad} id="how" aria-label="How TRANSPIRE works">
          <div className={styles.triadInner}>
            {triad.map(([title, description]) => (
              <article key={title}><h2>{title}</h2><p>{description}</p></article>
            ))}
          </div>
        </section>

        <section className={styles.roles} id="who" aria-labelledby="roles-heading">
          <Reveal className={styles.rolesIntro}>
            <h2 id="roles-heading">One place for everyone who improves the work</h2>
            <p>Each person sees what they need, in their own organisation&apos;s private workspace.</p>
          </Reveal>
          <div className={styles.roleGrid}>
            {roles.map(([who, title, description]) => (
              <article key={who}><span>{who}</span><h3>{title}</h3><p>{description}</p></article>
            ))}
          </div>
        </section>

        <section className={styles.platform} id="platform" aria-labelledby="platform-heading">
          <h2 id="platform-heading">One platform for ideas, governance, and measurable improvement</h2>
          <div className={styles.principleList}>
            {principles.map(([title, description]) => (
              <article key={title}><h3>{title}</h3><p>{description}</p></article>
            ))}
          </div>
        </section>

        <section className={styles.closing} id="journey" aria-labelledby="closing-heading">
          <HeroVideo />
          <div className={styles.closingShade} aria-hidden="true" />
          <div className={styles.closingInner}>
            <h2 id="closing-heading">Your next idea could be the one that changes the line.</h2>
            <Link href="/sign-in" scroll>Sign in to TRANSPIRE <span aria-hidden="true">↗</span></Link>
          </div>
        </section>
      </main>

      <EnterpriseFooter topHref="#top" />
    </div>
  );
}
