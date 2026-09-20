"use client";

import Link from "next/link";
import { Icon, type IconName } from "@/components/ui/Icon";
import { useBusinessProfile } from "@/lib/useBusinessProfile";

// Cancellations and recovery are one live flow, not separate pages - they
// both happen inside Appointments (cancel a booking there and the recovery
// panel opens on the same screen), so a separate disabled "coming soon" nav
// item for each was clutter that led nowhere. One real nav item beats two
// dead ones.
function navigation(customerLabel: string): { label: string; icon: IconName }[] {
  return [
    { label: "Dashboard", icon: "dashboard" },
    { label: "Appointments", icon: "calendar" },
    { label: "Voice agent", icon: "patients" },
    { label: `${customerLabel}s`, icon: "patients" },
    { label: "Settings", icon: "settings" },
  ];
}

function NavItem({ label, icon, activePage }: { label: string; icon: IconName; activePage: string }) {
  const routes: Record<string, string> = {
    Dashboard: "/",
    Appointments: "/appointments",
    "Voice agent": "/call",
    Settings: "/settings",
  };
  if (label in routes) {
    return <Link className={`nav-item${label === activePage ? " active" : ""}`} href={routes[label]} aria-current={label === activePage ? "page" : undefined}><Icon name={icon} />{label}</Link>;
  }
  return <button className="nav-item" type="button" disabled title={`${label} — coming soon`}><Icon name={icon} />{label}<span className="sr-only"> — coming soon</span></button>;
}

export function Sidebar({ activePage = "Dashboard" }: { activePage?: "Dashboard" | "Appointments" | "Voice agent" | "Settings" }) {
  const profile = useBusinessProfile();
  const customerLabel = profile?.customer_label ?? "Patient";
  const workspaceCaption = profile ? `${profile.name.toUpperCase()} WORKSPACE` : "WORKSPACE";

  return (
    <aside className="sidebar">
      <Link href="/" className="brand" aria-label="SlotSaver dashboard"><span className="brand-icon"><Icon name="calendar" /></span><span>Slot<span className="brand-accent">Saver</span></span></Link>
      <p className="sidebar-caption">{workspaceCaption}</p>
      <nav aria-label="Main navigation">{navigation(customerLabel).map((item) => <NavItem key={item.label} {...item} activePage={activePage} />)}</nav>
      <p className="navigation-note">More tools coming soon</p>
      <div className="workspace"><span className="workspace-avatar">SS</span><div><strong>{profile?.name ?? "Your business"}</strong><span>Workspace preview</span></div></div>
    </aside>
  );
}
