import type { Appointment } from "@/components/appointments/appointment-data";

export interface RecoveryCandidate {
  id: string;
  name: string;
  initials: string;
  score: number;
  reasons: string[];
}

// Illustrative UI fixtures, not clinical eligibility checks or Nemotron results.
// Replace this function with the agreed ranking response when integration is ready.
export function sampleCandidates(slot: Appointment): RecoveryCandidate[] {
  return [
    { id: "demo-emily", name: "Emily Carter", initials: "EC", score: 96, reasons: [`Waiting for a ${slot.visitType.toLowerCase()}`, `Prefers ${slot.provider}`, "Requested an earlier opening"] },
    { id: "demo-daniel", name: "Daniel Kim", initials: "DK", score: 89, reasons: [`Available for a ${slot.duration}-minute visit`, "Flexible about provider", "Open to short-notice appointments"] },
    { id: "demo-sophie", name: "Sophie Martinez", initials: "SM", score: 82, reasons: [`Waiting for a ${slot.visitType.toLowerCase()}`, "Flexible scheduling preferences", "Wants to be notified about openings"] },
  ].filter((candidate) => candidate.name.toLowerCase() !== slot.patient.trim().toLowerCase());
}
