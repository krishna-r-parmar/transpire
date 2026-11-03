import type { Metadata } from "next";
import Image from "next/image";
import Link from "next/link";
import { EnterpriseFooter } from "@/components/landing/enterprise-footer";
import { ThemeToggle } from "../theme-toggle";
import styles from "./privacy.module.css";

export const metadata: Metadata = {
  title: "Privacy Policy | TRANSPIRE",
  description: "How TRANSPIRE collects, uses, shares and protects personal data, and the rights you have over it.",
};

// Confirm these with Legal / the Data Protection Officer before publishing.
const lastUpdated = "3 November 2026";
const contact = {
  entity: "Dishman Carbogen Amcis Ltd.",
  address: "[Registered office address to be confirmed]",
  email: "[Privacy contact email to be confirmed]",
  grievanceOfficer: "[Grievance Officer name to be confirmed]",
  euRepresentative: "[EU / UK representative, if required, to be confirmed]",
};

const sections = [
  ["scope", "About this policy"],
  ["roles", "Who is responsible"],
  ["collect", "Information we collect"],
  ["use", "How we use it and why"],
  ["cookies", "Cookies and device storage"],
  ["share", "Who we share it with"],
  ["transfers", "International transfers"],
  ["retention", "How long we keep it"],
  ["security", "How we protect it"],
  ["rights", "Your rights"],
  ["children", "Children"],
  ["decisions", "Automated decisions"],
  ["changes", "Changes to this policy"],
  ["contact", "Contact and complaints"],
] as const;

export default function PrivacyPage() {
  return (
    <div className={styles.page} id="privacy-top">
      <a className={styles.skipLink} href="#policy">Skip to content</a>
      <header className={styles.header}>
        <Link className={styles.brand} href="/" aria-label="TRANSPIRE home">
          <Image src="/brand/transpire-logo.png" alt="TRANSPIRE, Ideate. Transform. Inspire." width={1400} height={371} priority />
        </Link>
        <ThemeToggle />
        <Link className={styles.signIn} href="/sign-in">Sign in</Link>
      </header>

      <main className={styles.layout} id="policy">
        <div className={styles.titleBlock}>
          <p className={styles.kicker}>Legal</p>
          <h1>Privacy Policy</h1>
          <p className={styles.updated}>Last updated {lastUpdated}</p>
          <p className={styles.summary}>
            TRANSPIRE is a workplace platform for sharing improvement ideas and running the projects that come from them.
            This policy explains what personal data we handle when you use it, why, and the choices and rights you have.
            It is written to meet the EU and UK General Data Protection Regulation (GDPR), India&apos;s Digital Personal Data
            Protection Act, 2023 (DPDP Act) and its Rules, the Swiss Federal Act on Data Protection (FADP), and other data
            protection laws that apply where our users work.
          </p>
        </div>

        <nav className={styles.toc} aria-label="On this page">
          <p>On this page</p>
          <ol>
            {sections.map(([id, label]) => <li key={id}><a href={`#${id}`}>{label}</a></li>)}
          </ol>
        </nav>

        <article className={styles.body}>
          <section id="scope">
            <h2>1. About this policy</h2>
            <p>
              This policy applies to the TRANSPIRE website and application, including the public pages, sign-in, and each
              organisation&apos;s private workspace. It covers employees, contractors and other people who are given access by
              their organisation, and anyone who visits the public pages.
            </p>
            <p>
              It does not cover other services you reach through links from TRANSPIRE, such as your organisation&apos;s own
              sign-in provider, which have their own privacy notices.
            </p>
          </section>

          <section id="roles">
            <h2>2. Who is responsible</h2>
            <p>TRANSPIRE is provided by {contact.entity} (&quot;we&quot;, &quot;us&quot;).</p>
            <ul>
              <li>
                <strong>Your organisation&apos;s workspace.</strong> The organisation that gives you access decides how its workspace is
                used, who can see what, and how long content is kept. For that content it acts as the controller (under GDPR and
                FADP) or Data Fiduciary (under the DPDP Act). Where we host a workspace for an organisation, we process its data on
                its instructions as a processor (or Data Processor).
              </li>
              <li>
                <strong>Running the platform.</strong> For the public pages, account security, and operating and protecting the
                service, we act as controller or Data Fiduciary.
              </li>
            </ul>
            <p>If you are unsure which applies to a question you have, contact us using the details in section 14 and we will direct it.</p>
          </section>

          <section id="collect">
            <h2>3. Information we collect</h2>
            <p>We collect only what we need to provide the service. Most of it comes from you or from your organisation.</p>
            <dl className={styles.dataList}>
              <div><dt>Account and work profile</dt><dd>Name, work email address, employee number, job title, department, site or business unit, your role and permissions in the workspace, and a profile photo if you choose to add one.</dd></div>
              <div><dt>Sign-in and security</dt><dd>How you sign in (for example your organisation&apos;s work account or a password), sign-in times, IP address, browser and device type, and records of failed or unusual sign-in attempts.</dd></div>
              <div><dt>Content you contribute</dt><dd>Ideas, descriptions, evidence, attachments, comments, reviews and decisions, project details, and the expected or realised benefits you record.</dd></div>
              <div><dt>Activity records</dt><dd>A record of significant actions in a workspace, such as who submitted, changed or approved an item and when, so that decisions can be traced.</dd></div>
              <div><dt>Communications and preferences</dt><dd>Notifications sent to you, your notification choices, and display preferences such as light or dark mode.</dd></div>
            </dl>
            <p>
              We do not ask for sensitive personal data, such as health, religion, biometric data or financial account details.
              Please do not include it, or other people&apos;s personal data that is not needed, in ideas or attachments.
            </p>
          </section>

          <section id="use">
            <h2>4. How we use it and why</h2>
            <p>Each use below lists the legal basis we rely on under GDPR and FADP and the ground we rely on under the DPDP Act.</p>
            <div className={styles.tableWrap}>
              <table>
                <thead><tr><th scope="col">Purpose</th><th scope="col">GDPR / FADP basis</th><th scope="col">DPDP Act ground</th></tr></thead>
                <tbody>
                  <tr><td>Create and manage your account, and let you sign in</td><td>Performance of a contract with your organisation; legitimate interests</td><td>Legitimate use for employment purposes, or consent where that does not apply</td></tr>
                  <tr><td>Let you submit, review, approve and deliver ideas and projects</td><td>Legitimate interests of your organisation in running its improvement programme</td><td>Legitimate use for employment purposes</td></tr>
                  <tr><td>Send notifications about items you are involved in</td><td>Legitimate interests</td><td>Legitimate use for employment purposes</td></tr>
                  <tr><td>Keep the service and accounts secure, and investigate misuse</td><td>Legitimate interests; legal obligation</td><td>Legitimate use, including for safeguarding against loss or liability</td></tr>
                  <tr><td>Keep a trail of decisions for accountability and audit</td><td>Legitimate interests; legal obligation</td><td>Legitimate use for employment purposes; compliance with law</td></tr>
                  <tr><td>Report on programme results to your organisation, in aggregated form where possible</td><td>Legitimate interests</td><td>Legitimate use for employment purposes</td></tr>
                  <tr><td>Meet legal, regulatory and court requirements</td><td>Legal obligation</td><td>Compliance with law or court order</td></tr>
                </tbody>
              </table>
            </div>
            <p>
              Where we rely on legitimate interests, we have balanced them against your rights. You can ask us for details of
              that assessment. Where we rely on consent, you can withdraw it at any time, as easily as you gave it. Withdrawal
              does not affect processing that happened before it.
            </p>
            <p>We do not sell personal data, and we do not use it for advertising.</p>
          </section>

          <section id="cookies">
            <h2>5. Cookies and device storage</h2>
            <p>TRANSPIRE uses only what is strictly necessary for the service to work:</p>
            <ul>
              <li>cookies that keep you signed in and protect sign-in and forms against misuse</li>
              <li>a small setting stored in your browser that remembers your light or dark mode choice</li>
            </ul>
            <p>
              We do not use advertising cookies or third-party tracking. Because these items are essential, they do not need your
              consent. You can clear them in your browser, but you will then need to sign in again.
            </p>
          </section>

          <section id="share">
            <h2>6. Who we share it with</h2>
            <ul>
              <li><strong>People in your organisation</strong>, according to the roles and visibility settings your organisation has chosen. Some ideas may be visible across your organisation in its Idea Bank.</li>
              <li><strong>Service providers</strong> who host the platform, deliver email, or provide sign-in services you choose to use. They act only on our instructions, under written contracts that require confidentiality and security.</li>
              <li><strong>Other companies in our group</strong>, where they provide or support the service, under the same protections.</li>
              <li><strong>Professional advisers and auditors</strong>, under duties of confidentiality.</li>
              <li><strong>Authorities, regulators or courts</strong>, where the law requires it or to protect rights, safety or property.</li>
              <li><strong>A successor organisation</strong> in a merger, acquisition or reorganisation, which will remain bound by this policy.</li>
            </ul>
            <p>Workspaces are kept separate, so one organisation cannot see another&apos;s data.</p>
          </section>

          <section id="transfers">
            <h2>7. International transfers</h2>
            <p>
              Our group and providers operate in several countries, so personal data may be processed outside the country where you
              work. When data leaves the EU, UK or Switzerland, we rely on an adequacy decision or on approved safeguards such as the
              European Commission&apos;s Standard Contractual Clauses (with the UK and Swiss addenda), together with additional
              measures where needed. Transfers from India are made only to countries that are not restricted under the DPDP Act. You
              can ask us for a copy of the relevant safeguards.
            </p>
          </section>

          <section id="retention">
            <h2>8. How long we keep it</h2>
            <ul>
              <li><strong>Account data</strong> is kept while you have access. It is deleted or anonymised within a reasonable period after your access ends, unless your organisation needs it for an open matter.</li>
              <li><strong>Ideas, projects and decisions</strong> are kept for as long as your organisation&apos;s retention settings require, because they form part of its improvement records.</li>
              <li><strong>Security and activity records</strong> are kept for a limited period needed to protect the service and meet audit and legal obligations.</li>
            </ul>
            <p>
              When a purpose has been met and no law requires us to keep the data, we delete it or make it anonymous. Under the DPDP
              Act, we erase data when you withdraw consent or when the purpose is no longer being served, unless the law requires us
              to keep it.
            </p>
          </section>

          <section id="security">
            <h2>9. How we protect it</h2>
            <p>
              We use technical and organisational safeguards that are appropriate to the risk. These include encryption in transit,
              access controls based on role, separation between organisations, monitoring for misuse, regular review of our controls,
              and confidentiality duties for staff and providers. No system is completely secure. If a personal data breach occurs,
              we will notify affected people and the relevant authorities as the law requires, including the Data Protection Board
              of India and EU, UK or Swiss supervisory authorities.
            </p>
          </section>

          <section id="rights">
            <h2>10. Your rights</h2>
            <p>Depending on the law that applies to you, you can:</p>
            <ul className={styles.rights}>
              <li><strong>Access</strong> your personal data, and get a summary of how it is processed and who it has been shared with</li>
              <li><strong>Correct</strong> or complete inaccurate data, and update your profile yourself</li>
              <li><strong>Erase</strong> data that is no longer needed or was processed unlawfully</li>
              <li><strong>Restrict</strong> or <strong>object to</strong> processing based on legitimate interests</li>
              <li><strong>Port</strong> data you provided, in a commonly used format</li>
              <li><strong>Withdraw consent</strong> where processing relies on it</li>
              <li><strong>Nominate</strong> another person to exercise your rights if you die or become incapable (DPDP Act)</li>
              <li><strong>Seek redress</strong> for a grievance through our Grievance Officer before going to the Data Protection Board of India</li>
              <li><strong>Complain</strong> to a supervisory authority, such as the authority where you live or work in the EU, the UK Information Commissioner&apos;s Office, or the Swiss Federal Data Protection and Information Commissioner</li>
            </ul>
            <p>
              Residents of US states with privacy laws, such as California, have rights to know, delete and correct their data, and
              we will not discriminate against you for using them. We do not sell or share personal data for cross-context
              behavioural advertising.
            </p>
            <p>
              To use a right, contact your organisation&apos;s TRANSPIRE administrator or us (section 14). We may need to confirm
              your identity. We respond within one month under GDPR and FADP, and within the time set by the DPDP Rules. Where
              your organisation controls the data, we will pass your request to it and help it respond.
            </p>
          </section>

          <section id="children">
            <h2>11. Children</h2>
            <p>TRANSPIRE is a workplace tool for adults. It is not intended for anyone under 18, and we do not knowingly process children&apos;s data.</p>
          </section>

          <section id="decisions">
            <h2>12. Automated decisions</h2>
            <p>
              We do not make decisions about you based only on automated processing that have legal or similarly significant effects.
              Decisions on ideas and projects are made by people in your organisation.
            </p>
          </section>

          <section id="changes">
            <h2>13. Changes to this policy</h2>
            <p>
              We may update this policy when the service or the law changes. We will change the date at the top and, for significant
              changes, tell you in TRANSPIRE or by email before they take effect.
            </p>
          </section>

          <section id="contact">
            <h2>14. Contact and complaints</h2>
            <address className={styles.contact}>
              <span><strong>{contact.entity}</strong></span>
              <span>{contact.address}</span>
              <span>Email: {contact.email}</span>
              <span>Grievance Officer (India): {contact.grievanceOfficer}</span>
              <span>Representative (EU / UK): {contact.euRepresentative}</span>
            </address>
            <p>
              For questions about content in your organisation&apos;s workspace, you can also contact your TRANSPIRE administrator.
              If you are not satisfied with our response, you can complain to the authorities listed in section 10.
            </p>
          </section>
        </article>
      </main>

      <EnterpriseFooter topHref="#privacy-top" />
    </div>
  );
}
