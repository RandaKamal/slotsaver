import type { MetricCardProps } from "./MetricCard";

// UI preview fixtures only. These values do not represent clinic activity.
export const demoMetrics: MetricCardProps[] = [
  { label: "Open cancellations", value: 3, description: "Opportunities to fill", icon: "cancellations" },
  { label: "Slots recovered", value: 12, description: "Patients seen sooner", icon: "recovery" },
  { label: "Patients waiting", value: 24, description: "Hoping for an earlier visit", icon: "patients" },
];
