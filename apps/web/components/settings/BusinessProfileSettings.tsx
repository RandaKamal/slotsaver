"use client";

import { useEffect, useState } from "react";
import {
  activateBusinessProfile,
  fetchBusinessProfile,
  fetchBusinessProfiles,
  updateBusinessProfile,
  type BusinessProfile,
  type BusinessProfileSummary,
  type IncentivePolicy,
  type ServiceOffering,
  type Worker,
} from "@/lib/api";
import styles from "./BusinessProfileSettings.module.css";

const WEEKDAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"];

function SavedNote({ show }: { show: boolean }) {
  return show ? <span className={styles.savedNote}>Saved</span> : null;
}

export function BusinessProfileSettings() {
  const [summaries, setSummaries] = useState<BusinessProfileSummary[]>([]);
  const [profile, setProfile] = useState<BusinessProfile | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const reload = (id?: number) => {
    fetchBusinessProfiles()
      .then((rows) => {
        setSummaries(rows);
        const target = id ?? rows.find((r) => r.active)?.id ?? rows[0]?.id;
        if (target) return fetchBusinessProfile(target);
        return null;
      })
      .then((detail) => { if (detail) setProfile(detail); })
      .catch(() => setError("Could not reach the business profile API."))
      .finally(() => setLoading(false));
  };

  useEffect(() => { reload(); }, []);

  async function selectProfile(id: number) {
    setLoading(true);
    try {
      const detail = await fetchBusinessProfile(id);
      setProfile(detail);
    } catch {
      setError("Could not load that profile.");
    } finally {
      setLoading(false);
    }
  }

  async function activate(id: number) {
    await activateBusinessProfile(id);
    reload(id);
  }

  async function save(patch: Partial<BusinessProfile>) {
    if (!profile) return;
    const updated = await updateBusinessProfile(profile.id, patch);
    setProfile(updated);
    setSummaries((current) => current.map((s) => (s.id === updated.id ? { ...s, name: updated.name, business_type: updated.business_type } : s)));
    return updated;
  }

  if (loading && !profile) return <div className={styles.page}><h1>Business profile</h1><p>Loading…</p></div>;
  if (error && !profile) return <div className={styles.page}><h1>Business profile</h1><p role="alert">{error}</p></div>;
  if (!profile) return null;

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <div>
          <p className="eyebrow">BUSINESS PROFILE SETUP</p>
          <h1>{profile.name}</h1>
        </div>
      </div>
      <p className={styles.subtitle}>
        One active profile drives the whole app — services, worker labels, working hours, and recovery/incentive rules.
        Switch or edit a profile below; nothing here needs a code change or restart.
      </p>

      <div className={styles.switcher}>
        <span>ACTIVE PROFILE</span>
        {summaries.map((s) => (
          <button
            key={s.id}
            className={`${styles.profileChip} ${s.id === profile.id ? styles.active : ""}`}
            onClick={() => selectProfile(s.id)}
          >
            {s.name}{s.active ? " ✓" : ""}
          </button>
        ))}
        {!profile.active && (
          <button className={styles.saveButton} onClick={() => activate(profile.id)}>
            Make “{profile.name}” active
          </button>
        )}
      </div>

      <BusinessSection profile={profile} onSave={save} />
      <ServicesSection profile={profile} onSave={save} />
      <WorkersSection profile={profile} onSave={save} />
      <HoursSection profile={profile} onSave={save} />
      <PolicySection profile={profile} onSave={save} />
    </div>
  );
}

type SaveFn = (patch: Partial<BusinessProfile>) => Promise<BusinessProfile | undefined>;

function useSavedFlash() {
  const [saved, setSaved] = useState(false);
  const flash = () => { setSaved(true); setTimeout(() => setSaved(false), 1800); };
  return { saved, flash };
}

function BusinessSection({ profile, onSave }: { profile: BusinessProfile; onSave: SaveFn }) {
  const [name, setName] = useState(profile.name);
  const [businessType, setBusinessType] = useState(profile.business_type);
  const [timezone, setTimezone] = useState(profile.timezone);
  const [location, setLocation] = useState(profile.location);
  const [workerLabel, setWorkerLabel] = useState(profile.worker_label);
  const [customerLabel, setCustomerLabel] = useState(profile.customer_label);
  const [serviceLabel, setServiceLabel] = useState(profile.service_label);
  const { saved, flash } = useSavedFlash();

  useEffect(() => {
    setName(profile.name); setBusinessType(profile.business_type); setTimezone(profile.timezone);
    setLocation(profile.location); setWorkerLabel(profile.worker_label);
    setCustomerLabel(profile.customer_label); setServiceLabel(profile.service_label);
  }, [profile]);

  return (
    <section className={styles.section}>
      <h2>1. Business</h2>
      <p className={styles.sectionHint}>Core identity and the vocabulary the rest of the app uses for this business type.</p>
      <div className={styles.grid}>
        <label className={styles.field}>Name<input value={name} onChange={(e) => setName(e.target.value)} /></label>
        <label className={styles.field}>Business type<input value={businessType} onChange={(e) => setBusinessType(e.target.value)} /></label>
        <label className={styles.field}>Timezone<input value={timezone} onChange={(e) => setTimezone(e.target.value)} /></label>
        <label className={styles.field}>Location<input value={location} onChange={(e) => setLocation(e.target.value)} /></label>
        <label className={styles.field}>Worker label (e.g. Dentist, Tutor, Barber)<input value={workerLabel} onChange={(e) => setWorkerLabel(e.target.value)} /></label>
        <label className={styles.field}>Customer label (e.g. Patient, Student, Client)<input value={customerLabel} onChange={(e) => setCustomerLabel(e.target.value)} /></label>
        <label className={styles.field}>Service label (e.g. Treatment, Session)<input value={serviceLabel} onChange={(e) => setServiceLabel(e.target.value)} /></label>
      </div>
      <div className={styles.actions}>
        <button className={styles.saveButton} onClick={() => onSave({ name, business_type: businessType, timezone, location, worker_label: workerLabel, customer_label: customerLabel, service_label: serviceLabel }).then(flash)}>
          Save business info
        </button>
        <SavedNote show={saved} />
      </div>
    </section>
  );
}

function ServicesSection({ profile, onSave }: { profile: BusinessProfile; onSave: SaveFn }) {
  const [services, setServices] = useState<ServiceOffering[]>(profile.services);
  const { saved, flash } = useSavedFlash();

  useEffect(() => setServices(profile.services), [profile]);

  function update(index: number, patch: Partial<ServiceOffering>) {
    setServices((current) => current.map((s, i) => (i === index ? { ...s, ...patch } : s)));
  }
  function addService() {
    setServices((current) => [...current, { id: `service-${current.length + 1}`, name: "New service", duration_minutes: 30, price: 0, eligible_roles: [], buffer_minutes: 0, allow_provider_preference: true }]);
  }
  function removeService(index: number) {
    setServices((current) => current.filter((_, i) => i !== index));
  }

  return (
    <section className={styles.section}>
      <h2>2. Services</h2>
      <p className={styles.sectionHint}>What this business offers — used for booking, availability, and incentive eligibility.</p>
      <div className={styles.rowList}>
        {services.map((service, index) => (
          <div className={styles.row} key={service.id}>
            <input aria-label="Service name" value={service.name} onChange={(e) => update(index, { name: e.target.value })} />
            <input aria-label="Duration (minutes)" type="number" min={5} value={service.duration_minutes} onChange={(e) => update(index, { duration_minutes: Number(e.target.value) })} />
            <input aria-label="Price" type="number" min={0} step="0.01" value={service.price} onChange={(e) => update(index, { price: Number(e.target.value) })} />
            <input aria-label="Eligible roles (comma-separated)" placeholder="Eligible roles" value={service.eligible_roles.join(", ")} onChange={(e) => update(index, { eligible_roles: e.target.value.split(",").map((r) => r.trim()).filter(Boolean) })} />
            <button className={styles.removeButton} onClick={() => removeService(index)} type="button">Remove</button>
          </div>
        ))}
      </div>
      <button className={styles.addButton} type="button" onClick={addService}>+ Add service</button>
      <div className={styles.actions}>
        <button className={styles.saveButton} onClick={() => onSave({ services }).then(flash)}>Save services</button>
        <SavedNote show={saved} />
      </div>
    </section>
  );
}

function WorkersSection({ profile, onSave }: { profile: BusinessProfile; onSave: SaveFn }) {
  const [workers, setWorkers] = useState<Worker[]>(profile.workers);
  const { saved, flash } = useSavedFlash();

  useEffect(() => setWorkers(profile.workers), [profile]);

  function update(index: number, patch: Partial<Worker>) {
    setWorkers((current) => current.map((w, i) => (i === index ? { ...w, ...patch } : w)));
  }
  function addWorker() {
    setWorkers((current) => [...current, { id: `worker-${current.length + 1}`, name: "New worker", role: profile.worker_label, service_ids: [], working_days: [], start_time: profile.open_time, end_time: profile.close_time, breaks: [], active: true }]);
  }
  function removeWorker(index: number) {
    setWorkers((current) => current.filter((_, i) => i !== index));
  }

  return (
    <section className={styles.section}>
      <h2>3. Workers</h2>
      <p className={styles.sectionHint}>The {profile.worker_label.toLowerCase()}s who take appointments, their role, and which services they can perform.</p>
      <div className={styles.rowList}>
        {workers.map((worker, index) => (
          <div className={styles.row} key={worker.id}>
            <input aria-label="Name" value={worker.name} onChange={(e) => update(index, { name: e.target.value })} />
            <input aria-label="Role" value={worker.role} onChange={(e) => update(index, { role: e.target.value })} />
            <input aria-label="Service ids (comma-separated)" placeholder="Service ids" value={worker.service_ids.join(", ")} onChange={(e) => update(index, { service_ids: e.target.value.split(",").map((s) => s.trim()).filter(Boolean) })} />
            <input aria-label="Start time" type="time" value={worker.start_time} onChange={(e) => update(index, { start_time: e.target.value })} />
            <input aria-label="End time" type="time" value={worker.end_time} onChange={(e) => update(index, { end_time: e.target.value })} />
            <label className={`${styles.field} ${styles.checkboxField}`}>
              <input type="checkbox" checked={worker.active} onChange={(e) => update(index, { active: e.target.checked })} /> Active
            </label>
            <button className={styles.removeButton} onClick={() => removeWorker(index)} type="button">Remove</button>
          </div>
        ))}
      </div>
      <button className={styles.addButton} type="button" onClick={addWorker}>+ Add {profile.worker_label.toLowerCase()}</button>
      <div className={styles.actions}>
        <button className={styles.saveButton} onClick={() => onSave({ workers }).then(flash)}>Save workers</button>
        <SavedNote show={saved} />
      </div>
    </section>
  );
}

function HoursSection({ profile, onSave }: { profile: BusinessProfile; onSave: SaveFn }) {
  const [openTime, setOpenTime] = useState(profile.open_time);
  const [closeTime, setCloseTime] = useState(profile.close_time);
  const [workingDays, setWorkingDays] = useState<string[]>(profile.working_days);
  const { saved, flash } = useSavedFlash();

  useEffect(() => { setOpenTime(profile.open_time); setCloseTime(profile.close_time); setWorkingDays(profile.working_days); }, [profile]);

  function toggleDay(day: string) {
    setWorkingDays((current) => current.includes(day) ? current.filter((d) => d !== day) : [...current, day]);
  }

  return (
    <section className={styles.section}>
      <h2>4. Working hours</h2>
      <p className={styles.sectionHint}>Drives the calendar grid, availability filtering, and voice-agent time-of-day matching.</p>
      <div className={styles.grid}>
        <label className={styles.field}>Opens<input type="time" value={openTime} onChange={(e) => setOpenTime(e.target.value)} /></label>
        <label className={styles.field}>Closes<input type="time" value={closeTime} onChange={(e) => setCloseTime(e.target.value)} /></label>
      </div>
      <div className={styles.grid} style={{ marginTop: 12 }}>
        {WEEKDAYS.map((day) => (
          <label key={day} className={`${styles.field} ${styles.checkboxField}`}>
            <input type="checkbox" checked={workingDays.includes(day)} onChange={() => toggleDay(day)} /> {day}
          </label>
        ))}
      </div>
      <div className={styles.actions}>
        <button className={styles.saveButton} onClick={() => onSave({ open_time: openTime, close_time: closeTime, working_days: workingDays }).then(flash)}>Save hours</button>
        <SavedNote show={saved} />
      </div>
    </section>
  );
}

function PolicySection({ profile, onSave }: { profile: BusinessProfile; onSave: SaveFn }) {
  const [autoRecoveryEnabled, setAutoRecoveryEnabled] = useState(profile.recovery_rules.auto_recovery_enabled);
  const [autoCallEnabled, setAutoCallEnabled] = useState(profile.recovery_rules.auto_call_enabled);
  const [candidateTimeoutSeconds, setCandidateTimeoutSeconds] = useState(profile.recovery_rules.candidate_timeout_seconds);
  const [maxRecoveryAttempts, setMaxRecoveryAttempts] = useState(profile.recovery_rules.max_recovery_attempts);
  const [incentiveFallbackEnabled, setIncentiveFallbackEnabled] = useState(profile.recovery_rules.incentive_fallback_enabled);

  const [maxDiscountPercent, setMaxDiscountPercent] = useState(profile.incentive_policy.max_discount_percent);
  const [minimumRevenue, setMinimumRevenue] = useState(profile.incentive_policy.minimum_revenue);
  const [incentiveScoreThreshold, setIncentiveScoreThreshold] = useState(profile.incentive_policy.incentive_score_threshold);
  const [excludedServices, setExcludedServices] = useState(profile.incentive_policy.excluded_services.join(", "));
  const [allowedIncentives, setAllowedIncentives] = useState<IncentivePolicy["allowed_incentives"]>(profile.incentive_policy.allowed_incentives);
  const { saved, flash } = useSavedFlash();

  useEffect(() => {
    setAutoRecoveryEnabled(profile.recovery_rules.auto_recovery_enabled);
    setAutoCallEnabled(profile.recovery_rules.auto_call_enabled);
    setCandidateTimeoutSeconds(profile.recovery_rules.candidate_timeout_seconds);
    setMaxRecoveryAttempts(profile.recovery_rules.max_recovery_attempts);
    setIncentiveFallbackEnabled(profile.recovery_rules.incentive_fallback_enabled);
    setMaxDiscountPercent(profile.incentive_policy.max_discount_percent);
    setMinimumRevenue(profile.incentive_policy.minimum_revenue);
    setIncentiveScoreThreshold(profile.incentive_policy.incentive_score_threshold);
    setExcludedServices(profile.incentive_policy.excluded_services.join(", "));
    setAllowedIncentives(profile.incentive_policy.allowed_incentives);
  }, [profile]);

  function updateIncentive(index: number, patch: Partial<IncentivePolicy["allowed_incentives"][number]>) {
    setAllowedIncentives((current) => current.map((inc, i) => (i === index ? { ...inc, ...patch } : inc)));
  }
  function addIncentive() {
    setAllowedIncentives((current) => [...current, { id: `incentive-${current.length + 1}`, type: "percent_discount", value: 10 }]);
  }
  function removeIncentive(index: number) {
    setAllowedIncentives((current) => current.filter((_, i) => i !== index));
  }

  function saveAll() {
    return onSave({
      recovery_rules: {
        auto_recovery_enabled: autoRecoveryEnabled,
        auto_call_enabled: autoCallEnabled,
        candidate_timeout_seconds: candidateTimeoutSeconds,
        max_recovery_attempts: maxRecoveryAttempts,
        incentive_fallback_enabled: incentiveFallbackEnabled,
      },
      incentive_policy: {
        max_discount_percent: maxDiscountPercent,
        minimum_revenue: minimumRevenue,
        allowed_incentives: allowedIncentives,
        incentive_time_threshold_hours: profile.incentive_policy.incentive_time_threshold_hours,
        excluded_services: excludedServices.split(",").map((s) => s.trim()).filter(Boolean),
        incentive_score_threshold: incentiveScoreThreshold,
      },
    }).then(flash);
  }

  return (
    <section className={styles.section}>
      <h2>5. Recovery &amp; incentive policy</h2>
      <p className={styles.sectionHint}>Governs the autonomous recovery scheduler and what Nemotron is allowed to offer to fill a cancelled slot.</p>

      <div className={styles.grid}>
        <label className={`${styles.field} ${styles.checkboxField}`}><input type="checkbox" checked={autoRecoveryEnabled} onChange={(e) => setAutoRecoveryEnabled(e.target.checked)} /> Automatic recovery enabled</label>
        <label className={styles.field}>Candidate timeout (seconds)<input type="number" min={5} value={candidateTimeoutSeconds} onChange={(e) => setCandidateTimeoutSeconds(Number(e.target.value))} /></label>
        <label className={styles.field}>Max recovery attempts<input type="number" min={1} value={maxRecoveryAttempts} onChange={(e) => setMaxRecoveryAttempts(Number(e.target.value))} /></label>
        <label className={`${styles.field} ${styles.checkboxField}`}><input type="checkbox" checked={incentiveFallbackEnabled} onChange={(e) => setIncentiveFallbackEnabled(e.target.checked)} /> Incentive fallback enabled</label>
      </div>

      <div className={styles.grid} style={{ marginTop: 14 }}>
        <label className={`${styles.field} ${styles.checkboxField}`}>
          <input type="checkbox" checked={autoCallEnabled} onChange={(e) => setAutoCallEnabled(e.target.checked)} /> Auto-call candidates (no approval click)
        </label>
      </div>
      <p className={styles.sectionHint} style={{ marginTop: 6 }}>
        When on, every candidate is called automatically as their turn comes up — first pass at full price,
        then the incentive pass above once everyone has declined or timed out. You are agreeing that Nemotron
        can place real outbound calls and offer the incentives configured below with no per-call approval.
        Off by default; the pending-approval queue on the dashboard is used instead.
      </p>

      <div className={styles.grid} style={{ marginTop: 14 }}>
        <label className={styles.field}>Max discount %<input type="number" min={0} max={100} value={maxDiscountPercent} onChange={(e) => setMaxDiscountPercent(Number(e.target.value))} /></label>
        <label className={styles.field}>Minimum revenue floor ($)<input type="number" min={0} value={minimumRevenue} onChange={(e) => setMinimumRevenue(Number(e.target.value))} /></label>
        <label className={styles.field}>Incentive match-score threshold<input type="number" min={0} max={1} step="0.05" value={incentiveScoreThreshold} onChange={(e) => setIncentiveScoreThreshold(Number(e.target.value))} /></label>
        <label className={styles.field}>Excluded services (comma-separated ids)<input value={excludedServices} onChange={(e) => setExcludedServices(e.target.value)} /></label>
      </div>

      <p className={styles.sectionHint} style={{ marginTop: 16 }}>Allowed incentive types</p>
      <div className={styles.rowList}>
        {allowedIncentives.map((incentive, index) => (
          <div className={styles.row} key={`${incentive.id}-${index}`}>
            <input aria-label="Incentive id" value={incentive.id} onChange={(e) => updateIncentive(index, { id: e.target.value })} />
            <input aria-label="Incentive type" value={incentive.type} onChange={(e) => updateIncentive(index, { type: e.target.value })} />
            <input aria-label="Incentive value" type="number" value={incentive.value} onChange={(e) => updateIncentive(index, { value: Number(e.target.value) })} />
            <button className={styles.removeButton} onClick={() => removeIncentive(index)} type="button">Remove</button>
          </div>
        ))}
      </div>
      <button className={styles.addButton} type="button" onClick={addIncentive}>+ Add incentive type</button>

      <div className={styles.actions}>
        <button className={styles.saveButton} onClick={saveAll}>Save recovery &amp; incentive policy</button>
        <SavedNote show={saved} />
      </div>
    </section>
  );
}
