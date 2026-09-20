import { Sidebar } from "@/components/dashboard/Sidebar";
import { CustomerList } from "@/components/customers/CustomerList";

export const metadata = { title: "Patients | SlotSaver" };

export default function PatientsPage() {
  return <div className="app-shell">
    <a className="skip-link" href="#main-content">Skip to content</a>
    <Sidebar activePage="Patients" />
    <div className="main-area">
      <div className="topbar"><span>Workspace <span className="breadcrumb-divider">/</span> <strong>Patients</strong></span><span className="preview-badge">Live data</span></div>
      <main id="main-content"><CustomerList /></main>
    </div>
  </div>;
}
