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

export async function cancelAppointment(id: number): Promise<ApiAppointment> {
  const res = await fetch(`${API_URL}/api/appointments/${id}/cancel`, { method: "POST" });
  if (!res.ok) throw new Error(`POST /api/appointments/${id}/cancel -> ${res.status}`);
  return res.json() as Promise<ApiAppointment>;
}

// --- POST /api/recovery/from-cancellation ------------------------------------

export interface RecoveryCandidate {
  patient_id: string;
  match_score: number;
  reason: string;
  /** Set when this candidate is already booked into a different appointment -
   *  accepting their offer is a REARRANGEMENT (move them, free their old
   *  slot) rather than a plain fill. */
  currently_booked_slot_id?: number | null;
  currently_booked_start?: string | null;
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
  outreach?: {
    id: number;
    should_call: boolean;
    reason: string;
    incentive: { decision?: string; chosen_incentive?: string | null; reasoning?: string | null } | null;
    call_brief: { tone: string; opening_line: string; key_points: string[]; incentive_pitch: string | null };
    status: string;
  } | null;
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

// --- POST /api/recovery/{plan_id}/response -----------------------------------

/** Advances the current offer: "accepted" books it for the current
 *  candidate (and, if they were already booked elsewhere, triggers the
 *  rearrangement cascade on the backend - see slot_recovery.cascade_after_move).
 *  "declined" / "timeout" move to the next ranked candidate. */
export async function respondToRecoveryPlan(planId: string, response: "accepted" | "declined" | "timeout"): Promise<RecoveryPlan> {
  const res = await fetch(`${API_URL}/api/recovery/${planId}/response`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ response }),
    cache: "no-store",
  });
  if (!res.ok) throw new Error(`POST /api/recovery/${planId}/response -> ${res.status}`);
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

// --- Customers / patient memory ------------------------------------------------

export interface CustomerSummary {
  patient_id: string;
  saved_conversations: number;
  latest_said: string | null;
  latest_at: string | null;
  brief: string;
}

export function fetchCustomers(signal?: AbortSignal): Promise<CustomerSummary[]> {
  return getJson<CustomerSummary[]>("/api/customers", signal);
}

// --- Business profile ---------------------------------------------------------

export interface BusinessProfileSummary {
  id: number;
  slug: string;
  name: string;
  business_type: string;
  active: boolean;
}

export interface Worker {
  id: string;
  name: string;
  role: string;
  service_ids: string[];
  working_days: string[];
  start_time: string;
  end_time: string;
  breaks: { start: string; end: string }[];
  active: boolean;
}

export interface ServiceOffering {
  id: string;
  name: string;
  duration_minutes: number;
  price: number;
  eligible_roles: string[];
  buffer_minutes: number;
  allow_provider_preference: boolean;
}

export interface BookingRules {
  min_notice_minutes: number;
  max_horizon_days: number;
  same_day_allowed: boolean;
  customer_can_choose_provider: boolean;
  provider_flexibility_allowed: boolean;
}

export interface RecoveryRules {
  auto_recovery_enabled: boolean;
  candidate_timeout_seconds: number;
  max_recovery_attempts: number;
  incentive_fallback_enabled: boolean;
}

export interface IncentivePolicy {
  max_discount_percent: number;
  minimum_revenue: number;
  allowed_incentives: { id: string; type: string; value: number }[];
  incentive_time_threshold_hours: number;
  excluded_services: string[];
  incentive_score_threshold: number;
}

export interface BusinessProfile extends BusinessProfileSummary {
  timezone: string;
  location: string;
  worker_label: string;
  customer_label: string;
  service_label: string;
  working_days: string[];
  open_time: string;
  close_time: string;
  workers: Worker[];
  services: ServiceOffering[];
  booking_rules: BookingRules;
  recovery_rules: RecoveryRules;
  incentive_policy: IncentivePolicy;
}

export function fetchBusinessProfiles(signal?: AbortSignal): Promise<BusinessProfileSummary[]> {
  return getJson<BusinessProfileSummary[]>("/api/business-profiles", signal);
}

export function fetchActiveBusinessProfile(signal?: AbortSignal): Promise<BusinessProfile> {
  return getJson<BusinessProfile>("/api/business-profiles/active", signal);
}

export function fetchBusinessProfile(id: number, signal?: AbortSignal): Promise<BusinessProfile> {
  return getJson<BusinessProfile>(`/api/business-profiles/${id}`, signal);
}

export async function activateBusinessProfile(id: number): Promise<BusinessProfile> {
  const res = await fetch(`${API_URL}/api/business-profiles/${id}/activate`, { method: "POST" });
  if (!res.ok) throw new Error(`activate profile failed: ${res.status}`);
  return res.json() as Promise<BusinessProfile>;
}

export async function updateBusinessProfile(id: number, patch: Partial<BusinessProfile>): Promise<BusinessProfile> {
  const res = await fetch(`${API_URL}/api/business-profiles/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(patch),
  });
  if (!res.ok) throw new Error(`update profile failed: ${res.status}`);
  return res.json() as Promise<BusinessProfile>;
}
