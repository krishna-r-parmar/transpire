"use client";

import { ArrowLeft, ArrowRight, X } from "lucide-react";
import { useCallback, useEffect, useId, useLayoutEffect, useRef, useState, type ReactNode } from "react";
import { apiRequest } from "@/lib/api";
import styles from "./guided-tour.module.css";

export type TourStep = {
  /** `data-tour` value of the element to highlight. Omit, or leave it unrendered, for a centred card. */
  target?: string;
  title: string;
  body: ReactNode;
};

export type TourId = "platform" | "submit_idea";

const startEvent = "transpire:start-tour";
const PAD = 6;
const GAP = 14;
const CARD_WIDTH = 360;

/** Ask a mounted tour to replay from its first step. */
export function startTour(id: TourId) {
  window.dispatchEvent(new CustomEvent(startEvent, { detail: id }));
}

/**
 * Opens the tour once per version for each person (progress is stored on their account),
 * and again whenever `startTour(id)` is called. Finishing or skipping both count as seen.
 */
export function useTour(id: TourId, version: number, autoStart: boolean) {
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (!autoStart) return;
    let active = true;
    apiRequest("/profile/tours")
      .then(async (response) => response.ok ? (await response.json() as { seen: Record<string, number> }) : null)
      .then((progress) => { if (active && progress && (progress.seen[id] ?? 0) < version) setOpen(true); })
      .catch(() => undefined);
    return () => { active = false; };
  }, [id, version, autoStart]);

  useEffect(() => {
    const onStart = (event: Event) => { if ((event as CustomEvent<TourId>).detail === id) setOpen(true); };
    window.addEventListener(startEvent, onStart);
    return () => window.removeEventListener(startEvent, onStart);
  }, [id]);

  const close = useCallback(() => {
    setOpen(false);
    void apiRequest(`/profile/tours/${id}`, { method: "PUT", body: JSON.stringify({ version }) }).catch(() => undefined);
  }, [id, version]);

  return { open, close };
}

type Rect = { top: number; left: number; width: number; height: number };

function findTarget(target?: string) {
  if (!target) return null;
  const element = document.querySelector<HTMLElement>(`[data-tour="${target}"]`);
  if (!element) return null;
  const rect = element.getBoundingClientRect();
  // Hidden (e.g. the sidebar inside a closed mobile drawer) or off to the side: explain it from the centre instead.
  if (rect.width === 0 || rect.height === 0 || rect.right <= 0 || rect.left >= window.innerWidth) return null;
  return element;
}

type TourProps = { open: boolean; steps: TourStep[]; label: string; onClose: () => void };

/** Mounted only while open, so every replay starts again from the first step. */
export function GuidedTour(props: TourProps) {
  return props.open && props.steps.length ? <TourOverlay {...props} /> : null;
}

function TourOverlay({ steps, label, onClose }: TourProps) {
  const [index, setIndex] = useState(0);
  const [rect, setRect] = useState<Rect | null>(null);
  const card = useRef<HTMLDivElement>(null);
  const [cardHeight, setCardHeight] = useState(0);
  const titleId = useId();
  const bodyId = useId();
  const step = steps[Math.min(index, steps.length - 1)];
  const last = index >= steps.length - 1;

  const measure = useCallback(() => {
    if (card.current) setCardHeight(card.current.offsetHeight);
    const element = findTarget(step?.target);
    if (!element) { setRect(null); return; }
    const box = element.getBoundingClientRect();
    setRect({ top: box.top - PAD, left: box.left - PAD, width: box.width + PAD * 2, height: box.height + PAD * 2 });
  }, [step]);

  useLayoutEffect(() => {
    const element = findTarget(step.target);
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (element) {
      // When the card can't sit beside the target it goes below, so centre the target and the card together.
      const box = element.getBoundingClientRect();
      const fitsBeside = box.right + GAP + CARD_WIDTH + 16 <= window.innerWidth && box.width < window.innerWidth / 2;
      const needed = fitsBeside ? box.height : box.height + GAP + (card.current?.offsetHeight || 260);
      // Only scroll when the target (and its card) doesn't already fit; items in the fixed sidebar never need it.
      if (box.top < 16 || box.top + needed > window.innerHeight - 16) {
        const desiredTop = Math.max(16, (window.innerHeight - needed) / 2);
        window.scrollTo({ top: window.scrollY + box.top - desiredTop, behavior: reduced ? "instant" : "smooth" });
      }
    }
    // Measuring layout before paint is what layout effects are for; waiting a frame would flash the previous highlight.
    measure();
    const frame = window.requestAnimationFrame(measure);
    // Smooth scrolling settles after a few frames; measure again once it has.
    const timer = window.setTimeout(measure, reduced ? 0 : 380);
    card.current?.focus();
    return () => { window.cancelAnimationFrame(frame); window.clearTimeout(timer); };
  }, [step, measure]);

  useEffect(() => {
    const element = card.current;
    if (!element) return;
    const observer = new ResizeObserver(() => setCardHeight(element.offsetHeight));
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    window.addEventListener("resize", measure);
    window.addEventListener("scroll", measure, true);
    return () => { window.removeEventListener("resize", measure); window.removeEventListener("scroll", measure, true); };
  }, [measure]);

  // Hand focus back to wherever the person was once the tour closes. While open, extra room at the
  // bottom of the page lets the last section scroll up far enough for its card to fit underneath.
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    const previousPadding = document.body.style.paddingBottom;
    document.body.style.paddingBottom = "50vh";
    return () => { document.body.style.paddingBottom = previousPadding; previous?.focus?.(); };
  }, []);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") { event.preventDefault(); event.stopPropagation(); onClose(); }
      else if (event.key === "ArrowRight") { event.preventDefault(); if (last) onClose(); else setIndex((value) => value + 1); }
      else if (event.key === "ArrowLeft") { event.preventDefault(); setIndex((value) => Math.max(0, value - 1)); }
      else if (event.key === "Tab" && card.current) {
        const focusable = [...card.current.querySelectorAll<HTMLElement>("button:not([disabled])")];
        if (!focusable.length) return;
        const first = focusable[0], end = focusable[focusable.length - 1];
        if (event.shiftKey && (document.activeElement === first || document.activeElement === card.current)) { event.preventDefault(); end.focus(); }
        else if (!event.shiftKey && document.activeElement === end) { event.preventDefault(); first.focus(); }
      }
    };
    window.addEventListener("keydown", onKeyDown, true);
    return () => window.removeEventListener("keydown", onKeyDown, true);
  }, [last, onClose]);

  return <div className={styles.layer}>
    {/* Blocks clicks on the page while the tour is open; the cut-out only shows the target. */}
    <div className={styles.scrim} data-spotlight={Boolean(rect)} aria-hidden="true" />
    {rect ? <div className={styles.spotlight} style={{ top: rect.top, left: rect.left, width: rect.width, height: rect.height }} aria-hidden="true" /> : null}
    <div
      ref={card}
      className={styles.card}
      data-placement={rect ? "anchored" : "centre"}
      style={rect ? cardPosition(rect, cardHeight) : undefined}
      role="dialog"
      aria-modal="true"
      aria-label={label}
      aria-labelledby={titleId}
      aria-describedby={bodyId}
      tabIndex={-1}
    >
      <header>
        <span className={styles.count}>{index + 1} of {steps.length}</span>
        <button type="button" className={styles.skip} onClick={onClose} aria-label={`Close ${label}`}><X size={16} aria-hidden="true" /></button>
      </header>
      <h2 id={titleId}>{step.title}</h2>
      <div id={bodyId} className={styles.body}>{step.body}</div>
      <footer>
        <ol className={styles.dots} aria-hidden="true">{steps.map((item, dot) => <li key={item.title} data-active={dot === index} data-done={dot < index} />)}</ol>
        <div className={styles.actions}>
          {index === 0
            ? <button type="button" className={styles.secondary} onClick={onClose}>Skip tour</button>
            : <button type="button" className={styles.secondary} onClick={() => setIndex(index - 1)}><ArrowLeft size={15} aria-hidden="true" />Back</button>}
          <button type="button" className={styles.primary} onClick={() => last ? onClose() : setIndex(index + 1)}>{last ? "Finish" : index === 0 ? "Show me" : "Next"}{last ? null : <ArrowRight size={15} aria-hidden="true" />}</button>
        </div>
      </footer>
      <p className={styles.srOnly} aria-live="polite">Step {index + 1} of {steps.length}: {step.title}</p>
    </div>
  </div>;
}

/** Beside the target when there is room (sidebar items), otherwise below or above it. Phones get a bottom sheet via CSS. */
function cardPosition(rect: Rect, height: number) {
  const vw = window.innerWidth, vh = window.innerHeight;
  const width = Math.min(CARD_WIDTH, vw - 32);
  const clampTop = (top: number) => Math.max(16, Math.min(top, vh - height - 16));
  const clampLeft = (left: number) => Math.max(16, Math.min(left, vw - width - 16));
  if (rect.left + rect.width + GAP + width + 16 <= vw && rect.width < vw / 2) {
    return { top: clampTop(rect.top), left: rect.left + rect.width + GAP, width };
  }
  if (rect.top + rect.height + GAP + height + 16 <= vh) {
    return { top: rect.top + rect.height + GAP, left: clampLeft(rect.left), width };
  }
  if (rect.top - GAP - height >= 16) {
    return { top: rect.top - GAP - height, left: clampLeft(rect.left), width };
  }
  return { top: clampTop(vh - height - 16), left: clampLeft(rect.left + rect.width / 2 - width / 2), width };
}
