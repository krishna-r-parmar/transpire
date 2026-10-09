"use client";

import Image from "next/image";
import { usePathname } from "next/navigation";
import { TenantLink as Link } from "@/components/app/tenant-link";
import { useTenantRouter as useRouter } from "@/lib/use-tenant-router";
import { FormEvent, useEffect, useLayoutEffect, useRef, useState, useSyncExternalStore } from "react";
import { apiRequest, apiUrl } from "@/lib/api";
import { tenantPath, tenantSlugFromPathname } from "@/lib/tenant-routing";
import styles from "./sign-in.module.css";

type FieldErrors = {
  email?: string;
  password?: string;
};

type WorkspaceChoice = {
  id: string;
  slug: string;
  name: string;
};

type CentralSignInResult = {
  selection_required: boolean;
  selection_token: string | null;
  workspaces: WorkspaceChoice[];
  session: {
    tenant: WorkspaceChoice;
  } | null;
};

type WorkspaceSelection = {
  token: string | null;
  email: string;
  workspaces: WorkspaceChoice[];
  method: "password" | "sso";
};

const quotes = [
  {
    quote: "Innovation distinguishes between a leader and a follower.",
    name: "Steve Jobs",
    image: "/people/steve-jobs.jpg",
  },
  {
    quote: "There’s a way to do it better. Find it.",
    name: "Thomas Edison",
    image: "/people/thomas-edison.jpg",
  },
  {
    quote: "The value of an idea lies in the using of it.",
    name: "Thomas Edison",
    image: "/people/thomas-edison.jpg",
  },
  {
    quote: "Don’t wait for the perfect solution.",
    name: "Masaaki Imai",
    image: "/people/masaaki-imai.png",
  },
  {
    quote: "Failure is the seed of success.",
    name: "Kaoru Ishikawa",
    image: "/people/kaoru-ishikawa.jpg",
  },
  {
    quote: "The KAIZEN™ Philosophy assumes that our way of life, be it our working life or our home life, deserves to be constantly improved.",
    name: "Masaaki Imai",
    image: "/people/masaaki-imai.png",
  },
  {
    quote: "Improvement usually means doing something that we have never done before.",
    name: "Shigeo Shingo",
    image: "/people/shigeo-shingo.jpg",
  },
] as const;

const subscribeToHydration = () => () => undefined;

function MicrosoftMark() {
  return (
    <svg aria-hidden="true" viewBox="0 0 23 23" width="19" height="19">
      <path fill="#F25022" d="M1 1h10v10H1z" />
      <path fill="#7FBA00" d="M12 1h10v10H12z" />
      <path fill="#00A4EF" d="M1 12h10v10H1z" />
      <path fill="#FFB900" d="M12 12h10v10H12z" />
    </svg>
  );
}

export function SignInPortal({ returnedWithSSOError = false, selectingSSOWorkspace = false }: { returnedWithSSOError?: boolean; selectingSSOWorkspace?: boolean }) {
  const router = useRouter();
  const pathname = usePathname();
  const tenantSlug = tenantSlugFromPathname(pathname);
  const hydrated = useSyncExternalStore(subscribeToHydration, () => true, () => false);
  const videoRef = useRef<HTMLVideoElement>(null);
  const [showPassword, setShowPassword] = useState(false);
  const [playing, setPlaying] = useState(true);
  const [quoteIndex, setQuoteIndex] = useState(0);
  const [quotePaused, setQuotePaused] = useState(false);
  const [reduceMotion, setReduceMotion] = useState(false);
  const [loading, setLoading] = useState(selectingSSOWorkspace);
  const [errors, setErrors] = useState<FieldErrors>({});
  const [message, setMessage] = useState(returnedWithSSOError ? "Microsoft sign-in could not be completed. Confirm you used the work account registered for this organisation, then try again." : "");
  const [messageTone, setMessageTone] = useState<"info" | "error">(returnedWithSSOError ? "error" : "info");
  const [workspaceSelection, setWorkspaceSelection] = useState<WorkspaceSelection | null>(null);
  const [ssoEnabled, setSsoEnabled] = useState(false);
  const [checkingSSO, setCheckingSSO] = useState(Boolean(tenantSlug));
  const [rememberMe, setRememberMe] = useState(false);

  useLayoutEffect(() => {
    const root = document.documentElement;
    const previousScrollBehavior = root.style.scrollBehavior;

    root.style.scrollBehavior = "auto";
    window.scrollTo(0, 0);
    root.style.scrollBehavior = previousScrollBehavior;
  }, []);

  useEffect(() => {
    const motionPreference = window.matchMedia("(prefers-reduced-motion: reduce)");
    const syncPreference = () => {
      setReduceMotion(motionPreference.matches);
      if (motionPreference.matches) {
        videoRef.current?.pause();
        setPlaying(false);
      }
    };

    syncPreference();
    motionPreference.addEventListener("change", syncPreference);
    return () => motionPreference.removeEventListener("change", syncPreference);
  }, []);

  useEffect(() => {
    if (reduceMotion || quotePaused || !playing) return;

    const rotation = window.setInterval(() => {
      setQuoteIndex((current) => (current + 1) % quotes.length);
    }, 7000);

    return () => window.clearInterval(rotation);
  }, [playing, quotePaused, reduceMotion]);

  useEffect(() => {
    if (!tenantSlug) return;
    let active = true;
    apiRequest("/auth/sso/status")
      .then(async (response) => response.ok ? await response.json() as { enabled: boolean } : { enabled: false })
      .then((result) => { if (active) setSsoEnabled(result.enabled); })
      .catch(() => undefined)
      .finally(() => { if (active) setCheckingSSO(false); });
    return () => { active = false; };
  }, [tenantSlug]);

  useEffect(() => {
    if (!selectingSSOWorkspace || tenantSlug) return;
    let active = true;
    apiRequest("/auth/sso/global/workspaces")
      .then(async (response) => {
        if (!response.ok) throw new Error("Selection expired");
        return await response.json() as WorkspaceChoice[];
      })
      .then((workspaces) => {
        if (!active) return;
        if (workspaces.length < 2) throw new Error("No workspace selection available");
        setWorkspaceSelection({
          token: null,
          email: "your Microsoft account",
          workspaces,
          method: "sso",
        });
      })
      .catch(() => {
        if (!active) return;
        setMessageTone("error");
        setMessage("Your Microsoft workspace selection expired. Please sign in again.");
      })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [selectingSSOWorkspace, tenantSlug]);

  const toggleFilm = async () => {
    const video = videoRef.current;
    if (!video) return;

    if (video.paused) {
      try {
        await video.play();
      } catch {
        setPlaying(false);
      }
    } else {
      video.pause();
    }
  };

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setMessage("");

    const form = new FormData(event.currentTarget);
    const email = String(form.get("email") ?? "").trim();
    const password = String(form.get("password") ?? "");
    const nextErrors: FieldErrors = {};

    if (!email) {
      nextErrors.email = "Enter your work email address.";
    } else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
      nextErrors.email = "Enter a valid work email address.";
    }

    if (!password) {
      nextErrors.password = "Enter your password.";
    }

    setErrors(nextErrors);
    if (Object.keys(nextErrors).length > 0) return;

    setLoading(true);
    try {
      const response = await apiRequest("/auth/sign-in", {
        method: "POST",
        body: JSON.stringify({
          email,
          password,
          remember_me: form.get("remember") === "on",
          preferred_tenant_slug: tenantSlugFromPathname(pathname),
        }),
      });

      if (!response.ok) {
        setMessageTone("error");
        setMessage(
          response.status === 401
            ? "Email or password is incorrect."
            : response.status === 429
              ? "Too many sign-in attempts. Please wait a few minutes and try again."
              : "Sign-in is temporarily unavailable. Please try again.",
        );
        return;
      }

      const result = await response.json() as CentralSignInResult;
      if (result.session) {
        router.replace(tenantPath(result.session.tenant.slug, "/home"));
        return;
      }
      if (result.selection_required && result.selection_token && result.workspaces.length > 0) {
        setWorkspaceSelection({
          token: result.selection_token,
          email,
          workspaces: result.workspaces,
          method: "password",
        });
        setMessage("");
        return;
      }
      setMessageTone("error");
      setMessage("Sign-in could not be completed. Please try again.");
    } catch {
      setMessageTone("error");
      setMessage("Sign-in is temporarily unavailable. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  const handleWorkspaceSelection = async (workspace: WorkspaceChoice) => {
    if (!workspaceSelection) return;
    setLoading(true);
    setMessage("");
    try {
      const ssoSelection = workspaceSelection.method === "sso";
      const response = await apiRequest(ssoSelection ? "/auth/sso/global/select-workspace" : "/auth/select-workspace", {
        method: "POST",
        body: JSON.stringify({
          ...(workspaceSelection.token ? { selection_token: workspaceSelection.token } : {}),
          tenant_id: workspace.id,
        }),
      });
      if (!response.ok) {
        setMessageTone("error");
        setMessage("Your secure selection expired. Please sign in again.");
        setWorkspaceSelection(null);
        return;
      }
      if (ssoSelection) {
        const result = await response.json() as NonNullable<CentralSignInResult["session"]>;
        router.replace(tenantPath(result.tenant.slug, "/home"));
      } else {
        const result = await response.json() as CentralSignInResult;
        if (!result.session) throw new Error("Missing session");
        router.replace(tenantPath(result.session.tenant.slug, "/home"));
      }
    } catch {
      setMessageTone("error");
      setMessage("Sign-in is temporarily unavailable. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  const handleMicrosoftSignIn = () => {
    setErrors({});
    setLoading(true);
    const endpoint = tenantSlug ? "/auth/sso/start" : "/auth/sso/global/start";
    window.location.assign(apiUrl(`${endpoint}?remember_me=${rememberMe ? "true" : "false"}`));
  };

  return (
    <main className={styles.page} id="sign-in-top">
      <a className={styles.skipLink} href="#sign-in-form">Skip to sign-in form</a>

      <section className={styles.formSide} aria-labelledby="sign-in-heading">
        <header className={styles.formHeader}>
          <Link href="/" className={styles.brand} aria-label="Return to TRANSPIRE home">
            <Image
              src="/brand/transpire-logo.png"
              alt="TRANSPIRE, Ideate. Transform. Inspire."
              width={1400}
              height={371}
              priority
            />
          </Link>
          <Link className={styles.backLink} href="/">Back to website <span aria-hidden="true">↗</span></Link>
        </header>

        <div className={styles.formShell}>
          <div className={styles.formIntro}>
            <p className={styles.eyebrow}>Secure organisational access</p>
            <h1 id="sign-in-heading">{workspaceSelection ? "Choose your organisation" : "Welcome back"}</h1>
            <p>
              {workspaceSelection
                ? `Your account belongs to more than one organisation. Continue as ${workspaceSelection.email}.`
                : ssoEnabled
                  ? "Continue securely with your organisation's Microsoft account."
                  : "Sign in to continue to your TRANSPIRE workspace."}
            </p>
          </div>

          <form
            action="/sign-in"
            className={styles.form}
            id="sign-in-form"
            method="post"
            noValidate
            aria-busy={!hydrated || loading}
            onSubmit={handleSubmit}
          >
            {message ? (
              <div className={styles.status} data-tone={messageTone} role="status">
                <span aria-hidden="true">{messageTone === "error" ? "!" : "i"}</span>
                <p>{message}</p>
              </div>
            ) : null}

            {workspaceSelection ? (
              <div className={styles.workspaceChoices}>
                {workspaceSelection.workspaces.map((workspace) => (
                  <button
                    className={styles.workspaceChoice}
                    type="button"
                    key={workspace.id}
                    disabled={loading}
                    onClick={() => handleWorkspaceSelection(workspace)}
                  >
                    <span>
                      <strong>{workspace.name}</strong>
                      <small>{workspace.slug}</small>
                    </span>
                    <span aria-hidden="true">→</span>
                  </button>
                ))}
                <button
                  className={styles.changeAccount}
                  type="button"
                  disabled={loading}
                  onClick={() => {
                    setWorkspaceSelection(null);
                    setMessage("");
                  }}
                >
                  Use another account
                </button>
              </div>
            ) : ssoEnabled ? <div className={styles.ssoOnly}>
              <button className={styles.microsoft} type="button" onClick={handleMicrosoftSignIn} disabled={checkingSSO || loading}>
                <MicrosoftMark />
                <span>{loading ? "Connecting to Microsoft" : "Continue with Microsoft"}</span>
              </button>
              <p className={styles.ssoNote}>Password sign-in is no longer used for this organisation. Your TRANSPIRE work and access remain unchanged.</p>
            </div> : <>
            <div className={styles.field} data-invalid={Boolean(errors.email)}>
              <label htmlFor="work-email">Work email</label>
              <input
                id="work-email"
                name="email"
                type="email"
                inputMode="email"
                autoComplete="username"
                placeholder="name@company.com"
                aria-invalid={Boolean(errors.email)}
                aria-describedby={errors.email ? "email-error" : undefined}
                disabled={!hydrated || loading}
                onChange={() => {
                  if (errors.email) setErrors((current) => ({ ...current, email: undefined }));
                }}
              />
              {errors.email ? <p className={styles.error} id="email-error">{errors.email}</p> : null}
            </div>

            <div className={styles.field} data-invalid={Boolean(errors.password)}>
              <div className={styles.labelRow}>
                <label htmlFor="password">Password</label>
                <Link href="/forgot-password">Forgot password?</Link>
              </div>
              <div className={styles.passwordWrap}>
                <input
                  id="password"
                  name="password"
                  type={showPassword ? "text" : "password"}
                  autoComplete="current-password"
                  placeholder="Enter your password"
                  aria-invalid={Boolean(errors.password)}
                  aria-describedby={errors.password ? "password-error" : undefined}
                  disabled={!hydrated || loading}
                  onChange={() => {
                    if (errors.password) setErrors((current) => ({ ...current, password: undefined }));
                  }}
                />
                <button
                  className={styles.passwordToggle}
                  type="button"
                  disabled={!hydrated || loading}
                  onClick={() => setShowPassword((visible) => !visible)}
                  aria-label={showPassword ? "Hide password" : "Show password"}
                  aria-pressed={showPassword}
                >
                  {showPassword ? "Hide" : "Show"}
                </button>
              </div>
              {errors.password ? <p className={styles.error} id="password-error">{errors.password}</p> : null}
            </div>

            <label className={styles.remember}>
              <input name="remember" type="checkbox" checked={rememberMe} disabled={!hydrated || loading} onChange={(event) => setRememberMe(event.target.checked)} />
              <span>Keep me signed in on this device</span>
            </label>

            <button className={styles.submit} type="submit" disabled={!hydrated || loading}>
              <span className={loading ? styles.loadingText : undefined}>
                {!hydrated ? "Preparing sign-in" : loading ? "Signing in" : "Sign in"}
              </span>
              {loading ? <i aria-hidden="true" /> : <span aria-hidden="true">→</span>}
            </button>

            <div className={styles.divider}><span>or</span></div>

            <button className={styles.microsoft} type="button" onClick={handleMicrosoftSignIn} disabled={checkingSSO}>
              <MicrosoftMark />
              <span>Continue with Microsoft</span>
            </button>

            <p className={styles.ssoNote}>{checkingSSO ? "Checking your organisation's sign-in method." : "Available when Microsoft SSO is enabled for your organisation."}</p>
            </>}
          </form>

          <div className={styles.help}>
            <span aria-hidden="true">?</span>
            <p>Having trouble signing in? Contact your organisation&apos;s TRANSPIRE administrator.</p>
          </div>
        </div>

        <p className={styles.formLegal}>Protected organisational access · Privacy and security controls apply</p>
      </section>

      <aside className={styles.visual} aria-label="TRANSPIRE brand story">
        <video
          ref={videoRef}
          aria-hidden="true"
          autoPlay
          muted
          loop
          playsInline
          poster="/brand/transpire-v2-background.png"
          onPlay={() => setPlaying(true)}
          onPause={() => setPlaying(false)}
        >
          <source src="/video/transpire-hero.mp4" type="video/mp4" />
        </video>
        <div className={styles.visualShade} aria-hidden="true" />
        <div className={styles.signalLine} aria-hidden="true"><i /><i /><i /></div>
        <div
          className={styles.quoteStage}
          onMouseEnter={() => setQuotePaused(true)}
          onMouseLeave={() => setQuotePaused(false)}
          onFocusCapture={() => setQuotePaused(true)}
          onBlurCapture={(event) => {
            if (!event.currentTarget.contains(event.relatedTarget)) setQuotePaused(false);
          }}
        >
          <p className={styles.quoteEyebrow}>Ideas that move us forward</p>
          <figure className={styles.quote} key={quoteIndex}>
            <blockquote data-long={quotes[quoteIndex].quote.length > 100}>
              <span aria-hidden="true">“</span>
              {quotes[quoteIndex].quote}
              <span aria-hidden="true">”</span>
            </blockquote>
            <figcaption>
              <Image
                src={quotes[quoteIndex].image}
                alt={`Portrait of ${quotes[quoteIndex].name}`}
                width={112}
                height={112}
                sizes="56px"
              />
              <span>
                <strong>{quotes[quoteIndex].name}</strong>
                <small>On continuous improvement</small>
              </span>
            </figcaption>
          </figure>
          <div className={styles.quoteNavigation} aria-label="Choose an inspirational quote">
            <span aria-hidden="true">{String(quoteIndex + 1).padStart(2, "0")}</span>
            <div>
              {quotes.map((item, index) => (
                <button
                  type="button"
                  key={`${item.name}-${index}`}
                  data-active={index === quoteIndex}
                  onClick={() => setQuoteIndex(index)}
                  aria-label={`Show quote ${index + 1} by ${item.name}`}
                  aria-current={index === quoteIndex ? "true" : undefined}
                />
              ))}
            </div>
            <span aria-hidden="true">{String(quotes.length).padStart(2, "0")}</span>
          </div>
        </div>
        <button
          className={styles.filmControl}
          type="button"
          onClick={toggleFilm}
          aria-label={playing ? "Pause background film and quote rotation" : "Play background film and quote rotation"}
        >
          <span aria-hidden="true">{playing ? "Ⅱ" : "▶"}</span>
          {playing ? "Pause motion" : "Play motion"}
        </button>
      </aside>
    </main>
  );
}
