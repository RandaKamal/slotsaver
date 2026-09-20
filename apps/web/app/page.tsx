import { existsSync } from "node:fs";
import path from "node:path";
import { Sidebar } from "@/components/dashboard/Sidebar";
import { MascotCard } from "@/components/dashboard/MascotCard";
import { MetricCard } from "@/components/dashboard/MetricCard";
import { demoMetrics } from "@/components/dashboard/mock-data";
import { fetchMetrics } from "@/lib/api";
import { OutreachQueue } from "@/components/outreach/OutreachQueue";
import type { MetricCardProps } from "@/components/dashboard/MetricCard";

function publicMascot(filename: string) {
  return existsSync(path.join(process.cwd(), "public/mascots", filename))
    ? `/mascots/${filename}`
    : undefined;
}

/** Real clinic counts, or the labelled fixtures if the API is down. */
async function metrics(): Promise<{ cards: MetricCardProps[]; live: boolean }> {
  try {
    const m = await fetchMetrics();
    return {
      live: true,
      cards: [
        { label: "Open cancellations", value: m.open_slots, description: `$${m.revenue_at_risk.toFixed(0)} at risk`, icon: "cancellations" },
        { label: "Booked appointments", value: m.booked, description: "Currently filled", icon: "recovery" },
        { label: "Patients waiting", value: m.patients_waiting, description: "Asked to hear about openings", icon: "patients" },
      ],
    };
  } catch {
    return { live: false, cards: demoMetrics };
  }
}

export default async function HomePage() {
  const mascotSrc = publicMascot("slotsaver-bunny.png") ?? publicMascot("scout-happy.png");
  const happySrc = publicMascot("scout-happy.png");
  const { cards, live } = await metrics();

  return (
    <div className="app-shell">
      <a className="skip-link" href="#main-content">Skip to content</a>
      <Sidebar />
      <div className="main-area">
        <div className="topbar"><span>Workspace <span className="breadcrumb-divider">/</span> <strong>Dashboard</strong></span><span className="preview-badge">{live ? "Live data" : "UI preview"}</span></div>
        <main id="main-content" className="dashboard">
          <header className="dashboard-header"><p className="eyebrow">A LITTLE MORE ROOM FOR CARE</p><h1>Welcome to SlotSaver.</h1><p>Let&apos;s fill some empty slots.</p></header>
          <MascotCard mascotSrc={mascotSrc} happySrc={happySrc} />
          <section className="summary" aria-labelledby="summary-heading"><div className="section-heading"><h2 id="summary-heading">Your clinic at a glance</h2><span>{live ? "Live from your clinic" : "Sample data"}</span></div><div className="metric-grid">{cards.map((metric) => <MetricCard key={metric.label} {...metric} />)}</div></section>
          <section className="summary" aria-labelledby="outreach-heading">
            <div className="section-heading">
              <h2 id="outreach-heading">Pending outbound calls</h2>
              <span>Nemotron decides who to call and what to say — you decide if the call happens</span>
            </div>
            <OutreachQueue />
          </section>
          <p className="dashboard-footer">Fewer empty slots. Shorter wait times. More room for care.</p>
        </main>
      </div>
    </div>
  );
}
