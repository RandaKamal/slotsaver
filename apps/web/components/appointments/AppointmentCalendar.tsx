"use client";

import { useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import { Icon } from "@/components/ui/Icon";
import { cancelAppointment, fetchAppointments, fetchMetrics, fetchRecoveryPlanBySlot, recoverFromCancellation, type ApiAppointment, type DashboardMetrics, type RecoveryPlan } from "@/lib/api";
import { useBusinessProfile } from "@/lib/useBusinessProfile";
import { RecoveryPanel } from "@/components/recovery/RecoveryPanel";
import { addDays, dateLabel, DEFAULT_CLOSE_HOUR, DEFAULT_OPEN_HOUR, minutes, providers, sampleAppointments, timeLabel, validAppointment, visitTypes, weekStart, type Appointment } from "./appointment-data";
import styles from "./AppointmentCalendar.module.css";

// Simplest reliable live-demo mechanism: short-interval refetching. No
// realtime transport exists in this stack, so this is the polling window
// PASS criteria asks for rather than WebSockets.
const POLL_MS = 2000;

/** Locally-created (Milestone 1 demo) rows have a crypto.randomUUID() id;
 *  server-backed rows always use this shape. Used to refresh only the real
 *  half of the list on each poll without discarding local-only scratch data. */
function isServerEventId(id: string) {
  return /^slot-\d+$/.test(id);
}
function serverIdOf(event: Appointment): number | undefined {
  return (event as Appointment & { serverId?: number }).serverId;
}

/** Short, real (never fabricated) recovery-stage label. `undefined` plan
 *  means "haven't polled yet"; `null` means "polled, no plan exists yet" —
 *  both real states, not failures. */
function stageLabel(plan: RecoveryPlan | null | undefined): string {
  if (!plan) return "Cancellation detected · starting recovery";
  const total = plan.ranked_candidate_ids?.length ?? 0;
  const idx = plan.current_candidate_index ?? 0;
  if (plan.status === "pending") {
    if (total === 0) return "Finding matches…";
    return plan.stage === "INCENTIVE"
      ? `Incentive offer → candidate ${idx + 1} of ${total}`
      : `Calling candidate ${idx + 1} of ${total}`;
  }
  if (plan.status === "exhausted") {
    if (plan.stage === "INCENTIVE") {
      return plan.selected_incentive?.decision === "continue_full_price"
        ? "Queue exhausted · staying at full price"
        : "Queue exhausted · recovery stopped";
    }
    return "Queue exhausted · evaluating incentive";
  }
  if (plan.status === "filled") return "Appointment recovered ✓";
  if (plan.status === "no_candidates") return "No eligible patients found";
  if (plan.status === "ranking_failed") return "Ranking unavailable";
  return "Finding matches…";
}

function shortStageLabel(plan: RecoveryPlan | null | undefined): string {
  if (!plan) return "Open";
  if (plan.status === "pending") return plan.stage === "INCENTIVE" ? "Incentive offer" : "Calling…";
  if (plan.status === "exhausted") return "Exhausted";
  if (plan.status === "no_candidates") return "No matches";
  if (plan.status === "ranking_failed") return "Ranking failed";
  return "Open";
}

/** Backend row -> the calendar's local shape.
 *  `serverId` is kept so a cancellation can address the real DB row; UI-created
 *  events have no server record and simply omit it. */
function fromApi(row: ApiAppointment): Appointment & { serverId: number } {
  const [date, clock] = row.start_time.split("T");
  return {
    id: `slot-${row.id}`,
    serverId: row.id,
    patient: row.status === "booked" ? "Booked" : "Open slot",
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
  const profile = useBusinessProfile();
  const workerLabel = profile?.worker_label ?? "Provider";
  const customerLabel = profile?.customer_label ?? "Patient";
  const activeProviders = profile?.workers.filter((w) => w.active).map((w) => w.name) ?? [];
  const activeServices = profile?.services.map((s) => s.name) ?? [];
  const providerOptions: readonly string[] = activeProviders.length ? activeProviders : providers;
  const serviceOptions: readonly string[] = activeServices.length ? activeServices : visitTypes;
  const openHour = profile ? Number(profile.open_time.split(":")[0]) : DEFAULT_OPEN_HOUR;
  const closeHour = profile ? Number(profile.close_time.split(":")[0]) : DEFAULT_CLOSE_HOUR;
  const hours = Array.from({ length: Math.max(1, closeHour - openHour) }, (_, index) => index + openHour);

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
  const [recoveryPlans, setRecoveryPlans] = useState<Record<number, RecoveryPlan | null>>({});
  const [cancelling, setCancelling] = useState(false);

  useEffect(() => {
    // Independent of the appointments poll below - the metrics row and AI
    // status bar degrade gracefully (dashes, no invented numbers) if this
    // one fails without the calendar itself being affected. Polled so a
    // booking/cancellation elsewhere updates these without a page refresh.
    let stopped = false;
    const poll = () => fetchMetrics().then((m) => { if (!stopped) setMetrics(m); }).catch(() => { if (!stopped) setMetrics(null); });
    poll();
    const id = setInterval(poll, POLL_MS);
    return () => { stopped = true; clearInterval(id); };
  }, []);

  useEffect(() => {
    const date = localToday();
    setToday(date);
    setWeek(weekStart(date));

    // Real clinic rows when the API is up; fixtures otherwise, so the calendar
    // is never blank during a demo with the backend down. Polled (not a
    // one-shot fetch) so a cancellation, autonomous recovery step, or booking
    // made anywhere else shows up here without a manual refresh.
    let stopped = false;
    let weekInitialized = false;
    let sampleInitialized = false;
    const poll = () => fetchAppointments()
      .then((rows) => {
        if (stopped) return;
        setEvents((current) => [...rows.map(fromApi), ...current.filter((event) => !isServerEventId(event.id))]);
        setUsingSample(false);
        if (!weekInitialized && rows.length) {
          weekInitialized = true;
          setWeek(weekStart(rows[0].start_time.slice(0, 10)));
        }
      })
      .catch(() => {
        if (stopped || sampleInitialized) return;
        sampleInitialized = true;
        setEvents((current) => [...sampleAppointments(date), ...current.filter((event) => !isServerEventId(event.id))]);
        setUsingSample(true);
      });
    poll();
    const id = setInterval(poll, POLL_MS);
    return () => { stopped = true; clearInterval(id); };
  }, []);

  // Every currently-open, server-backed slot (not just this week's view) gets
  // its live recovery plan polled - this is how the calendar shows autonomous
  // progress (ranking, calls, decline/timeout advance, incentive, accept)
  // without depending on any button click.
  const openSlotServerIds = useMemo(
    () => events.filter((event) => event.status === "cancelled" && serverIdOf(event) !== undefined).map((event) => serverIdOf(event)!),
    [events],
  );
  const openSlotServerIdsKey = openSlotServerIds.slice().sort((a, b) => a - b).join(",");

  useEffect(() => {
    if (!openSlotServerIdsKey) return;
    const ids = openSlotServerIdsKey.split(",").map(Number);
    let stopped = false;
    const poll = () => Promise.all(
      ids.map((id) => fetchRecoveryPlanBySlot(id).then((plan) => [id, plan] as const).catch(() => [id, null] as const)),
    ).then((pairs) => {
      if (stopped) return;
      setRecoveryPlans((current) => ({ ...current, ...Object.fromEntries(pairs) }));
    });
    poll();
    const id = setInterval(poll, POLL_MS);
    return () => { stopped = true; clearInterval(id); };
  }, [openSlotServerIdsKey]);

  useEffect(() => {
    if (draft) dialog.current?.showModal();
  }, [draft]);

  function edit(event?: Appointment, date = today, time = "09:00") {
    setError("");
    setConfirmDelete(false);
    setDraft(event ?? { id: "", patient: "", date, time, duration: 60, provider: provider === "all" ? providerOptions[0] : provider, visitType: serviceOptions[0], status: "booked" });
  }
  function closeEditor() {
    dialog.current?.close();
    setDraft(null);
  }
  /** Cancels the appointment the editor is open on, server-side.
   *
   *  Deliberately NOT driven by the form's submit event. It used to be, and
   *  whether a cancellation happened depended on reading
   *  nativeEvent.submitter - null for a keyboard submit or a re-dispatched
   *  one - and on the whole form passing validAppointment first. Neither has
   *  anything to do with freeing a slot: an owner cancelling a real booking
   *  must not be blocked because some unrelated field is invalid, and a
   *  cancellation must never be inferred.
   */
  async function cancelDraft() {
    if (!draft) return;
    const serverId = serverIdOf(draft);
    if (serverId === undefined) {
      // A row that only exists in the browser (added in the UI, never saved)
      // has no server record to cancel - drop it locally and say so, rather
      // than silently doing nothing.
      setEvents((current) => current.map((item) => item.id === draft.id ? { ...item, status: "cancelled" } : item));
      setNotice("This appointment only existed in the calendar, so there was nothing to recover.");
      closeEditor();
      return;
    }

    // Only the cancellation itself is awaited - it's a single guarded UPDATE
    // and it's the part the owner is actually waiting on. Recovery is a
    // CONSEQUENCE of it (Nemotron ranking, the incentive gate, the call
    // brief: three or four model calls, tens of seconds when the endpoint is
    // throttled), so awaiting it here froze the dialog on "Cancelling…" for
    // the whole pipeline.
    setCancelling(true);
    setError("");
    try {
      await cancelAppointment(serverId);
    } catch {
      setError("Could not reach the server to cancel this appointment. Try again.");
      setCancelling(false);
      return;
    }
    setCancelling(false);
    setEvents((current) => current.map((item) => item.id === draft.id ? { ...item, status: "cancelled" } : item));
    setRecoveryId(draft.id);
    setNotice(`${draft.patient}’s appointment is cancelled — live recovery is starting below.`);
    closeEditor();

    // Kicks recovery off directly rather than waiting on the autonomous
    // scheduler. Fired once and not awaited: the panel below polls for the
    // plan and shows progress as it arrives. run_recovery claims the slot
    // before it ranks, so this racing the scheduler can no longer produce
    // two plans calling the same people.
    recoverFromCancellation(serverId)
      .then((plan) => setRecoveryPlans((current) => ({ ...current, [serverId]: plan })))
      .catch(() => { /* the panel keeps polling; the scheduler is the backstop */ });
  }

  /** One click: free the next booked slot in view and start recovery on it.
   *
   *  Same two calls the editor's cancel makes - this only saves opening the
   *  appointment first, which matters when the whole point is to show the
   *  chain start from a standing position.
   */
  async function startLiveRecovery() {
    const target = visible
      .filter((event) => event.status === "booked" && serverIdOf(event) !== undefined)
      .sort((a, b) => (a.date + a.time).localeCompare(b.date + b.time))[0];
    if (!target) {
      setError("No booked appointment in this week to open up.");
      return;
    }
    const serverId = serverIdOf(target)!;
    setCancelling(true);
    setError("");
    try {
      await cancelAppointment(serverId);
    } catch {
      setError("Could not reach the server to open this slot. Try again.");
      setCancelling(false);
      return;
    }
    setCancelling(false);
    setEvents((current) => current.map((item) => item.id === target.id ? { ...item, status: "cancelled" } : item));
    setRecoveryId(target.id);
    setNotice(`${timeLabel(target.time)} ${target.provider} is now open — finding the best match.`);
    recoverFromCancellation(serverId)
      .then((plan) => setRecoveryPlans((current) => ({ ...current, [serverId]: plan })))
      .catch(() => { /* the panel keeps polling; the scheduler is the backstop */ });
  }

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!draft) return;
    const isCancel = (event.nativeEvent as SubmitEvent).submitter?.getAttribute("value") === "cancel-appointment";
    const data = new FormData(event.currentTarget);
    const appointment: Appointment = {
      id: draft.id || crypto.randomUUID(),
      patient: String(data.get("patient")).trim(),
      provider: String(data.get("provider")),
      visitType: String(data.get("visitType")),
      date: String(data.get("date")),
      time: String(data.get("time")),
      duration: Number(data.get("duration")),
      status: isCancel ? "cancelled" : String(data.get("status")) as Appointment["status"],
    };
    if (!validAppointment(appointment, providerOptions, serviceOptions, openHour, closeHour)) {
      setError(`Add a ${customerLabel.toLowerCase()} name and a valid appointment between ${timeLabel(`${openHour}:00`)} and ${timeLabel(`${closeHour}:00`)}. Visits must last 15–180 minutes.`);
      return;
    }

    if (isCancel) {
      // Submit-based cancellation is handled by cancelDraft, wired directly
      // to the button's onClick. Reaching here means the submitter was not
      // readable, which used to fall through to the local-only branch below:
      // the row flipped to "cancelled" on screen, no request was ever sent,
      // and no error appeared - indistinguishable from a real cancellation
      // until you noticed nothing was ever called.
      await cancelDraft();
      return;
    }

    setEvents((current) => draft.id ? current.map((item) => item.id === draft.id ? appointment : item) : [...current, appointment]);
    setWeek(weekStart(appointment.date));
    setProvider("all");
    setNotice(appointment.status === "cancelled"
      ? `${appointment.patient}’s appointment is cancelled. Find matching ${customerLabel.toLowerCase()}s in the open slots section above the calendar.`
      : `${appointment.patient}’s appointment ${draft.id ? "updated" : "added"}.`);
    closeEditor();
  }
  function remove() {
    if (!draft) return;
    setEvents((current) => current.filter((item) => item.id !== draft.id));
    setNotice(`${draft.patient}’s appointment deleted.`);
    closeEditor();
  }
  async function importEvents(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const file = fileInput.current?.files?.[0];
    if (!file) return;
    try {
      if (file.size > 500_000) throw new Error("Choose a JSON file smaller than 500 KB.");
      const data: unknown = JSON.parse(await file.text());
      if (!Array.isArray(data) || data.length < 1 || data.length > 100
        || !data.every((item) => validAppointment(item, providerOptions, serviceOptions, openHour, closeHour))) {
        throw new Error(`Use the sample format with 1–100 valid appointments, listed ${workerLabel.toLowerCase()}s and services, within business hours.`);
      }
      const imported = data.map((item) => ({ ...item, id: crypto.randomUUID() }));
      setEvents((current) => [...current, ...imported]);
      setWeek(weekStart(imported[0].date));
      setProvider("all");
      setNotice(`${imported.length} appointments imported.`);
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
  const sample = JSON.stringify([{ patient: "Alex Morgan", provider: providerOptions[0], visitType: serviceOptions[0], date: today, time: `${String(openHour).padStart(2, "0")}:00`, duration: 60, status: "booked" }], null, 2);

  // Real numbers only - "—" rather than a guess when /api/appointments/metrics
  // is unreachable. Fill rate is derived client-side from the same two counts
  // the backend already returns, not a new backend field.
  const fillRateLabel = metrics && metrics.booked + metrics.open_slots > 0
    ? `${Math.round((metrics.booked / (metrics.booked + metrics.open_slots)) * 100)}%`
    : "—";
  // Live autonomous-recovery progress takes over the one status line whenever
  // there's a real, server-backed cancellation in flight - this is the "show
  // autonomous recovery progress visibly" requirement, without a separate
  // workflow dashboard.
  const activeRecoveries = events.filter((event) => event.status === "cancelled" && serverIdOf(event) !== undefined);
  const aiStatusText = activeRecoveries.length > 0
    ? `${activeRecoveries.length} slot${activeRecoveries.length === 1 ? "" : "s"} in autonomous recovery • ${stageLabel(recoveryPlans[serverIdOf(activeRecoveries[0])!])}`
    : metrics
      ? metrics.open_slots > 0
        ? `${metrics.open_slots} open ${metrics.open_slots === 1 ? "slot" : "slots"} detected • ${metrics.patients_waiting} ${customerLabel.toLowerCase()}${metrics.patients_waiting === 1 ? "" : "s"} waiting to be matched`
        : `All slots filled • ${metrics.patients_waiting} ${customerLabel.toLowerCase()}${metrics.patients_waiting === 1 ? "" : "s"} on the waiting list`
      : `${openings.length} open ${openings.length === 1 ? "slot" : "slots"} in this view • matching data unavailable`;

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <h1>Appointments</h1>
        <div className={styles.actions}>
          <button className={styles.secondary} onClick={() => { setImportError(""); if (fileInput.current) fileInput.current.value = ""; importDialog.current?.showModal(); }}>Import appointments</button>
          <button className={styles.primary} onClick={() => edit()}><span aria-hidden="true">＋</span> Add appointment</button>
        </div>
      </header>

      <div className={styles.aiBar} role="status">
        <span className={styles.aiBarDot} aria-hidden="true" />
        <Icon name="recovery" />
        <span>{aiStatusText}{usingSample ? " • sample data, API unreachable" : ""}</span>
        {metrics && <span className={styles.aiBarMetrics}>{metrics.booked} booked · {metrics.open_slots} open · {fillRateLabel} filled</span>}
      </div>

      {recoveryAppointment && <RecoveryPanel key={recoveryAppointment.id} appointment={recoveryAppointment} slotId={(recoveryAppointment as Appointment & { serverId?: number }).serverId} onClose={() => setRecoveryId(null)} />}
      <section className={styles.calendar} aria-label="Weekly appointment calendar">
        <div className={styles.toolbar}>
          <div className={styles.dateControls}>
            <button className={styles.secondary} onClick={() => setWeek(weekStart(today))}>Today</button>
            <button className={styles.arrow} aria-label="Previous week" onClick={() => setWeek(addDays(week, -7))}>‹</button>
            <button className={styles.arrow} aria-label="Next week" onClick={() => setWeek(addDays(week, 7))}>›</button>
            <h2 aria-live="polite">{dateLabel(week, { month: "short", day: "numeric" })} – {dateLabel(days[6], { month: "short", day: "numeric", year: "numeric" })}</h2>
            <button className={styles.primary} onClick={startLiveRecovery} disabled={cancelling}>{cancelling ? "Opening…" : "Open next slot"}</button>
          </div>
          <label className={styles.filter}><span className="sr-only">Filter by {workerLabel.toLowerCase()}</span><select aria-label={`Filter by ${workerLabel.toLowerCase()}`} value={provider} onChange={(event) => setProvider(event.target.value)}><option value="all">All {workerLabel.toLowerCase()}s</option>{providerOptions.map((name) => <option key={name}>{name}</option>)}</select><span className={styles.weekBadge}>Week view</span></label>
        </div>
        <div className={styles.calendarMeta}><span>{visible.filter((event) => event.status === "booked").length} booked · {visible.filter((event) => event.status === "cancelled").length} open</span><span>Local time · {timeLabel(`${openHour}:00`)}–{timeLabel(`${closeHour}:00`)}</span></div>
        <div className={styles.scroll} tabIndex={0} role="region" aria-label="Calendar. Scroll horizontally on smaller screens.">
          <div className={styles.weekGrid}>
            <div className={styles.dayHeaders}><div className={styles.timeHeading}><Icon name="calendar" /></div>{days.map((day) => <div key={day} className={`${styles.dayHeading} ${day === today ? styles.today : ""}`}><span>{dateLabel(day, { weekday: "short" })}</span><strong>{dateLabel(day, { day: "numeric" })}</strong>{day === today && <span className="sr-only">Today</span>}</div>)}</div>
            <div className={styles.body}>
              <div className={styles.timeColumn}>{hours.map((hour) => <div key={hour}>{timeLabel(`${hour}:00`).replace(":00", "")}</div>)}</div>
              {days.map((day) => <div key={day} className={`${styles.dayColumn} ${day === today ? styles.todayColumn : ""}`}>
                {hours.map((hour) => <button key={hour} className={styles.slot} aria-label={`Add appointment on ${dateLabel(day, { weekday: "long", month: "long", day: "numeric" })} at ${timeLabel(`${hour}:00`)}`} onClick={() => edit(undefined, day, `${String(hour).padStart(2, "0")}:00`)} />)}
                {arrange(visible.filter((event) => event.date === day)).map(({ event, lane, lanes }) => <button key={event.id} className={`${styles.event} ${event.status === "cancelled" ? styles.cancelled : styles.booked}`} style={{ top: (minutes(event.time) - openHour * 60) * 1.2, height: Math.max(event.duration * 1.2 - 4, 16), left: `calc(${lane / lanes * 100}% + 3px)`, width: `calc(${100 / lanes}% - 6px)` }} onClick={() => event.status === "cancelled" ? setRecoveryId(event.id) : edit(event)} aria-label={`${event.patient}, ${event.visitType}, ${event.provider}, ${timeLabel(event.time)}, ${event.status}. ${event.status === "cancelled" ? "Find matches" : "Edit appointment"}`} title={`${event.patient} · ${event.provider} · ${timeLabel(event.time)} · ${event.duration} min · ${event.status}${event.status === "cancelled" ? " · click to find matches" : ""}`}>
                  <strong>{event.patient}</strong>{event.duration >= 30 && <span>{event.visitType}</span>}{event.duration >= 45 && <span>{timeLabel(event.time)} · {event.duration} min</span>}{event.duration >= 60 && <span className={styles.eventProvider}>{event.status === "cancelled" ? (serverIdOf(event) !== undefined ? shortStageLabel(recoveryPlans[serverIdOf(event)!]) : "Open") : event.provider}</span>}
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
          <div className={styles.modalHeader}><div><p className="eyebrow">YOUR SCHEDULE</p><h2 id="appointment-title">{draft.id ? "Edit appointment" : "New appointment"}</h2></div><button type="button" className={styles.arrow} aria-label="Close appointment editor" onClick={closeEditor}>×</button></div>
          {serverIdOf(draft) !== undefined && <p className={styles.modalNote}>Cancelling this appointment starts recovery: matching {customerLabel.toLowerCase()}s are ranked and contacted automatically.</p>}
          <label className={styles.field}>{customerLabel} name<input name="patient" defaultValue={draft.patient} required maxLength={100} placeholder="e.g. Alex Morgan" autoFocus /></label>
          <div className={styles.fields}><label className={styles.field}>{workerLabel}<select aria-label={workerLabel} name="provider" defaultValue={draft.provider}>{providerOptions.map((name) => <option key={name}>{name}</option>)}</select></label><label className={styles.field}>Service<select aria-label="Service" name="visitType" defaultValue={draft.visitType}>{serviceOptions.map((name) => <option key={name}>{name}</option>)}</select></label></div>
          <div className={styles.fields}><label className={styles.field}>Date<input type="date" name="date" defaultValue={draft.date} required /></label><label className={styles.field}>Start time<input type="time" name="time" min={`${String(openHour).padStart(2, "0")}:00`} max={`${String(closeHour - 1).padStart(2, "0")}:45`} defaultValue={draft.time} required /></label></div>
          <div className={styles.fields}><label className={styles.field}>Duration (minutes)<input name="duration" type="number" min="15" max="180" step="1" defaultValue={draft.duration} required /></label><label className={styles.field}>Status<select aria-label="Status" name="status" defaultValue={draft.status}><option value="booked">Booked</option><option value="cancelled">Cancelled</option></select></label></div>
          {error && <p className={styles.error} role="alert">{error}</p>}
          {confirmDelete ? <div key="delete-confirmation" className={styles.deleteConfirmation}><p>Delete this appointment?</p><button type="button" className={styles.danger} onClick={remove}>Confirm delete</button><button type="button" className={styles.secondary} onClick={(event) => { event.preventDefault(); setConfirmDelete(false); }}>Keep appointment</button></div> : <div key="editor-actions" className={styles.modalActions}>{draft.id && <button type="button" className={styles.delete} onClick={() => setConfirmDelete(true)}>Delete appointment</button>}<button type="button" className={styles.secondary} onClick={closeEditor}>Close</button>{draft.id && draft.status === "booked" && <button type="button" onClick={cancelDraft} className={styles.secondary} disabled={cancelling}>{cancelling ? "Cancelling…" : "Cancel appointment"}</button>}<button type="submit" className={styles.primary} disabled={cancelling}>Save appointment</button></div>}
        </form>}
      </dialog>
      <dialog ref={importDialog} className={styles.dialog} aria-labelledby="import-title">
        <form onSubmit={importEvents}><div className={styles.modalHeader}><h2 id="import-title">Import appointments</h2><button type="button" className={styles.arrow} aria-label="Close import" onClick={() => importDialog.current?.close()}>×</button></div>
          <p className={styles.modalNote}>Add up to 100 appointments from a JSON file.</p>
          <a className={styles.download} href={`data:application/json;charset=utf-8,${encodeURIComponent(sample)}`} download="slotsaver-sample-appointments.json">Download sample JSON</a>
          <label className={styles.field}>Appointment file<input ref={fileInput} type="file" accept=".json,application/json" required onChange={() => setImportError("")} /></label>
          {importError && <p className={styles.error} role="alert">{importError}</p>}
          <div className={styles.modalActions}><button type="button" className={styles.secondary} onClick={() => importDialog.current?.close()}>Cancel</button><button type="submit" className={styles.primary}>Import appointments</button></div>
        </form>
      </dialog>
    </div>
  );
}
