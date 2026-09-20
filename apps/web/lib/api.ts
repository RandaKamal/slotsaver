/**
 * Typed client for the backend endpoints the dashboard needs.
 *
 * This file was referenced by page.tsx, AppointmentCalendar.tsx and
 * RecoveryPanel.tsx but never actually committed - the merge that wired them
 * to live data (22faefd) only included the four files that import from it.
 * Shapes below match exactly what those three call sites already read.
 */

import { API_URL } from "@/lib/constants";

async function getJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, { signal, cache: "no-store" });
  if (!res.ok) throw new Error(`GET ${path} -> ${res.status}`);
  return res.json() as Promise<T>;
}

// --- GET /api/appointments/metrics -----------------------------------------

export interface DashboardMetrics {
  open_slots: number;
  booked: number;
  patients_waiting: number;
  revenue_at_risk: number;
}

export function fetchMetrics(): Promise<DashboardMetrics> {
  return getJson<DashboardMetrics>("/api/appointments/metrics");
}

// --- GET /api/appointments ---------------------------------------------------

export interface ApiAppointment {
  id: number;
  service: string;
  provider: string;
  start_time: string;
  duration_minutes: number;
  price: number;
  status: string;
}

export function fetchAppointments(signal?: AbortSignal): Promise<ApiAppointment[]> {
  return getJson<ApiAppointment[]>("/api/appointments", signal);
}

// --- POST /api/recovery/from-cancellation ------------------------------------

export interface RecoveryCandidate {
  patient_id: string;
  match_score: number;
  reason: string;
}

export interface ExcludedCandidate {
  patient_id: string;
  reason: string;
}

export interface RecoveryPlan {
  plan_id?: string | null;
  candidates?: RecoveryCandidate[];
  excluded?: ExcludedCandidate[];
  ranked_candidate_ids?: string[];
  candidate_statuses?: Record<string, string>;
  current_candidate_index?: number;
  // "pending" | "filled" | "exhausted" | "ranking_failed" | "no_candidates"
  status?: string;
  // "NORMAL" | "INCENTIVE"
  stage?: string;
  selected_incentive?: { decision?: string; chosen_incentive?: string | null; reasoning?: string | null } | null;
  revenue_at_risk?: number;
  message?: string;
  cancelled_by?: string | null;
}

export async function recoverFromCancellation(slotId: number): Promise<RecoveryPlan> {
  const res = await fetch(`${API_URL}/api/recovery/from-cancellation`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ slot_id: slotId }),
    cache: "no-store",
  });
  if (!res.ok) throw new Error(`POST /api/recovery/from-cancellation -> ${res.status}`);
  return res.json() as Promise<RecoveryPlan>;
}

// --- GET /api/recovery/by-slot/{slot_id} -------------------------------------

/** The live recovery plan for a slot, however it was created — the autonomous
 *  scheduler, a live phone cancellation, or the manual trigger above. Used for
 *  polling. `null` means no cancellation has been processed for this slot yet
 *  (a real, expected state right after a fresh cancellation), not a failure. */
export async function fetchRecoveryPlanBySlot(slotId: number, signal?: AbortSignal): Promise<RecoveryPlan | null> {
  const res = await fetch(`${API_URL}/api/recovery/by-slot/${slotId}`, { signal, cache: "no-store" });
  if (res.status === 404) return null;
  if (!res.ok) throw new Error(`GET /api/recovery/by-slot/${slotId} -> ${res.status}`);
  return res.json() as Promise<RecoveryPlan>;
}


// --- Outreach approval queue --------------------------------------------------

export interface CallBrief {
  tone: string;
  opening_line: string;
  key_points: string[];
  incentive_pitch: string | null;
}

export interface OutreachAttempt {
  id: number;
  slot_id: number;
  patient_id: string;
  phone_number: string | null;
  match_score: number;
  revenue_at_risk: number;
  should_call: boolean;
  decision_reason: string;
  incentive: { chosen_incentive?: string; reasoning?: string } | null;
  call_brief: CallBrief;
  status: string;
  created_at: string | null;
  decided_at: string | null;
}

export async function fetchPendingOutreach(signal?: AbortSignal): Promise<OutreachAttempt[]> {
  return getJson<OutreachAttempt[]>("/api/outreach/pending", signal);
}

async function decide(id: number, action: "approve" | "reject"): Promise<OutreachAttempt> {
  const res = await fetch(`${API_URL}/api/outreach/${id}/${action}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({}),
  });
  if (!res.ok) throw new Error(`${action} failed: ${res.status}`);
  return res.json();
}

export const approveOutreach = (id: number) => decide(id, "approve");
export const rejectOutreach = (id: number) => decide(id, "reject");
