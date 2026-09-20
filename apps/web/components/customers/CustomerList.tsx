"use client";

import { useEffect, useState } from "react";
import { fetchCustomers, type CustomerSummary } from "@/lib/api";
import { useBusinessProfile } from "@/lib/useBusinessProfile";
import styles from "./CustomerList.module.css";

export function CustomerList() {
  const profile = useBusinessProfile();
  const customerLabel = profile?.customer_label ?? "Patient";
  const [customers, setCustomers] = useState<CustomerSummary[] | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    fetchCustomers(controller.signal).then(setCustomers).catch(() => setFailed(true));
    return () => controller.abort();
  }, []);

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <p className="eyebrow">{customerLabel.toUpperCase()} MEMORY</p>
        <h1>{customerLabel}s</h1>
      </div>
      <p className={styles.subtitle}>
        Everyone SlotSaver has stored scheduling intent for — the same stored preferences and
        history the voice agent and recovery ranking already read from, in one place.
      </p>
      {failed && <p className={styles.empty}>Could not reach the API.</p>}
      {!failed && customers === null && <p className={styles.empty}>Loading…</p>}
      {customers?.length === 0 && <p className={styles.empty}>No {customerLabel.toLowerCase()}s on file yet.</p>}
      {customers?.map((c) => (
        <article key={c.patient_id} className={styles.card}>
          <div className={styles.cardHeader}>
            <h2>{c.patient_id}</h2>
            <span className={styles.count}>{c.saved_conversations} saved conversation{c.saved_conversations === 1 ? "" : "s"}</span>
          </div>
          {c.latest_said && <p className={styles.said}>&ldquo;{c.latest_said}&rdquo;</p>}
          <p className={styles.brief}>{c.brief}</p>
        </article>
      ))}
    </div>
  );
}
