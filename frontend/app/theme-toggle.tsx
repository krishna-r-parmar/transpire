"use client";

import { useSyncExternalStore } from "react";
import { Moon, Sun } from "lucide-react";
import styles from "./landing.module.css";

type Theme = "light" | "dark";

const themeEvent = "transpire-theme-change";

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

export function ThemeToggle() {
  const theme = useSyncExternalStore(subscribe, getTheme, getServerTheme);

  const selectTheme = (selectedTheme: Theme) => {
    if (selectedTheme === theme) return;

    document.documentElement.dataset.theme = selectedTheme;
    try {
      window.localStorage.setItem("transpire-theme", selectedTheme);
    } catch {
      // The selected theme still applies for the current page when storage is unavailable.
    }
    window.dispatchEvent(new Event(themeEvent));
  };

  return (
    <fieldset
      className={styles.themeToggle}
      data-selected-theme={theme}
    >
      <legend className={styles.srOnly}>Colour theme</legend>
      <span className={styles.themeIndicator} aria-hidden="true" />

      <label className={styles.themeOption} title="Light mode">
        <input
          type="radio"
          name="transpire-colour-theme"
          value="light"
          checked={theme === "light"}
          onChange={() => selectTheme("light")}
          aria-label="Use light mode"
        />
        <Sun size={17} strokeWidth={2} aria-hidden="true" />
      </label>

      <label className={styles.themeOption} title="Dark mode">
        <input
          type="radio"
          name="transpire-colour-theme"
          value="dark"
          checked={theme === "dark"}
          onChange={() => selectTheme("dark")}
          aria-label="Use dark mode"
        />
        <Moon size={16} strokeWidth={2} aria-hidden="true" />
      </label>
    </fieldset>
  );
}
