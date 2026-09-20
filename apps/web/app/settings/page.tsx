import { Sidebar } from "@/components/dashboard/Sidebar";
import { BusinessProfileSettings } from "@/components/settings/BusinessProfileSettings";

export const metadata = { title: "Settings | SlotSaver" };

export default function SettingsPage() {
  return <div className="app-shell">
    <a className="skip-link" href="#main-content">Skip to content</a>
    <Sidebar activePage="Settings" />
    <div className="main-area">
      <div className="topbar"><span>Workspace <span className="breadcrumb-divider">/</span> <strong>Settings</strong></span><span className="preview-badge">Business profile</span></div>
      <main id="main-content"><BusinessProfileSettings /></main>
    </div>
  </div>;
}
