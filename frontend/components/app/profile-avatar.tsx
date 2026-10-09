"use client";

import Image from "next/image";
import { useEffect, useState } from "react";
import { apiRequest } from "@/lib/api";
import styles from "./profile-avatar.module.css";

export function ProfileAvatar({ name, size = "standard", hasPhoto }: { name: string; size?: "standard" | "large"; hasPhoto?: boolean }) {
  const [photoUrl, setPhotoUrl] = useState("");
  const [revision, setRevision] = useState(0);

  useEffect(() => {
    const refresh = () => setRevision(Date.now());
    window.addEventListener("transpire:profile-photo-updated", refresh);
    return () => window.removeEventListener("transpire:profile-photo-updated", refresh);
  }, []);

  useEffect(() => {
    if (hasPhoto === false) return;
    let active = true;
    let objectUrl = "";
    apiRequest(`/profile/photo?v=${revision}`)
      .then(async (response) => {
        if (!response.ok) { if (active) setPhotoUrl(""); return; }
        objectUrl = URL.createObjectURL(await response.blob());
        if (active) setPhotoUrl(objectUrl);
      })
      .catch(() => undefined);
    return () => { active = false; if (objectUrl) URL.revokeObjectURL(objectUrl); };
  }, [hasPhoto, revision]);

  const visiblePhoto = hasPhoto === false ? "" : photoUrl;

  return <span className={styles.avatar} data-size={size} aria-hidden="true">
    {visiblePhoto ? <Image src={visiblePhoto} alt="" fill sizes={size === "large" ? "88px" : "40px"} unoptimized /> : <strong>{initials(name)}</strong>}
  </span>;
}

function initials(name: string) {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  return (parts.length > 1 ? `${parts[0][0]}${parts.at(-1)?.[0] ?? ""}` : parts[0]?.slice(0, 2) ?? "IN").toUpperCase();
}
