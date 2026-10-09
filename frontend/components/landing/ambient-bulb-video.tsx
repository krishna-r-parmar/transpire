"use client";

import Image from "next/image";
import { useEffect, useRef } from "react";
import styles from "./ambient-bulb-video.module.css";

type AmbientBulbVideoProps = {
  className?: string;
};

export function AmbientBulbVideo({ className = "" }: AmbientBulbVideoProps) {
  const videoRef = useRef<HTMLVideoElement>(null);

  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;

    const motionPreference = window.matchMedia("(prefers-reduced-motion: reduce)");
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (motionPreference.matches || !entry.isIntersecting) {
          video.pause();
          return;
        }
        void video.play().catch(() => undefined);
      },
      { rootMargin: "160px", threshold: 0.08 },
    );

    observer.observe(video);
    return () => observer.disconnect();
  }, []);

  return (
    <div className={`${styles.media} ${className}`} aria-hidden="true">
      <Image src="/brand/transpire-hero.png" alt="" fill loading="eager" sizes="(max-width: 767px) 100vw, 64vw" />
      <video ref={videoRef} muted loop playsInline preload="metadata" poster="/brand/transpire-hero.png">
        <source src="/video/transpire-bulb.mp4" type="video/mp4" />
      </video>
    </div>
  );
}
