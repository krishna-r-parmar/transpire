"use client";

import { Search, X } from "lucide-react";
import styles from "./ui-controls.module.css";

type SearchFieldProps = {
  id: string;
  label: string;
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  resultCount?: number;
};

export function SearchField({ id, label, value, onChange, placeholder = "Search", resultCount }: SearchFieldProps) {
  return (
    <div className={styles.searchField} role="search">
      <label htmlFor={id}>{label}</label>
      <div>
        <Search aria-hidden="true" size={16} />
        <input id={id} type="search" value={value} onChange={(event) => onChange(event.target.value)} placeholder={placeholder} autoComplete="off" />
        {value ? <button type="button" aria-label={`Clear ${label.toLowerCase()}`} onClick={() => onChange("")}><X aria-hidden="true" size={15} /></button> : null}
      </div>
      {typeof resultCount === "number" ? <span aria-live="polite">{resultCount} result{resultCount === 1 ? "" : "s"}</span> : null}
    </div>
  );
}
