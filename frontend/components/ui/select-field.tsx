"use client";

import { Check, ChevronDown, Search } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import styles from "./ui-controls.module.css";

type SelectOption = { value: string; label: string; description?: string };

type SelectFieldProps = {
  id: string;
  label: string;
  name: string;
  value: string;
  options: SelectOption[];
  onChange: (value: string) => void;
  disabled?: boolean;
  invalid?: boolean;
};

export function SelectField({ id, label, name, value, options, onChange, disabled = false, invalid = false }: SelectFieldProps) {
  const root = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const searchInput = useRef<HTMLInputElement>(null);
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const selected = options.find((option) => option.value === value) ?? options[0];
  const visibleOptions = useMemo(() => {
    const term = query.trim().toLocaleLowerCase();
    if (!term) return options;
    return options.filter((option) =>
      `${option.label} ${option.description ?? ""}`.toLocaleLowerCase().includes(term),
    );
  }, [options, query]);

  const close = () => {
    setOpen(false);
    setQuery("");
  };

  useEffect(() => {
    if (!open) return;
    const closeOnOutsideClick = (event: PointerEvent) => {
      if (!root.current?.contains(event.target as Node)) close();
    };
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        close();
        trigger.current?.focus();
      }
    };
    document.addEventListener("pointerdown", closeOnOutsideClick);
    window.addEventListener("keydown", closeOnEscape);
    window.setTimeout(() => searchInput.current?.focus(), 0);
    return () => {
      document.removeEventListener("pointerdown", closeOnOutsideClick);
      window.removeEventListener("keydown", closeOnEscape);
    };
  }, [open]);

  const moveFocus = (event: React.KeyboardEvent<HTMLButtonElement>, index: number) => {
    if (!["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) return;
    event.preventDefault();
    const buttons = root.current?.querySelectorAll<HTMLButtonElement>("[role='option']");
    if (!buttons?.length) return;
    const nextIndex = event.key === "Home" ? 0 : event.key === "End" ? buttons.length - 1 : event.key === "ArrowDown" ? Math.min(index + 1, buttons.length - 1) : Math.max(index - 1, 0);
    buttons[nextIndex]?.focus();
  };

  return (
    <div className={styles.selectField} ref={root}>
      <label id={`${id}-label`} htmlFor={id}>{label}</label>
      <input type="hidden" name={name} value={value} />
      <button
        ref={trigger}
        id={id}
        className={styles.selectTrigger}
        type="button"
        role="combobox"
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={`${id}-options`}
        aria-labelledby={`${id}-label ${id}-value`}
        aria-invalid={invalid}
        disabled={disabled}
        onClick={() => setOpen((current) => !current)}
        onKeyDown={(event) => {
          if (event.key === "ArrowDown" || event.key === "ArrowUp") {
            event.preventDefault();
            setOpen(true);
          }
        }}
      >
        <span id={`${id}-value`}><strong>{selected?.label ?? "Select a role"}</strong><small>{selected?.description ?? "Choose initial access"}</small></span>
        <ChevronDown aria-hidden="true" size={17} />
      </button>
      <div className={styles.selectMenu} data-open={open}>
        <div className={styles.optionSearch}>
          <Search aria-hidden="true" size={15} />
          <input
            ref={searchInput}
            id={`${id}-search`}
            type="search"
            aria-label={`Search ${label.toLocaleLowerCase()}`}
            aria-controls={`${id}-options`}
            value={query}
            placeholder={`Search ${label.toLocaleLowerCase()}`}
            onChange={(event) => setQuery(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "ArrowDown" && visibleOptions.length) {
                event.preventDefault();
                root.current?.querySelector<HTMLButtonElement>("[role='option']")?.focus();
              }
            }}
          />
        </div>
        <div id={`${id}-options`} className={styles.selectOptions} role="listbox" aria-labelledby={`${id}-label`}>
          {visibleOptions.map((option, index) => (
            <button
              key={option.value}
              type="button"
              role="option"
              aria-selected={option.value === value}
              tabIndex={open ? 0 : -1}
              onKeyDown={(event) => moveFocus(event, index)}
              onClick={() => {
                onChange(option.value);
                close();
                trigger.current?.focus();
              }}
            >
              <span><strong>{option.label}</strong>{option.description ? <small>{option.description}</small> : null}</span>
              {option.value === value ? <Check aria-hidden="true" size={16} /> : null}
            </button>
          ))}
          {!visibleOptions.length ? <p>No options match this search.</p> : null}
        </div>
      </div>
    </div>
  );
}
