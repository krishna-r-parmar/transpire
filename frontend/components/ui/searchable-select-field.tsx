"use client";

import { Check, ChevronDown, Search, UserRound } from "lucide-react";
import { KeyboardEvent, useEffect, useMemo, useRef, useState } from "react";
import styles from "./ui-controls.module.css";

export type SearchableSelectOption = {
  value: string;
  label: string;
  description?: string;
  status?: "active" | "pending";
};

type SearchableSelectFieldProps = {
  id: string;
  label: string;
  name: string;
  value: string;
  options: SearchableSelectOption[];
  onChange: (value: string) => void;
  placeholder?: string;
  searchPlaceholder?: string;
  emptyMessage?: string;
  disabled?: boolean;
};

export function SearchableSelectField({ id, label, name, value, options, onChange, placeholder = "Select a person", searchPlaceholder = "Search people", emptyMessage = "No people match this search.", disabled = false }: SearchableSelectFieldProps) {
  const root = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const searchInput = useRef<HTMLInputElement>(null);
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const selected = options.find((option) => option.value === value);
  const visible = useMemo(() => {
    const term = query.trim().toLocaleLowerCase();
    return term ? options.filter((option) => `${option.label} ${option.description ?? ""} ${option.status ?? ""}`.toLocaleLowerCase().includes(term)) : options;
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
    const closeOnEscape = (event: globalThis.KeyboardEvent) => {
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

  const focusOption = (index: number) => {
    root.current?.querySelectorAll<HTMLButtonElement>("[role='option']")[index]?.focus();
  };

  const moveOptionFocus = (event: KeyboardEvent<HTMLButtonElement>, index: number) => {
    if (!["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) return;
    event.preventDefault();
    const last = visible.length - 1;
    focusOption(event.key === "Home" ? 0 : event.key === "End" ? last : event.key === "ArrowDown" ? Math.min(index + 1, last) : Math.max(index - 1, 0));
  };

  return <div className={styles.searchableSelect} ref={root}>
    <label id={`${id}-label`} htmlFor={id}>{label}</label>
    <input type="hidden" name={name} value={value} />
    <button ref={trigger} id={id} className={styles.selectTrigger} type="button" aria-haspopup="listbox" aria-expanded={open} aria-labelledby={`${id}-label ${id}-value`} disabled={disabled} onClick={() => setOpen((current) => !current)} onKeyDown={(event) => {
      if (["ArrowDown", "ArrowUp"].includes(event.key)) { event.preventDefault(); setOpen(true); }
    }}>
      <span id={`${id}-value`}><strong>{selected?.label ?? placeholder}</strong><small>{selected?.description ?? (options.length ? "Search active members and pending invitees" : "No assignable people available")}</small></span>
      <span className={styles.selectEnd}>{selected?.status ? <i data-status={selected.status}>{selected.status}</i> : null}<ChevronDown aria-hidden="true" size={17} /></span>
    </button>
    <div className={styles.searchableMenu} data-open={open}>
      <div className={styles.optionSearch}><Search aria-hidden="true" size={15} /><input ref={searchInput} type="search" role="combobox" aria-label={searchPlaceholder} aria-controls={`${id}-options`} aria-expanded={open} aria-autocomplete="list" value={query} placeholder={searchPlaceholder} onChange={(event) => setQuery(event.target.value)} onKeyDown={(event) => { if (event.key === "ArrowDown" && visible.length) { event.preventDefault(); focusOption(0); } }} /></div>
      <div id={`${id}-options`} className={styles.searchableOptions} role="listbox" aria-labelledby={`${id}-label`}>
        {visible.map((option, index) => <button key={option.value} type="button" role="option" aria-selected={option.value === value} tabIndex={open ? 0 : -1} onKeyDown={(event) => moveOptionFocus(event, index)} onClick={() => { onChange(option.value); close(); trigger.current?.focus(); }}><span className={styles.personGlyph}><UserRound aria-hidden="true" size={15} /></span><span><strong>{option.label}</strong>{option.description ? <small>{option.description}</small> : null}</span>{option.status ? <i data-status={option.status}>{option.status}</i> : null}{option.value === value ? <Check aria-hidden="true" size={16} /> : null}</button>)}
        {!visible.length ? <p>{emptyMessage}</p> : null}
      </div>
    </div>
  </div>;
}
