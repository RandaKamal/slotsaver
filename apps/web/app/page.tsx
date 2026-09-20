import { existsSync } from "node:fs";
import path from "node:path";
import { Sidebar } from "@/components/dashboard/Sidebar";
import { MascotCard } from "@/components/dashboard/MascotCard";
import { MetricCard } from "@/components/dashboard/MetricCard";
import { demoMetrics } from "@/components/dashboard/mock-data";

function publicMascot(filename: string) {
  return existsSync(path.join(process.cwd(), "public/mascots", filename))
    ? `/mascots/${filename}`
    : undefined;
}

export default function HomePage() {
  const mascotSrc = publicMascot("slotsaver-bunny.png") ?? publicMascot("scout-happy.png");
  const happySrc = publicMascot("scout-happy.png");

  return (
    <div className="app-shell">
      <a className="skip-link" href="#main-content">Skip to content</a>
      <Sidebar />
      <div className="main-area">
        <div className="topbar"><span>Workspace <span className="breadcrumb-divider">/</span> <strong>Dashboard</strong></span><span className="preview-badge">UI preview</span></div>
        <main id="main-content" className="dashboard">
          <header className="dashboard-header"><p className="eyebrow">A LITTLE MORE ROOM FOR CARE</p><h1>Welcome to SlotSaver.</h1><p>Let&apos;s fill some empty slots.</p></header>
          <MascotCard mascotSrc={mascotSrc} happySrc={happySrc} />
          <section className="summary" aria-labelledby="summary-heading"><div className="section-heading"><h2 id="summary-heading">Your clinic at a glance</h2><span>Sample data</span></div><div className="metric-grid">{demoMetrics.map((metric) => <MetricCard key={metric.label} {...metric} />)}</div></section>
          <p className="dashboard-footer">Fewer empty slots. Shorter wait times. More room for care.</p>
        </main>
      </div>
    </div>
  );
}
