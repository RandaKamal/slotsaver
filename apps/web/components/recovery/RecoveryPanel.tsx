"use client";

import { useEffect, useRef, useState } from "react";
import { approveOutreach, fetchRecoveryPlanBySlot, recoverFromCancellation, respondToRecoveryPlan, type RecoveryPlan } from "@/lib/api";
import { dateLabel, timeLabel, type Appointment } from "@/components/appointments/appointment-data";
import { Icon } from "@/components/ui/Icon";
import { sampleCandidates } from "./mock-data";
import styles from "./RecoveryPanel.module.css";

const POLL_MS = 2000;

interface RecoveryPanelProps {
  appointment: Appointment;
  /** Backend slot id. Present for real rows; absent for locally-created ones,
   *  which have no server record and therefore fall back to sample data. */
  slotId?: number;
  onClose: () => void;
}

function candidateStatusLabel(status: string | undefined): string {
  switch (status) {
    case "accepted": return "Accepted ✓";
    case "declined": return "Declined";
    case "expired": return "Timed out";
    case "offered": return "Calling now";
    default: return "Not yet offered";
  }
}

export function RecoveryPanel({ appointment, slotId, onClose }: RecoveryPanelProps) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [plan, setPlan] = useState<RecoveryPlan | null>(null);
  const [loading, setLoading] = useState(slotId !== undefined);
  const [failed, setFailed] = useState(false);
  const [triggering, setTriggering] = useState(false);
  const [callState, setCallState] = useState<"idle" | "calling" | "placed" | "not_configured" | "failed">("idle");
  const [accepting, setAccepting] = useState(false);
  const [rearranged, setRearranged] = useState(false);
  const [declining, setDeclining] = useState(false);

  useEffect(() => { dialog.current?.showModal(); }, []);

  // Live, real backend state - not a one-shot trigger. The autonomous
  // scheduler (or a live phone cancellation) may already be running this
  // recovery; this just polls for whatever it's doing, same as the
  // calendar's own open-slot polling. Nemotron ranks whoever survives the
  // deterministic eligibility filter; see recovery_matcher.py.
  useEffect(() => {
    if (slotId === undefined) return;
    let live = true;
    const poll = () => fetchRecoveryPlanBySlot(slotId)
      .then((result) => { if (live) { setPlan(result); setFailed(false); } })
      .catch(() => { if (live) setFailed(true); })
      .finally(() => { if (live) setLoading(false); });
    poll();
    const id = setInterval(poll, POLL_MS);
    return () => { live = false; clearInterval(id); };
  }, [slotId]);

  async function triggerNow() {
    if (slotId === undefined) return;
    setTriggering(true);
    try {
      const result = await recoverFromCancellation(slotId);
      setPlan(result);
      setFailed(false);
    } catch {
      setFailed(true);
    } finally {
      setTriggering(false);
    }
  }

  /** The candidate said no on the call. Nothing captures that today - a
   *  live decline doesn't reach the state machine, so the offer would sit
   *  until its timeout elapsed before anyone else was tried. Recording it
   *  here advances to the next candidate immediately, which is also what
   *  authorizes the incentive on that next offer (recovery_rules
   *  .incentive_from_attempt). */
  async function markDeclined(planId: string) {
    setDeclining(true);
    try {
      const result = await respondToRecoveryPlan(planId, "declined");
      setPlan(result);
      setCallState("idle");
      setFailed(false);
    } catch {
      setFailed(true);
    } finally {
      setDeclining(false);
    }
  }

  async function acceptRearrangement(planId: string) {
    setAccepting(true);
    try {
      const result = await respondToRecoveryPlan(planId, "accepted");
      setPlan(result);
      setRearranged(true);
      setFailed(false);
    } catch {
      setFailed(true);
    } finally {
      setAccepting(false);
    }
  }

  async function callNow(outreachId: number) {
    setCallState("calling");
    try {
      const attempt = await approveOutreach(outreachId);
      // "approved" (not "placed") means the approval was recorded but
      // ElevenLabs/Twilio env vars aren't set yet - a config gap, not a
      // failed call attempt. See call_service.CallNotConfigured.
      setCallState(
        attempt.status === "placed" ? "placed"
          : attempt.status === "approved" ? "not_configured"
          : "failed",
      );
    } catch {
      setCallState("failed");
    }
  }

  // Real ranking when we have it; clearly-labelled fixtures when we don't
  // (locally-created slots have no server row for the backend to recover).
  //
  // A plan whose ranking FAILED still carries candidates - the deterministic
  // eligibility list, which is real and worth showing - but those rows have
  // no match_score or reason, because only Nemotron produces those. Scoring
  // undefined gave "NaN%"; these stay null and render as "not ranked yet"
  // rather than inventing a number the model never returned.
  const rankingFailed = plan?.status === "ranking_failed";
  const live = plan?.candidates?.length
    ? plan.candidates.map((c) => ({
        id: c.patient_id,
        name: c.patient_id,
        initials: c.patient_id.slice(0, 2).toUpperCase(),
        score: typeof c.match_score === "number" ? Math.round(c.match_score * 100) : null,
        reasons: c.reason ? [c.reason] : [],
      }))
    : null;
  const candidates: { id: string; name: string; initials: string; score: number | null; reasons: string[] }[] =
    live ?? sampleCandidates(appointment);
  const isLive = live !== null;
  const first = candidates[0];
  const ranked = plan?.ranked_candidate_ids ?? [];
  const statuses = plan?.candidate_statuses ?? {};
  const currentIndex = plan?.current_candidate_index ?? 0;
  const currentPatientId = ranked[currentIndex];
  const currentRaw = isLive ? plan?.candidates?.find((c) => c.patient_id === currentPatientId) : undefined;
  const rearrangeFromWhen = currentRaw?.currently_booked_start
    ? new Date(currentRaw.currently_booked_start).toLocaleString("en-US", { weekday: "short", hour: "numeric", minute: "2-digit" })
    : "a different time";
  // Awaiting the first plan: a real state right after a fresh cancellation,
  // not a failure - the scheduler ticks every few seconds.
  const awaitingPlan = slotId !== undefined && !loading && plan === null;

  return (
    <dialog ref={dialog} className={styles.panel} aria-labelledby="recovery-title" aria-describedby="recovery-disclaimer" onClose={onClose}>
      <header className={styles.header}>
        <div><p className={styles.eyebrow}>MAKE ROOM FOR AN EARLIER VISIT</p><h2 id="recovery-title">Recovery plan</h2></div>
        <button type="button" className={styles.close} aria-label="Close recovery panel" onClick={() => dialog.current?.close()}>×</button>
      </header>
      <p id="recovery-disclaimer" className={styles.disclaimer}>{isLive
        ? <><strong>Live recovery.</strong> Ranking, calls, timeouts and incentives shown here are the real backend state, polled every couple seconds — not a simulation.</>
        : <><strong>Demo only.</strong> Patient matches and scores are sample data. No calls or messages will be sent.</>}</p>
      <ol className={styles.steps} aria-label="Recovery progress">
        <li>1 <span>Opening identified</span></li>
        <li aria-current={!plan?.candidates?.length ? "step" : undefined} className={!plan?.candidates?.length ? styles.current : ""}>2 <span>{isLive ? "Ranking candidates" : "Sample matches"}</span></li>
        <li aria-current={plan?.candidates?.length ? "step" : undefined} className={plan?.candidates?.length ? styles.current : ""}>3 <span>{isLive ? "Live recovery" : "Demo only"}</span></li>
      </ol>
      <section className={styles.opening} aria-label="Cancelled appointment opening">
        <span className={styles.slotIcon}><Icon name="calendar" /></span>
        <div><h3>{appointment.visitType} · {appointment.duration} minutes</h3><p>{dateLabel(appointment.date, { weekday: "short", month: "short", day: "numeric", year: "numeric" })} at {timeLabel(appointment.time)}</p><p>{appointment.provider} · Cancelled by {appointment.patient}</p></div>
        <span className={styles.badge}>Open slot</span>
      </section>
      <div className={styles.sectionTitle}><h3>Patients who could be a fit</h3><span>{loading ? "loading…" : `${candidates.length} ${rankingFailed ? "eligible, unranked" : isLive ? "matches" : "sample matches"}`}</span></div>
      <p className={styles.caption}>{loading
        ? "Checking the live recovery plan for this slot…"
        : rankingFailed
          ? "Eligibility ran and these patients qualify, but Nemotron could not rank them — no scores or ordering below. The scheduler retries on its own."
          : isLive
            ? "Ranked by Nemotron. Patients who fail a hard constraint were removed before ranking."
            : "Ranked examples of how patient preferences can be explained."}</p>
      {failed && <p className={styles.caption}>Could not reach the recovery API — showing sample data instead.</p>}
      {awaitingPlan && <p className={styles.status} role="status">
        No cancellation recovery has started for this slot yet — the autonomous scheduler ticks every few seconds.{" "}
        <button type="button" className={styles.secondary} onClick={triggerNow} disabled={triggering}>{triggering ? "Starting…" : "Trigger recovery now"}</button>
      </p>}
      {isLive && plan?.excluded?.length ? (
        <ul className={styles.caption} aria-label="Patients excluded before ranking">
          {plan.excluded.map((e) => <li key={e.patient_id}>Excluded {e.patient_id} — {e.reason}</li>)}
        </ul>
      ) : null}
      <ol className={styles.candidates} aria-label={isLive ? "Ranked patients, live status" : "Ranked sample patients"}>
        {candidates.map((candidate, index) => <li key={candidate.id} className={styles.candidate}>
          <span className={styles.rank}>{index + 1}</span><span className={styles.avatar} aria-hidden="true">{candidate.initials}</span>
          <div className={styles.candidateBody}><h4>{candidate.name}{index === 0 && !rankingFailed && <span className={styles.topMatch}>{isLive ? "Top match" : "Top sample match"}</span>}{isLive && !rankingFailed && <span className={styles.badge}>{candidateStatusLabel(statuses[candidate.id])}</span>}</h4><ul>{candidate.reasons.map((reason) => <li key={reason}><span aria-hidden="true">✓</span>{reason}</li>)}</ul></div>
          <div className={styles.score}><strong>{candidate.score === null ? "—" : `${candidate.score}%`}</strong><span>{candidate.score === null ? "Not ranked" : isLive ? "Match score" : "Example score"}</span></div>
        </li>)}
      </ol>
      {isLive && plan?.status === "pending" && currentRaw?.currently_booked_slot_id && <div className={styles.status} role="status">
        <p><strong>Rearrange calendar?</strong> {currentPatientId} is already booked {rearrangeFromWhen}, but their stored preference is a better fit for this slot. Moving them here frees up their old time for further recovery, and they'll be sent a message about the change.</p>
        <button type="button" className={styles.primary} onClick={() => plan.plan_id && acceptRearrangement(plan.plan_id)} disabled={accepting || rearranged}>
          {accepting ? "Rearranging…" : rearranged ? "Rearranged ✓ — message sent" : "Rearrange & notify"}
        </button>
      </div>}
      {isLive && plan?.stage === "INCENTIVE" && plan?.selected_incentive && <p className={styles.status} role="status">
        {plan.selected_incentive.decision === "offer_incentive"
          ? `Clinic-approved incentive offered: ${plan.selected_incentive.chosen_incentive ?? "discount"}. ${plan.selected_incentive.reasoning ?? ""}`
          : (plan.message ?? "Incentive fallback evaluated.")}
      </p>}
      {isLive && plan?.outreach?.should_call && <div className={styles.status} role="status">
        <p><strong>Nemotron recommends calling:</strong> “{plan.outreach.call_brief.opening_line}”</p>
        {plan.outreach.call_brief.incentive_pitch && <p>Incentive to offer on the call: {plan.outreach.call_brief.incentive_pitch}</p>}
        {plan.outreach.status !== "pending_approval" || callState !== "idle" ? (
          <p>
            {callState === "calling" ? "Placing the call…"
              : plan.outreach.status === "placed" || callState === "placed" ? "📞 Call placed — this is a real outbound call, not a simulation."
              : plan.outreach.status === "rejected" ? "Call skipped."
              : callState === "not_configured" ? "Approved, but ElevenLabs/Twilio aren't configured on this deployment yet — no call was placed."
              : callState === "failed" ? "Call attempt failed — check ElevenLabs/Twilio configuration and logs."
              : `Call status: ${plan.outreach.status}`}
          </p>
        ) : (
          <button type="button" className={styles.primary} onClick={() => callNow(plan.outreach!.id)}>📞 Call {currentPatientId ?? candidates[0]?.name ?? "candidate"} now</button>
        )}
      </div>}
      {isLive && plan?.status === "pending" && currentPatientId && !currentRaw?.currently_booked_slot_id && <p className={styles.status} role="status">
        {currentPatientId} said no on the call? Record it and SlotSaver moves to the next candidate straight away — the next offer is the one allowed to carry a discount.{" "}
        <button type="button" className={styles.secondary} onClick={() => plan.plan_id && markDeclined(plan.plan_id)} disabled={declining}>
          {declining ? "Recording…" : `Mark ${currentPatientId} declined →`}
        </button>
      </p>}
      {isLive && plan?.status === "filled" && <p className={styles.status} role="status">Slot recovered — booked automatically once a candidate accepted. No owner action was required.</p>}
      {isLive && plan?.status === "no_candidates" && <p className={styles.status} role="status">No stored intent matched this slot — it would go unfilled.</p>}
      {isLive && plan?.status === "ranking_failed" && <p className={styles.status} role="status">{plan.message ?? "Ranking failed."}</p>}
      <footer className={styles.footer}>
        <p>{isLive
          ? "The appointment stays open until a candidate accepts, an incentive is accepted, or an owner books it manually. This panel only shows live progress — closing it doesn't pause recovery."
          : "This is a preview only — there's no real backend row for a locally-created slot to recover."}</p>
        {ranked.length > 0 && currentIndex < ranked.length && plan?.status === "pending" && <span className={styles.badge}>Currently offered: {ranked[currentIndex]}</span>}
      </footer>
      <p className={styles.integration}>{isLive
        ? <>Nemotron supplied these rankings live{plan?.revenue_at_risk ? ` · $${plan.revenue_at_risk.toFixed(0)} at risk on this slot` : ""}. The call button above places a real ElevenLabs/Twilio outbound call.</>
        : <>Planned integration: Nemotron supplies patient rankings; ElevenLabs handles outreach.</>}</p>
    </dialog>
  );
}
