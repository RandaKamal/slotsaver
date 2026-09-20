/**
 * Typed client for the backend endpoints the dashboard needs.
 *
 * This file was referenced by page.tsx, AppointmentCalendar.tsx and
 * RecoveryPanel.tsx but never actually committed - the merge that wired them
 * to live data (22faefd) only included the four files that import from it.
 * Shapes below match exactly what those three call sites already read.
 */

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

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
  revenue_at_risk?: number;
  message?: string;
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
