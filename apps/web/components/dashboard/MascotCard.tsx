"use client";

import { useEffect, useState } from "react";
import { ScoutMascot } from "@/components/mascot/ScoutMascot";
import { Icon } from "@/components/ui/Icon";

export function MascotCard({ mascotSrc, happySrc }: { mascotSrc?: string; happySrc?: string }) {
  const [showNotice, setShowNotice] = useState(false);
  const [greeting, setGreeting] = useState(false);

  useEffect(() => {
    if (!greeting) return;
    const timeout = window.setTimeout(() => setGreeting(false), 2400);
    return () => window.clearTimeout(timeout);
  }, [greeting]);

  return (
    <section className="mascot-card" aria-labelledby="mascot-heading">
      <div className="hero-copy">
        <span className="eyebrow">A LITTLE OPENING. A BIG DIFFERENCE.</span>
        <h2 id="mascot-heading">An open slot.<br /><span>A new opportunity.</span></h2>
        <p>Ready to recover your next cancellation. Help patients get care sooner, one opening at a time.</p>
        <button className="primary-button" type="button" aria-expanded={showNotice} aria-controls="cancellations-notice" onClick={() => setShowNotice(!showNotice)}>View Cancellations<Icon name="arrow" /></button>
        <p id="cancellations-notice" className="cta-notice" role="status" hidden={!showNotice}>Your cancellation list is coming next. This preview is not connected to your clinic&apos;s schedule.</p>
      </div>
      <div className="mascot-area">
        <ScoutMascot
          state={greeting ? "happy" : "idle"}
          src={mascotSrc ?? ""}
          stateImages={happySrc ? { happy: happySrc } : undefined}
        >
          <button className="scout-greeting" type="button" onClick={() => setGreeting(true)} disabled={greeting}>
            {greeting ? "Scout says hello!" : "Say hello to Scout"}
          </button>
        </ScoutMascot>
      </div>
    </section>
  );
}
