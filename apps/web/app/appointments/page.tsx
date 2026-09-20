import { Sidebar } from "@/components/dashboard/Sidebar";
import { AppointmentCalendar } from "@/components/appointments/AppointmentCalendar";

export const metadata = { title: "Appointments | SlotSaver" };

export default function AppointmentsPage() {
  return <div className="app-shell">
    <a className="skip-link" href="#main-content">Skip to content</a>
    <Sidebar activePage="Appointments" />
    <div className="main-area">
      <div className="topbar"><span>Workspace <span className="breadcrumb-divider">/</span> <strong>Appointments</strong></span><span className="preview-badge">UI preview</span></div>
      <main id="main-content"><AppointmentCalendar /></main>
    </div>
  </div>;
}
