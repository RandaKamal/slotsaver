"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import { Icon } from "@/components/ui/Icon";
import { fetchAppointments, fetchMetrics, type ApiAppointment, type DashboardMetrics } from "@/lib/api";
import { RecoveryPanel } from "@/components/recovery/RecoveryPanel";
import { addDays, dateLabel, minutes, providers, sampleAppointments, timeLabel, validAppointment, visitTypes, weekStart, type Appointment } from "./appointment-data";
import styles from "./AppointmentCalendar.module.css";

const hours = Array.from({ length: 12 }, (_, index) => index + 8);

/** Backend row -> the calendar's local shape.
 *  `serverId` is kept so a cancellation can address the real DB row; UI-created
 *  events have no server record and simply omit it. */
function fromApi(row: ApiAppointment): Appointment & { serverId: number } {
  const [date, clock] = row.start_time.split("T");
  return {
    id: `slot-${row.id}`,
    serverId: row.id,
    patient: row.status === "booked" ? "Booked patient" : "Open slot",
    provider: row.provider,
    visitType: row.service,
    date,
    time: clock.slice(0, 5),
    duration: row.duration_minutes,
    status: row.status === "booked" ? "booked" : "cancelled",
  };
}
function localToday() {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;
}

// Events that overlap get separate lanes instead of hiding one another.
function arrange(events: Appointment[]) {
  const ends: number[] = [];
  const placed = [...events].sort((a, b) => minutes(a.time) - minutes(b.time)).map((event) => {
    let lane = ends.findIndex((end) => end <= minutes(event.time));
    if (lane < 0) lane = ends.length;
    ends[lane] = minutes(event.time) + event.duration;
    return { event, lane };
  });
  return placed.map((item) => ({ ...item, lanes: ends.length }));
}

export function AppointmentCalendar() {
  const [today, setToday] = useState("");
  const [week, setWeek] = useState("");
  const [events, setEvents] = useState<Appointment[]>([]);
  const [provider, setProvider] = useState("all");
  const [notice, setNotice] = useState("");
  const [recoveryId, setRecoveryId] = useState<string | null>(null);
  const [draft, setDraft] = useState<Appointment | null>(null);
  const [error, setError] = useState("");
  const [confirmDelete, setConfirmDelete] = useState(false);
  const dialog = useRef<HTMLDialogElement>(null);
  const importDialog = useRef<HTMLDialogElement>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  const [importError, setImportError] = useState("");
  const [usingSample, setUsingSample] = useState(false);
  const [metrics, setMetrics] = useState<DashboardMetrics | null>(null);

  useEffect(() => {
    // Independent of the appointments fetch below - the metrics row and AI
    // status bar degrade gracefully (dashes, no invented numbers) if this
    // one fails without the calendar itself being affected.
    fetchMetrics()
      .then(setMetrics)
      .catch(() => setMetrics(null));
  }, []);

  useEffect(() => {
    const date = localToday();
    setToday(date);
    setWeek(weekStart(date));

    // Real clinic rows when the API is up; fixtures otherwise, so the calendar
    // is never blank during a demo with the backend down.
    const controller = new AbortController();
    fetchAppointments(controller.signal)
      .then((rows) => {
        setEvents(rows.map(fromApi));
        setUsingSample(false);
        if (rows.length) setWeek(weekStart(rows[0].start_time.slice(0, 10)));
      })
      .catch(() => {
        setEvents(sampleAppointments(date));
        setUsingSample(true);
      });
    return () => controller.abort();
  }, []);

  useEffect(() => {
    if (draft) dialog.current?.showModal();
  }, [draft]);

  function edit(event?: Appointment, date = today, time = "09:00") {
    setError("");
    setConfirmDelete(false);
    setDraft(event ?? { id: "", patient: "", date, time, duration: 60, provider: provider === "all" ? providers[0] : provider, visitType: visitTypes[0], status: "booked" });
  }
  function closeEditor() {
    dialog.current?.close();
    setDraft(null);
  }
  function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!draft) return;
    const data = new FormData(event.currentTarget);
    const appointment: Appointment = {
      id: draft.id || crypto.randomUUID(),
      patient: String(data.get("patient")).trim(),
      provider: String(data.get("provider")),
      visitType: String(data.get("visitType")),
      date: String(data.get("date")),
      time: String(data.get("time")),
      duration: Number(data.get("duration")),
      status: (event.nativeEvent as SubmitEvent).submitter?.getAttribute("value") === "cancel-appointment"
        ? "cancelled"
        : String(data.get("status")) as Appointment["status"],
    };
    if (!validAppointment(appointment)) {
      setError("Add a patient name and a valid appointment between 8 AM and 6 PM. Visits must last 15–180 minutes and end by 6 PM.");
      return;
    }
    setEvents((current) => draft.id ? current.map((item) => item.id === draft.id ? appointment : item) : [...current, appointment]);
    setWeek(weekStart(appointment.date));
    setProvider("all");
    setNotice(appointment.status === "cancelled"
      ? `${appointment.patient}’s appointment is cancelled. Find matching patients in the open slots section above the calendar.`
      : `${appointment.patient}’s appointment ${draft.id ? "updated" : "added"}. Changes are saved in this preview only.`);
    closeEditor();
  }
  function remove() {
    if (!draft) return;
    setEvents((current) => current.filter((item) => item.id !== draft.id));
    setNotice(`${draft.patient}’s appointment deleted from the preview.`);
    closeEditor();
  }
  async function importEvents(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const file = fileInput.current?.files?.[0];
    if (!file) return;
    try {
      if (file.size > 500_000) throw new Error("Choose a JSON file smaller than 500 KB.");
      const data: unknown = JSON.parse(await file.text());
      if (!Array.isArray(data) || data.length < 1 || data.length > 100 || !data.every(validAppointment)) {
        throw new Error("Use the sample format with 1–100 valid appointments, listed providers and visit types, and visits between 8 AM and 6 PM.");
      }
      const imported = data.map((item) => ({ ...item, id: crypto.randomUUID() }));
      setEvents((current) => [...current, ...imported]);
      setWeek(weekStart(imported[0].date));
      setProvider("all");
      setNotice(`${imported.length} appointments imported into this preview. Nothing was uploaded to a server.`);
      importDialog.current?.close();
    } catch (caught) {
      setImportError(caught instanceof SyntaxError ? "This file is not valid JSON. Download the sample format and try again." : (caught as Error).message);
    }
  }

  if (!week) return <div className={styles.page}><h1>Appointments</h1><p role="status">Loading your calendar…</p></div>;
  const days = Array.from({ length: 7 }, (_, index) => addDays(week, index));
  const visible = events.filter((event) => days.includes(event.date) && (provider === "all" || provider === event.provider));
  const openings = visible.filter((event) => event.status === "cancelled");
  const recoveryAppointment = events.find((event) => event.id === recoveryId && event.status === "cancelled");
  const sample = JSON.stringify([{ patient: "Alex Morgan", provider: "Dr. Lee", visitType: "Follow-up", date: today, time: "10:00", duration: 60, status: "booked" }], null, 2);

  // Real numbers only - "—" rather than a guess when /api/appointments/metrics
  // is unreachable. Fill rate is derived client-side from the same two counts
  // the backend already returns, not a new backend field.
  const fillRateLabel = metrics && metrics.booked + metrics.open_slots > 0
    ? `${Math.round((metrics.booked / (metrics.booked + metrics.open_slots)) * 100)}%`
    : "—";
  const aiStatusText = metrics
    ? metrics.open_slots > 0
      ? `${metrics.open_slots} open ${metrics.open_slots === 1 ? "slot" : "slots"} detected • ${metrics.patients_waiting} ${metrics.patients_waiting === 1 ? "patient" : "patients"} waiting to be matched`
      : `All slots filled • ${metrics.patients_waiting} ${metrics.patients_waiting === 1 ? "patient" : "patients"} on the waiting list`
    : `${openings.length} open ${openings.length === 1 ? "slot" : "slots"} in this view • patient-matching data unavailable`;

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <h1>Appointments</h1>
        <div className={styles.actions}>
          <button className={styles.secondary} onClick={() => { setImportError(""); if (fileInput.current) fileInput.current.value = ""; importDialog.current?.showModal(); }}>Import appointments</button>
          <button className={styles.primary} onClick={() => edit()}><span aria-hidden="true">＋</span> Add appointment</button>
        </div>
      </header>

      <div className={styles.statsRow}>
        <div className={styles.stat}><span className={styles.statLabel}>Open slots</span><span className={styles.statValue}>{metrics?.open_slots ?? "—"}</span></div>
        <div className={styles.stat}><span className={styles.statLabel}>Booked</span><span className={styles.statValue}>{metrics?.booked ?? "—"}</span></div>
        <div className={styles.stat}><span className={styles.statLabel}>Fill rate</span><span className={styles.statValue}>{fillRateLabel}</span></div>
      </div>

      <div className={styles.aiBar} role="status">
        <span className={styles.aiBarDot} aria-hidden="true" />
        <Icon name="recovery" />
        <span>{aiStatusText}{usingSample ? " • sample data, API unreachable" : ""}</span>
      </div>

      {openings.length > 0 && <section className={styles.openSlots} aria-label="Open slots">
        <div className={styles.openSlotsHeading}><Icon name="recovery" /> {openings.length} {openings.length === 1 ? "opening" : "openings"}</div>
        <div className={styles.openSlotsList}>{openings.map((slot) => <div key={slot.id} className={styles.openSlot}>
          <span>{dateLabel(slot.date, { weekday: "short", month: "short", day: "numeric" })} · {timeLabel(slot.time)}</span>
          <em>{slot.visitType} · {slot.provider} · cancelled by {slot.patient}</em>
          <button type="button" className={styles.secondary} onClick={() => setRecoveryId(slot.id)} aria-label={`Find matching patients for ${slot.patient}’s cancelled appointment`}>Find matches →</button>
        </div>)}</div>
      </section>}
      {recoveryAppointment && <RecoveryPanel key={recoveryAppointment.id} appointment={recoveryAppointment} slotId={(recoveryAppointment as Appointment & { serverId?: number }).serverId} onClose={() => setRecoveryId(null)} />}
      <section className={styles.calendar} aria-label="Weekly appointment calendar">
        <div className={styles.toolbar}>
          <div className={styles.dateControls}>
            <button className={styles.secondary} onClick={() => setWeek(weekStart(today))}>Today</button>
            <button className={styles.arrow} aria-label="Previous week" onClick={() => setWeek(addDays(week, -7))}>‹</button>
            <button className={styles.arrow} aria-label="Next week" onClick={() => setWeek(addDays(week, 7))}>›</button>
            <h2 aria-live="polite">{dateLabel(week, { month: "short", day: "numeric" })} – {dateLabel(days[6], { month: "short", day: "numeric", year: "numeric" })}</h2>
          </div>
          <label className={styles.filter}><span className="sr-only">Filter by provider</span><select aria-label="Filter by provider" value={provider} onChange={(event) => setProvider(event.target.value)}><option value="all">All providers</option>{providers.map((name) => <option key={name}>{name}</option>)}</select><span className={styles.weekBadge}>Week view</span></label>
        </div>
        <div className={styles.calendarMeta}><span>{visible.filter((event) => event.status === "booked").length} booked · {visible.filter((event) => event.status === "cancelled").length} open</span><span>Local time · 8 AM–6 PM</span></div>
        <div className={styles.scroll} tabIndex={0} role="region" aria-label="Calendar. Scroll horizontally on smaller screens.">
          <div className={styles.weekGrid}>
            <div className={styles.dayHeaders}><div className={styles.timeHeading}><Icon name="calendar" /></div>{days.map((day) => <div key={day} className={`${styles.dayHeading} ${day === today ? styles.today : ""}`}><span>{dateLabel(day, { weekday: "short" })}</span><strong>{dateLabel(day, { day: "numeric" })}</strong>{day === today && <span className="sr-only">Today</span>}</div>)}</div>
            <div className={styles.body}>
              <div className={styles.timeColumn}>{hours.map((hour) => <div key={hour}>{timeLabel(`${hour}:00`).replace(":00", "")}</div>)}</div>
              {days.map((day) => <div key={day} className={`${styles.dayColumn} ${day === today ? styles.todayColumn : ""}`}>
                {hours.map((hour) => <button key={hour} className={styles.slot} aria-label={`Add appointment on ${dateLabel(day, { weekday: "long", month: "long", day: "numeric" })} at ${timeLabel(`${hour}:00`)}`} onClick={() => edit(undefined, day, `${String(hour).padStart(2, "0")}:00`)} />)}
                {arrange(visible.filter((event) => event.date === day)).map(({ event, lane, lanes }) => <button key={event.id} className={`${styles.event} ${event.status === "cancelled" ? styles.cancelled : styles.booked}`} style={{ top: (minutes(event.time) - 480) * 1.2, height: Math.max(event.duration * 1.2 - 4, 16), left: `calc(${lane / lanes * 100}% + 3px)`, width: `calc(${100 / lanes}% - 6px)` }} onClick={() => edit(event)} aria-label={`${event.patient}, ${event.visitType}, ${event.provider}, ${timeLabel(event.time)}, ${event.status}. Edit appointment`} title={`${event.patient} · ${event.provider} · ${timeLabel(event.time)} · ${event.duration} min · ${event.status}`}>
                  <strong>{event.patient}</strong>{event.duration >= 30 && <span>{event.visitType}</span>}{event.duration >= 45 && <span>{timeLabel(event.time)} · {event.duration} min</span>}{event.duration >= 60 && <span className={styles.eventProvider}>{event.status === "cancelled" ? "Open" : event.provider}</span>}
                </button>)}
              </div>)}
            </div>
          </div>
        </div>
        <footer className={styles.legend}><span><i /> Booked</span><span><i className={styles.cancelledDot} /> Open</span><span className={styles.hint}>Click an open time to add. Click an appointment to edit.</span></footer>
      </section>
      {visible.length === 0 && <p className={styles.empty}>No appointments for this week{provider !== "all" ? ` with ${provider}` : ""}. Choose an open time to add one.</p>}
      {notice && <p className={styles.notice} role="status">{notice}</p>}

      <dialog ref={dialog} className={styles.dialog} aria-labelledby="appointment-title" onClose={() => setDraft(null)}>
        {draft && <form onSubmit={save} key={draft.id || `${draft.date}-${draft.time}`}>
          <div className={styles.modalHeader}><div><p className="eyebrow">YOUR CLINIC SCHEDULE</p><h2 id="appointment-title">{draft.id ? "Edit appointment" : "New appointment"}</h2></div><button type="button" className={styles.arrow} aria-label="Close appointment editor" onClick={closeEditor}>×</button></div>
          <p className={styles.modalNote}>Sample data only. This won’t book or contact a patient.</p>
          <label className={styles.field}>Patient name<input name="patient" defaultValue={draft.patient} required maxLength={100} placeholder="e.g. Alex Morgan" autoFocus /></label>
          <div className={styles.fields}><label className={styles.field}>Provider<select aria-label="Provider" name="provider" defaultValue={draft.provider}>{providers.map((name) => <option key={name}>{name}</option>)}</select></label><label className={styles.field}>Visit type<select aria-label="Visit type" name="visitType" defaultValue={draft.visitType}>{visitTypes.map((name) => <option key={name}>{name}</option>)}</select></label></div>
          <div className={styles.fields}><label className={styles.field}>Date<input type="date" name="date" defaultValue={draft.date} required /></label><label className={styles.field}>Start time<input type="time" name="time" min="08:00" max="17:45" defaultValue={draft.time} required /></label></div>
          <div className={styles.fields}><label className={styles.field}>Duration (minutes)<input name="duration" type="number" min="15" max="180" step="1" defaultValue={draft.duration} required /></label><label className={styles.field}>Status<select aria-label="Status" name="status" defaultValue={draft.status}><option value="booked">Booked</option><option value="cancelled">Cancelled</option></select></label></div>
          {error && <p className={styles.error} role="alert">{error}</p>}
          {confirmDelete ? <div key="delete-confirmation" className={styles.deleteConfirmation}><p>Delete this appointment from the preview?</p><button type="button" className={styles.danger} onClick={remove}>Confirm delete</button><button type="button" className={styles.secondary} onClick={(event) => { event.preventDefault(); setConfirmDelete(false); }}>Keep appointment</button></div> : <div key="editor-actions" className={styles.modalActions}>{draft.id && <button type="button" className={styles.delete} onClick={() => setConfirmDelete(true)}>Delete appointment</button>}<button type="button" className={styles.secondary} onClick={closeEditor}>Cancel</button>{draft.id && draft.status === "booked" && <button type="submit" name="intent" value="cancel-appointment" className={styles.secondary}>Cancel appointment</button>}<button type="submit" className={styles.primary}>Save appointment</button></div>}
        </form>}
      </dialog>
      <dialog ref={importDialog} className={styles.dialog} aria-labelledby="import-title">
        <form onSubmit={importEvents}><div className={styles.modalHeader}><h2 id="import-title">Import appointments</h2><button type="button" className={styles.arrow} aria-label="Close import" onClick={() => importDialog.current?.close()}>×</button></div>
          <p className={styles.modalNote}>Add up to 100 appointments from a JSON file to this local preview. Nothing is uploaded or saved to your clinic’s system.</p>
          <a className={styles.download} href={`data:application/json;charset=utf-8,${encodeURIComponent(sample)}`} download="slotsaver-sample-appointments.json">Download sample JSON</a>
          <label className={styles.field}>Appointment file<input ref={fileInput} type="file" accept=".json,application/json" required onChange={() => setImportError("")} /></label>
          {importError && <p className={styles.error} role="alert">{importError}</p>}
          <div className={styles.modalActions}><button type="button" className={styles.secondary} onClick={() => importDialog.current?.close()}>Cancel</button><button type="submit" className={styles.primary}>Import into preview</button></div>
        </form>
      </dialog>
    </div>
  );
}
