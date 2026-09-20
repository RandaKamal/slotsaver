import { Sidebar } from "@/components/dashboard/Sidebar";
import { VoiceAgent } from "@/components/calls/VoiceAgent";

export const metadata = { title: "Voice agent | SlotSaver" };

export default function CallPage() {
  return (
    <div className="app-shell">
      <a className="skip-link" href="#main-content">Skip to content</a>
      <Sidebar activePage="Voice agent" />
      <div className="main-area">
        <div className="topbar">
          <span>Workspace <span className="breadcrumb-divider">/</span> <strong>Voice agent</strong></span>
          <span className="preview-badge">Live</span>
        </div>
        <main id="main-content" className="dashboard">
          <header className="dashboard-header">
            <p className="eyebrow">TALK TO THE SCHEDULER</p>
            <h1>Voice agent</h1>
            <p>Book, reschedule, or tell us when you&apos;re free. Anything you say about your
              availability is saved as scheduling intent.</p>
          </header>
          <VoiceAgent />
        </main>
      </div>
    </div>
  );
}
