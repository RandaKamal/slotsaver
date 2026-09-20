"use client";

import { useEffect, useState } from "react";
import {
  approveOutreach,
  fetchPendingOutreach,
  rejectOutreach,
  type OutreachAttempt,
} from "@/lib/api";
import styles from "./OutreachQueue.module.css";

/** Owner approval queue for outbound recovery calls.
 *
 * Nemotron has already decided each of these is worth calling about and
 * drafted what the agent should say. Nothing dials out until Approve is
 * clicked here - see docs/twilio-integration.md for what happens after that. */
export function OutreachQueue() {
  const [items, setItems] = useState<OutreachAttempt[] | null>(null);
  const [decided, setDecided] = useState<Record<number, "approved" | "rejected">>({});
  const [busy, setBusy] = useState<number | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    fetchPendingOutreach(controller.signal)
      .then(setItems)
      .catch(() => setFailed(true));
    return () => controller.abort();
  }, []);

  async function act(id: number, action: "approve" | "reject") {
    setBusy(id);
    try {
      await (action === "approve" ? approveOutreach(id) : rejectOutreach(id));
      setDecided((d) => ({ ...d, [id]: action === "approve" ? "approved" : "rejected" }));
    } catch {
      setFailed(true);
    } finally {
      setBusy(null);
    }
  }

  if (failed && !items) {
    return <p className={styles.empty}>Could not reach the outreach queue — is the API running?</p>;
  }
  if (items === null) {
    return <p className={styles.empty}>Loading pending calls…</p>;
  }
  if (items.length === 0) {
    return <p className={styles.empty}>No outbound calls awaiting approval right now.</p>;
  }

  return (
    <div>
      {items.map((item) => {
        const outcome = decided[item.id];
        return (
          <article key={item.id} className={styles.card}>
            <div className={styles.header}>
              <div>
                <h3>{item.patient_id}</h3>
                <p>${item.revenue_at_risk.toFixed(0)} at risk on slot #{item.slot_id}
                  {item.phone_number ? ` · ${item.phone_number}` : " · no phone on file"}</p>
              </div>
              <span className={styles.score}>{Math.round(item.match_score * 100)}% match</span>
            </div>

            <p className={styles.reason}>{item.decision_reason}</p>

            <div className={styles.brief}>
              <span className={styles.tone}>{item.call_brief.tone}</span>
              <p className={styles.opener}>&ldquo;{item.call_brief.opening_line}&rdquo;</p>
              <ul className={styles.points}>
                {item.call_brief.key_points.map((point) => <li key={point}>{point}</li>)}
              </ul>
              {item.call_brief.incentive_pitch && (
                <p className={styles.incentive}>Incentive: {item.call_brief.incentive_pitch}</p>
              )}
            </div>

            {outcome ? (
              <p className={`${styles.done} ${styles[outcome]}`}>
                {outcome === "approved"
                  ? "Approved — call placement is not wired up yet."
                  : "Skipped. No call will be placed."}
              </p>
            ) : (
              <div className={styles.actions}>
                <button
                  type="button"
                  className={styles.approve}
                  disabled={busy === item.id}
                  onClick={() => act(item.id, "approve")}
                >
                  Approve call
                </button>
                <button
                  type="button"
                  className={styles.reject}
                  disabled={busy === item.id}
                  onClick={() => act(item.id, "reject")}
                >
                  Skip
                </button>
              </div>
            )}
          </article>
        );
      })}
    </div>
  );
}
