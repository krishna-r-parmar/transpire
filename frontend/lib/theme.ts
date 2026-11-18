"use client";

import { useSyncExternalStore } from "react";

export type Theme = "light" | "dark";

const themeEvent = "transpire-theme-change";
const storageKey = "transpire-theme";

function subscribe(callback: () => void) {
  window.addEventListener(themeEvent, callback);
  return () => window.removeEventListener(themeEvent, callback);
}

function getTheme(): Theme {
  return document.documentElement.dataset.theme === "dark" ? "dark" : "light";
}

function getServerTheme(): Theme {
  return "light";
}

/** The active colour theme. The root layout sets it before paint from the saved choice or the OS setting. */
export function useTheme(): Theme {
  return useSyncExternalStore(subscribe, getTheme, getServerTheme);
}

export function setTheme(theme: Theme) {
  if (getTheme() === theme) return;
  document.documentElement.dataset.theme = theme;
  try {
    window.localStorage.setItem(storageKey, theme);
  } catch {
    // The selected theme still applies for the current page when storage is unavailable.
  }
  window.dispatchEvent(new Event(themeEvent));
}
