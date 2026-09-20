"use client";

import { useEffect, useRef, useState } from "react";
import { dateLabel, timeLabel, type Appointment } from "@/components/appointments/appointment-data";
import { Icon } from "@/components/ui/Icon";
import { sampleCandidates } from "./mock-data";
import styles from "./RecoveryPanel.module.css";

interface RecoveryPanelProps {
  appointment: Appointment;
  onClose: () => void;
}

export function RecoveryPanel({ appointment, onClose }: RecoveryPanelProps) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [started, setStarted] = useState(false);
  const candidates = sampleCandidates(appointment);
  const first = candidates[0];

  useEffect(() => { dialog.current?.showModal(); }, []);

  return (
    <dialog ref={dialog} className={styles.panel} aria-labelledby="recovery-title" aria-describedby="recovery-disclaimer" onClose={onClose}>
      <header className={styles.header}>
        <div><p className={styles.eyebrow}>MAKE ROOM FOR AN EARLIER VISIT</p><h2 id="recovery-title">{started ? "Outreach preview" : "Recovery plan"}</h2></div>
        <button type="button" className={styles.close} aria-label="Close recovery panel" onClick={() => dialog.current?.close()}>×</button>
      </header>
      <p id="recovery-disclaimer" className={styles.disclaimer}><strong>Demo only.</strong> Patient matches and scores are sample data. No calls or messages will be sent.</p>
      <ol className={styles.steps} aria-label="Recovery progress"><li>1 <span>Opening identified</span></li><li aria-current={!started ? "step" : undefined} className={!started ? styles.current : ""}>2 <span>Sample matches</span></li><li aria-current={started ? "step" : undefined} className={started ? styles.current : ""}>3 <span>Outreach preview</span></li></ol>
      <section className={styles.opening} aria-label="Cancelled appointment opening">
        <span className={styles.slotIcon}><Icon name="calendar" /></span>
        <div><h3>{appointment.visitType} · {appointment.duration} minutes</h3><p>{dateLabel(appointment.date, { weekday: "short", month: "short", day: "numeric", year: "numeric" })} at {timeLabel(appointment.time)}</p><p>{appointment.provider} · Cancelled by {appointment.patient}</p></div>
        <span className={styles.badge}>Open slot</span>
      </section>
      {!started ? <>
        <div className={styles.sectionTitle}><h3>Patients who could be a fit</h3><span>{candidates.length} sample matches</span></div>
        <p className={styles.caption}>Ranked examples of how patient preferences can be explained.</p>
        <ol className={styles.candidates} aria-label="Ranked sample patients">
          {candidates.map((candidate, index) => <li key={candidate.id} className={styles.candidate}>
            <span className={styles.rank}>{index + 1}</span><span className={styles.avatar} aria-hidden="true">{candidate.initials}</span>
            <div className={styles.candidateBody}><h4>{candidate.name}{index === 0 && <span className={styles.topMatch}>Top sample match</span>}</h4><ul>{candidate.reasons.map((reason) => <li key={reason}><span aria-hidden="true">✓</span>{reason}</li>)}</ul></div>
            <div className={styles.score}><strong>{candidate.score}%</strong><span>Example score</span></div>
          </li>)}
        </ol>
        <footer className={styles.footer}><p>Start with the highest-ranked sample patient.</p><button type="button" className={styles.primary} disabled={!first} onClick={() => setStarted(true)}>Start outreach <Icon name="arrow" /></button></footer>
      </> : <section className={styles.outreach} aria-labelledby="outreach-heading">
        <div className={styles.sectionTitle}><h3 id="outreach-heading">First in the outreach queue</h3><span className={styles.badge}>Simulation</span></div>
        <div className={styles.contact}><span className={styles.avatar} aria-hidden="true">{first.initials}</span><div><h4>{first.name}</h4><p>Voice call · sample patient 1 of {candidates.length}</p></div></div>
        <p className={styles.caption}>Example call script</p>
        <blockquote>“Hi {first.name.split(" ")[0]}, this is your clinic. A {appointment.visitType.toLowerCase()} with {appointment.provider} has opened up on {dateLabel(appointment.date, { weekday: "long", month: "long", day: "numeric" })} at {timeLabel(appointment.time)}. Would you like this appointment?”</blockquote>
        <p className={styles.status} role="status">Demo outreach started. No actual call has been placed.</p>
        <h4 className={styles.queueTitle}>Up next if the patient declines or doesn’t answer</h4>
        <ol className={styles.queue} start={2}>{candidates.slice(1).map((candidate) => <li key={candidate.id}>{candidate.name}<span>Not contacted</span></li>)}</ol>
        <footer className={styles.footer}><p>The appointment stays open. Closing this panel resets the preview.</p><button type="button" className={styles.secondary} onClick={() => setStarted(false)}>Stop preview</button></footer>
      </section>}
      <p className={styles.integration}>Planned integration: Nemotron supplies patient rankings; ElevenLabs handles outreach.</p>
    </dialog>
  );
}
