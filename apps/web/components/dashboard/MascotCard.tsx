"use client";

import Link from "next/link";
import { ScoutMascot } from "@/components/mascot/ScoutMascot";
import { Icon } from "@/components/ui/Icon";
import { useBusinessProfile } from "@/lib/useBusinessProfile";

export function MascotCard({ mascotSrc, happySrc }: { mascotSrc?: string; happySrc?: string }) {
  const profile = useBusinessProfile();
  const customerLabel = (profile?.customer_label ?? "customer").toLowerCase();

  return (
    <section className="mascot-card" aria-labelledby="mascot-heading">
      <div className="hero-copy">
        <span className="eyebrow">A LITTLE OPENING. A BIG DIFFERENCE.</span>
        <h2 id="mascot-heading">An open slot. A new opportunity.</h2>
        <p>Cancel an appointment and watch SlotSaver find, rank, and offer it to the next best {customerLabel} — live.</p>
        <Link className="primary-button" href="/appointments">Open the calendar<Icon name="arrow" /></Link>
      </div>
      <div className="mascot-area">
        <ScoutMascot state="idle" src={mascotSrc ?? ""} stateImages={happySrc ? { happy: happySrc } : undefined} />
      </div>
    </section>
  );
}
