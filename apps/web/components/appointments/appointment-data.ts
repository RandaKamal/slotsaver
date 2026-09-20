export const providers = ["Dr. Lee", "Dr. Patel", "Dr. Rivera"] as const;
export const visitTypes = ["Follow-up", "Consultation", "Check-up"] as const;
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
export function sampleAppointments(today: string): Appointment[] {
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
  ].map((row, index) => ({ id: `sample-${index}`, patient: String(row[0]), date: addDays(monday, Number(row[1])), time: String(row[2]), duration: Number(row[3]), provider: providers[Number(row[4])], visitType: visitTypes[Number(row[5])], status: index === 4 ? "cancelled" : "booked" }));
}
// Local UI format only; deliberately separate from the future backend contract.
export function validAppointment(value: unknown): value is Appointment {
  if (!value || typeof value !== "object") return false;
  const a = value as Appointment;
  return typeof a.patient === "string" && !!a.patient.trim() && a.patient.length <= 100
    && providers.includes(a.provider as typeof providers[number])
    && visitTypes.includes(a.visitType as typeof visitTypes[number])
    && typeof a.date === "string" && /^\d{4}-\d{2}-\d{2}$/.test(a.date)
    && !Number.isNaN(Date.parse(a.date)) && new Date(a.date).toISOString().slice(0, 10) === a.date
    && typeof a.time === "string" && /^(0[89]|1[0-7]):[0-5]\d$/.test(a.time)
    && Number.isInteger(a.duration) && a.duration >= 15 && a.duration <= 180
    && minutes(a.time) + a.duration <= 18 * 60
    && (a.status === "booked" || a.status === "cancelled");
}
