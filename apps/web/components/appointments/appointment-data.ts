// Fallback values only, used before the active business profile has loaded
// or if the profile fetch fails - the live provider/service lists and hours
// come from the active BusinessProfile (see lib/useBusinessProfile.ts).
export const providers = ["Dr. Lee", "Dr. Patel", "Dr. Rivera"] as const;
export const visitTypes = ["Follow-up", "Consultation", "Check-up"] as const;
export const DEFAULT_OPEN_HOUR = 8;
export const DEFAULT_CLOSE_HOUR = 20;

export interface Appointment {
  id: string;
  patient: string;
  provider: string;
  visitType: string;
  date: string;
  time: string;
  duration: number;
  status: "booked" | "cancelled";
}
export function addDays(date: string, days: number) {
  const value = new Date(`${date}T12:00:00Z`);
  value.setUTCDate(value.getUTCDate() + days);
  return value.toISOString().slice(0, 10);
}
export function weekStart(date: string) {
  const day = new Date(`${date}T12:00:00Z`).getUTCDay();
  return addDays(date, -((day + 6) % 7));
}
export function minutes(time: string) {
  const [hour, minute] = time.split(":").map(Number);
  return hour * 60 + minute;
}
export function timeLabel(time: string) {
  const [hour, minute] = time.split(":").map(Number);
  return `${hour % 12 || 12}:${String(minute).padStart(2, "0")} ${hour >= 12 ? "PM" : "AM"}`;
}
export function dateLabel(date: string, options: Intl.DateTimeFormatOptions) {
  return new Intl.DateTimeFormat("en-US", { ...options, timeZone: "UTC" }).format(new Date(`${date}T12:00:00Z`));
}
export function sampleAppointments(today: string, providerList: readonly string[] = providers, serviceList: readonly string[] = visitTypes): Appointment[] {
  const monday = weekStart(today);
  return [
    ["Emma Wilson", 0, "09:00", 60, 0, 0],
    ["Noah Davis", 0, "13:00", 60, 1, 2],
    ["Olivia Chen", 1, "10:00", 60, 2, 1],
    ["Liam Johnson", 2, "09:30", 60, 0, 2],
    ["Ava Martinez", 2, "14:00", 60, 1, 0],
    ["James Brown", 3, "11:00", 60, 2, 1],
    ["Mia Thompson", 4, "10:00", 60, 0, 0],
    ["Ethan Brooks", 4, "14:00", 60, 1, 2],
  ].map((row, index) => ({
    id: `sample-${index}`,
    patient: String(row[0]),
    date: addDays(monday, Number(row[1])),
    time: String(row[2]),
    duration: Number(row[3]),
    provider: providerList[Number(row[4]) % providerList.length],
    visitType: serviceList[Number(row[5]) % serviceList.length],
    status: index === 4 ? "cancelled" : "booked",
  }));
}
// Local UI format only; deliberately separate from the future backend contract.
export function validAppointment(
  value: unknown,
  providerList: readonly string[] = providers,
  serviceList: readonly string[] = visitTypes,
  openHour: number = DEFAULT_OPEN_HOUR,
  closeHour: number = DEFAULT_CLOSE_HOUR,
): value is Appointment {
  if (!value || typeof value !== "object") return false;
  const a = value as Appointment;
  if (!(typeof a.time === "string" && /^\d{2}:\d{2}$/.test(a.time))) return false;
  const startHour = Number(a.time.split(":")[0]);
  return typeof a.patient === "string" && !!a.patient.trim() && a.patient.length <= 100
    && providerList.includes(a.provider)
    && serviceList.includes(a.visitType)
    && typeof a.date === "string" && /^\d{4}-\d{2}-\d{2}$/.test(a.date)
    && !Number.isNaN(Date.parse(a.date)) && new Date(a.date).toISOString().slice(0, 10) === a.date
    && startHour >= openHour && startHour < closeHour
    && Number.isInteger(a.duration) && a.duration >= 15 && a.duration <= 180
    && minutes(a.time) + a.duration <= closeHour * 60
    && (a.status === "booked" || a.status === "cancelled");
}
