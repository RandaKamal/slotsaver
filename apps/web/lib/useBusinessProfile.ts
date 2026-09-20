"use client";

import { useEffect, useState } from "react";
import { fetchActiveBusinessProfile, type BusinessProfile } from "@/lib/api";

const POLL_MS = 5000;

/** The active business profile, polled so switching it in Settings (or from
 *  another tab) updates labels, hours, provider/service lists and booking
 *  constraints here without a page reload. `null` means unreachable/loading -
 *  callers fall back to generic defaults, never invented clinic data. */
export function useBusinessProfile(): BusinessProfile | null {
  const [profile, setProfile] = useState<BusinessProfile | null>(null);

  useEffect(() => {
    let stopped = false;
    const poll = () =>
      fetchActiveBusinessProfile()
        .then((p) => { if (!stopped) setProfile(p); })
        .catch(() => { if (!stopped) setProfile(null); });
    poll();
    const id = setInterval(poll, POLL_MS);
    return () => { stopped = true; clearInterval(id); };
  }, []);

  return profile;
}
