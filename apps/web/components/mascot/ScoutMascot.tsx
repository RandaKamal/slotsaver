"use client";

import Image from "next/image";
import { useState, type ReactNode } from "react";
import styles from "./ScoutMascot.module.css";

export type ScoutState = "idle" | "thinking" | "happy" | "listening" | "celebrating";

export interface ScoutMascotProps {
  state?: ScoutState;
  src?: string;
  stateImages?: Partial<Record<ScoutState, string>>;
  message?: string;
  className?: string;
  children?: ReactNode;
}

const messages: Record<ScoutState, string> = {
  idle: "I’ll keep an eye out for openings.",
  thinking: "Let’s think through the possibilities.",
  happy: "A little hello from Scout!",
  listening: "I’m here when you’re ready.",
  celebrating: "A little moment worth celebrating!",
};

/** Presentational only: callers control workflow state; Scout never starts audio or outreach. */
export function ScoutMascot({
  state = "idle",
  src = "/mascots/slotsaver-bunny.png",
  stateImages,
  message,
  className = "",
  children,
}: ScoutMascotProps) {
  const [failedSources, setFailedSources] = useState<string[]>([]);
  const stateSource = stateImages?.[state];
  const imageSource = stateSource && !failedSources.includes(stateSource) ? stateSource : src;
  const hasImage = Boolean(imageSource) && !failedSources.includes(imageSource);

  return (
    <div className={`${styles.scout} ${className}`} data-state={state}>
      <p className={styles.message} role="status" aria-live="polite" aria-atomic="true">
        <span className={styles.name}>SCOUT</span>
        {message ?? messages[state]}
      </p>
      <div className={styles.stage}>
        <div className={styles.halo} aria-hidden="true" />
        <div className={styles.character}>
          {hasImage ? (
            <Image
              src={imageSource}
              alt="Scout, SlotSaver’s bunny companion"
              width={280}
              height={280}
              className={styles.artwork}
              onError={() => setFailedSources((sources) => sources.includes(imageSource) ? sources : [...sources, imageSource])}
            />
          ) : (
            <div className={styles.placeholder}>
              <span className={styles.wordmark}>Slot<span>Saver</span></span>
              <span>Scout’s spot</span>
              <small>Bunny artwork coming soon</small>
            </div>
          )}
        </div>
        <div key={state} className={styles.accents} aria-hidden="true"><i /><i /><i /></div>
      </div>
      {children}
    </div>
  );
}
