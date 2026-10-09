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

const movement = [
  ["01", "See it", "Recognise the opportunity hidden inside everyday work."],
  ["02", "Share it", "Give the observation enough context to travel clearly."],
  ["03", "Shape it", "Bring knowledge and judgement together around the idea."],
  ["04", "Move it", "Create ownership, direction, and a visible next step."],
  ["05", "Prove it", "Carry the result forward as organisational learning."],
];

const principles = [
  ["Guided idea capture", "Turn an observation into a structured improvement case with context, classification, evidence, and expected value."],
  ["Configurable governance", "Publish controlled approval contracts that reflect how each organisation evaluates and advances ideas."],
  ["A shared Idea Bank", "Make organisational learning discoverable while tenant-defined visibility protects sensitive detail."],
  ["Tenant-ready foundations", "Give each organisation an isolated workspace, its own configuration, and room to scale on one platform."],
];

const landingSectionVisibility = {
  movement: false,
  signalInterlude: false,
  continuousImprovementStory: false,
} as const;

export default function LandingPage() {
  return (
    <div className={styles.page} id="top">
      <a className={styles.skipLink} href="#main-content">Skip to content</a>

      <header className={styles.header}>
        <Link className={styles.brand} href="/" aria-label="TRANSPIRE home">
          <Image src="/brand/transpire-logo.png" alt="TRANSPIRE, Ideate. Transform. Inspire." width={1400} height={371} priority />
        </Link>
        <nav className={styles.nav} aria-label="Primary navigation">
          {landingSectionVisibility.movement ? <a href="#movement">How ideas move</a> : null}
          <a href="#platform">Platform capabilities</a>
          <a href="#journey">Begin your journey</a>
        </nav>
        <ThemeToggle />
        <Link className={styles.signIn} href="/sign-in" scroll>Sign in <span aria-hidden="true">↗</span></Link>
        <details className={styles.mobileMenu}>
          <summary aria-label="Open navigation"><span /><span /></summary>
          <nav aria-label="Mobile navigation">
            {landingSectionVisibility.movement ? <a href="#movement">How ideas move</a> : null}
            <a href="#platform">Platform capabilities</a>
            <a href="#journey">Begin your journey</a>
            <Link href="/sign-in" scroll>Sign in to TRANSPIRE</Link>
          </nav>
        </details>
      </header>

      <main id="main-content">
        <section className={styles.hero} aria-labelledby="hero-heading">
          <HeroVideo />
          <div className={styles.heroShade} aria-hidden="true" />
          <div className={styles.signalField} aria-hidden="true"><i /><i /><i /></div>
          <div className={styles.heroContent}>
            <p className={styles.eyebrow}>The organisational idea-management platform</p>
            <h1 id="hero-heading"><span>Ideate.</span><span className={styles.red}>Transform.</span><span className={styles.blue}>Inspire.</span></h1>
            <p className={styles.motto}>Transform ideas. Inspire progress.</p>
            <p className={styles.lead}>Make every observation easier to see, strengthen, and move toward meaningful change.</p>
            <div className={styles.actions}>
              <a className={styles.primaryAction} href="#platform">Explore capabilities <span aria-hidden="true">↓</span></a>
              <a className={styles.secondaryAction} href="#journey">Begin your journey</a>
            </div>
          </div>
          <div className={styles.heroFoot}>
            <span>Insight</span><i aria-hidden="true" /><span>Ownership</span><i aria-hidden="true" /><span>Outcome</span>
          </div>
        </section>

        {landingSectionVisibility.movement ? <section className={styles.movement} id="movement" aria-labelledby="movement-heading">
          <Reveal className={styles.movementIntro}>
            <p className={styles.eyebrow}>Momentum with meaning</p>
            <h2 id="movement-heading">A clear path gives an idea the confidence to move.</h2>
            <p>TRANSPIRE connects participation, governance, action, and learning without flattening the context that made the idea matter.</p>
          </Reveal>
          <Reveal className={styles.movementTrack}>
            {movement.map(([number, title, description]) => (
              <article key={number}>
                <span>{number}</span><h3>{title}</h3><p>{description}</p>
              </article>
            ))}
          </Reveal>
        </section> : null}

        {landingSectionVisibility.signalInterlude ? <section className={styles.imageInterlude} aria-label="Ideas becoming shared momentum">
          <div className={styles.interludeImage} aria-hidden="true" />
          <div className={styles.interludeLines} aria-hidden="true"><i /><i /></div>
          <Reveal className={styles.interludeCopy}>
            <p className={styles.eyebrow}>From signal to shared direction</p>
            <h2>Improvement becomes real when the next step is visible.</h2>
          </Reveal>
        </section> : null}

        <section className={styles.platform} id="platform" aria-labelledby="platform-heading">
          <div className={styles.impactBackground} aria-hidden="true" />
          <AmbientBulbVideo className={styles.ambientBulb} />
          <Reveal className={styles.platformHeading}>
            <p className={styles.eyebrow}>Designed to adapt</p>
            <h2 id="platform-heading">One platform for ideas, governance, and measurable improvement.</h2>
            <p className={styles.platformIntro}>TRANSPIRE connects contribution, controlled decision-making, organisational visibility, and tenant-aware administration in one adaptable environment.</p>
          </Reveal>
          <Reveal className={styles.principleList}>
            {principles.map(([title, description], index) => (
              <article key={title}><span>0{index + 1}</span><h3>{title}</h3><p>{description}</p></article>
            ))}
          </Reveal>
        </section>

        {landingSectionVisibility.continuousImprovementStory ? <section className={styles.impact} id="impact" aria-labelledby="impact-heading">
          <div className={styles.impactBackground} aria-hidden="true" />
          <AmbientBulbVideo className={styles.ambientBulb} />
          <Reveal className={styles.impactCopy}>
            <p className={styles.eyebrow}>A continuous improvement story</p>
            <h2 id="impact-heading">See the energy. Guide the work. Prove the change.</h2>
            <p>Ideas become organisational capability when contribution, decisions, action, and outcomes remain connected.</p>
          </Reveal>
        </section> : null}

        <section className={styles.closing} id="journey" aria-labelledby="closing-heading">
          <div className={styles.closingImage} aria-hidden="true" />
          <div className={styles.closingShade} aria-hidden="true" />
          <div className={styles.closingPulse} aria-hidden="true" />
          <Reveal className={styles.closingInner}>
            <p className={styles.eyebrow}>Begin with what you notice</p>
            <h2 id="closing-heading">You can make a change. Begin your journey?</h2>
            <Link href="/sign-in" scroll>Enter TRANSPIRE <span aria-hidden="true">↗</span></Link>
          </Reveal>
        </section>
      </main>

      <EnterpriseFooter journeyHref="#platform" journeyLabel="Platform capabilities" platformHref="#platform" impactHref="#journey" impactLabel="Begin your journey" topHref="#top" />
    </div>
  );
}
