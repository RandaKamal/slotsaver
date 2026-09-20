"use client";

import Link from "next/link";
import { Icon, type IconName } from "@/components/ui/Icon";
import { useBusinessProfile } from "@/lib/useBusinessProfile";

// Cancellations and recovery are one live flow, not separate pages - they
// both happen inside Appointments (cancel a booking there and the recovery
// panel opens on the same screen). The voice-agent test widget isn't part
// of the live demo flow either - real calls go out through the recovery/
// outreach path, not this page. Fewer dead-end nav items, not more of them.
function navigation(customerLabel: string): { label: string; icon: IconName; href: string }[] {
  return [
    { label: "Dashboard", icon: "dashboard", href: "/" },
    { label: "Appointments", icon: "calendar", href: "/appointments" },
    { label: `${customerLabel}s`, icon: "patients", href: "/patients" },
    { label: "Settings", icon: "settings", href: "/settings" },
  ];
}

function NavItem({ label, icon, href, activePage }: { label: string; icon: IconName; href: string; activePage: string }) {
  return <Link className={`nav-item${label === activePage ? " active" : ""}`} href={href} aria-current={label === activePage ? "page" : undefined}><Icon name={icon} />{label}</Link>;
}

export function Sidebar({ activePage = "Dashboard" }: { activePage?: string }) {
  const profile = useBusinessProfile();
  const customerLabel = profile?.customer_label ?? "Patient";
  const workspaceCaption = profile ? `${profile.name.toUpperCase()} WORKSPACE` : "WORKSPACE";

  return (
    <aside className="sidebar">
      <Link href="/" className="brand" aria-label="SlotSaver dashboard"><span className="brand-icon"><Icon name="calendar" /></span><span>Slot<span className="brand-accent">Saver</span></span></Link>
      <p className="sidebar-caption">{workspaceCaption}</p>
      <nav aria-label="Main navigation">{navigation(customerLabel).map((item) => <NavItem key={item.label} {...item} activePage={activePage} />)}</nav>
      <div className="workspace"><span className="workspace-avatar">SS</span><div><strong>{profile?.name ?? "Your business"}</strong><span>Workspace</span></div></div>
    </aside>
  );
}
