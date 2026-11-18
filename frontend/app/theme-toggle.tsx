"use client";

import { Moon, Sun } from "lucide-react";
import { setTheme, useTheme, type Theme } from "@/lib/theme";
import styles from "./landing.module.css";

export function ThemeToggle() {
  const theme = useTheme();
  const selectTheme = (selectedTheme: Theme) => setTheme(selectedTheme);

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
