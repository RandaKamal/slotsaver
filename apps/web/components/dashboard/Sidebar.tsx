import Link from "next/link";
import { Icon, type IconName } from "@/components/ui/Icon";

const navigation: { label: string; icon: IconName }[] = [
  { label: "Dashboard", icon: "dashboard" },
  { label: "Appointments", icon: "calendar" },
  { label: "Patients", icon: "patients" },
  { label: "Cancellations", icon: "cancellations" },
  { label: "Recovery", icon: "recovery" },
  { label: "Settings", icon: "settings" },
];

function NavItem({ label, icon, activePage }: { label: string; icon: IconName; activePage: string }) {
  if (label === "Dashboard" || label === "Appointments") {
    return <Link className={`nav-item${label === activePage ? " active" : ""}`} href={label === "Dashboard" ? "/" : "/appointments"} aria-current={label === activePage ? "page" : undefined}><Icon name={icon} />{label}</Link>;
  }
  return <button className="nav-item" type="button" disabled title={`${label} — coming soon`}><Icon name={icon} />{label}<span className="sr-only"> — coming soon</span></button>;
}

export function Sidebar({ activePage = "Dashboard" }: { activePage?: "Dashboard" | "Appointments" }) {
  return (
    <aside className="sidebar">
      <Link href="/" className="brand" aria-label="SlotSaver dashboard"><span className="brand-icon"><Icon name="calendar" /></span><span>Slot<span className="brand-accent">Saver</span></span></Link>
      <p className="sidebar-caption">CLINIC WORKSPACE</p>
      <nav aria-label="Main navigation">{navigation.map((item) => <NavItem key={item.label} {...item} activePage={activePage} />)}</nav>
      <p className="navigation-note">More tools coming soon</p>
      <div className="workspace"><span className="workspace-avatar">SS</span><div><strong>Your clinic</strong><span>Workspace preview</span></div></div>
    </aside>
  );
}
