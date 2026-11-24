import * as React from "react";
import type {
  AppUser, ApiKey, ChatMessage, Conversation, DateRange, DateRangePreset, Driver, FleetSnapshot, Geofence, MaintenanceRecord,
  Notification, SafetyEvent, ScheduledReport, Settings, Vehicle, AuditEntry,
} from "@/types";
import { api } from "@/services/api";
import { dataMode, type DataMode } from "@/services/mode";
import { fetchAlerts, fetchAlertSettings, fromServerGeofence, mergeAlerts, rememberRead, saveAlertSettings, toServerGeofence, type AlertSettings } from "@/services/alerts";
import { applyLivePositions, fetchGold, mergeLive, type LiveResp } from "@/services/live";
import { makeFormatter, type Fmt } from "@/lib/format";
import { makeRange } from "@/lib/metrics";
import { uid } from "@/lib/utils";

type State = { snapshot: FleetSnapshot | null; range: DateRange; fleetFilter: string; loading: boolean };

type Action =
  | { type: "loaded"; snapshot: FleetSnapshot }
  | { type: "range"; preset: DateRangePreset }
  | { type: "fleetFilter"; value: string }
  | { type: "patch"; fn: (s: FleetSnapshot) => FleetSnapshot };

function reducer(state: State, a: Action): State {
  switch (a.type) {
    case "loaded": return { ...state, snapshot: a.snapshot, loading: false };
    case "range": return { ...state, range: makeRange(a.preset) };
    case "fleetFilter": return { ...state, fleetFilter: a.value };
    case "patch": return state.snapshot ? { ...state, snapshot: a.fn(state.snapshot) } : state;
  }
}

const audit = (s: FleetSnapshot, action: string, target: string): AuditEntry[] =>
  [{ id: uid("A"), time: new Date().toISOString(), actor: s.users[0]?.name ?? "You", action, target }, ...s.audit].slice(0, 200);

export interface FleetActions {
  setRange(p: DateRangePreset): void;
  setFleetFilter(v: string): void;
  addVehicle(v: Omit<Vehicle, "id" | "status" | "position" | "heading" | "speedKmh" | "ignitionOn" | "lastUpdate" | "device"> & { id?: string }): Vehicle;
  updateVehicle(id: string, patch: Partial<Vehicle>): void;
  archiveVehicle(id: string): void;
  assignDriver(vehicleId: string, driverId?: string): void;
  addDriver(d: Omit<Driver, "id" | "status" | "coaching">): Driver;
  updateDriver(id: string, patch: Partial<Driver>): void;
  addCoaching(driverId: string, topic: string, notes: string): void;
  scheduleMaintenance(m: Omit<MaintenanceRecord, "id" | "status">, status?: MaintenanceRecord["status"]): void;
  completeMaintenance(id: string, cost: number, provider: string, notes?: string): void;
  addGeofence(g: Omit<Geofence, "id">): void;
  updateGeofence(id: string, patch: Partial<Geofence>): void;
  deleteGeofence(id: string): void;
  acknowledgeSafety(id: string, note?: string): void;
  markNotification(id: string, read: boolean): void;
  markAllRead(): void;
  updateSettings(patch: Partial<Settings>): void;
  addUser(u: Omit<AppUser, "id" | "lastActive" | "active">): void;
  updateUser(id: string, patch: Partial<AppUser>): void;
  addApiKey(name: string, scopes: string[]): ApiKey;
  revokeApiKey(id: string): void;
  setIntegrationStatus(id: string, status: "connected" | "available"): void;
  saveConversation(c: Conversation): void;
  appendMessage(convId: string, m: ChatMessage): void;
  addScheduledReport(r: Omit<ScheduledReport, "id">): void;
  removeScheduledReport(id: string): void;
  resetDemo(): Promise<void>;
  applyLive(resp: LiveResp): void;
  saveAlertSettings(s: AlertSettings): Promise<AlertSettings>;
}

const Ctx = React.createContext<(State & { mode: DataMode; alertSettings: AlertSettings | null; liveStatus: "off" | "ok" | "error"; fmt: Fmt; actions: FleetActions }) | null>(null);

export function FleetProvider({ children }: { children: React.ReactNode }) {
  const [state, dispatch] = React.useReducer(reducer, { snapshot: null, range: makeRange("7d"), fleetFilter: "all", loading: true });

  const mode: DataMode = dataMode();
  const [liveStatus, setLiveStatus] = React.useState<"off" | "ok" | "error">(mode === "live" ? "error" : "off");

  React.useEffect(() => { api.load().then((snapshot) => dispatch({ type: "loaded", snapshot })); }, []);

  // Live tracker data: poll every 15 s when the backend is configured (config.js present).
  React.useEffect(() => {
    if (mode !== "live" || !state.snapshot) return;
    let stop = false;
    const tick = () => fetchGold().then((g) => { if (!stop) { dispatch({ type: "patch", fn: (s) => mergeLive(s, g) }); setLiveStatus("ok"); } }).catch(() => { if (!stop) setLiveStatus("error"); });
    void tick();
    const h = setInterval(tick, 15_000);
    return () => { stop = true; clearInterval(h); };
  }, [state.snapshot === null]); // eslint-disable-line react-hooks/exhaustive-deps

  // Alerts (live accounts): settings + geofences from the server, alert list polled every 30 s.
  const [alertSettings, setAlertSettings] = React.useState<AlertSettings | null>(null);
  const fenceSent = React.useRef<string>("");
  React.useEffect(() => {
    if (mode !== "live" || !state.snapshot) return;
    let stop = false;
    fetchAlertSettings().then((st) => {
      if (stop) return;
      setAlertSettings(st);
      fenceSent.current = JSON.stringify(st.geofences);
      dispatch({ type: "patch", fn: (s) => ({ ...s, geofences: st.geofences.map(fromServerGeofence) }) });   // server is the source of truth
    }).catch(() => { /* settings unavailable: alerts page shows an error on save */ });
    const tick = () => fetchAlerts().then((a) => { if (!stop) dispatch({ type: "patch", fn: (s) => mergeAlerts(s, a) }); }).catch(() => {});
    void tick();
    const h = setInterval(tick, 30_000);
    return () => { stop = true; clearInterval(h); };
  }, [state.snapshot === null]); // eslint-disable-line react-hooks/exhaustive-deps

  // Geofence edits in a live account are saved to the server (debounced) so alerts use them.
  React.useEffect(() => {
    if (mode !== "live" || !alertSettings || !state.snapshot) return;
    const fences = state.snapshot.geofences.map(toServerGeofence).filter((g): g is NonNullable<typeof g> => g !== null);
    const sig = JSON.stringify(fences);
    if (sig === fenceSent.current) return;
    const h = setTimeout(() => {
      fenceSent.current = sig;
      saveAlertSettings({ ...alertSettings, geofences: fences }).then(setAlertSettings).catch(() => { fenceSent.current = ""; });
    }, 800);
    return () => clearTimeout(h);
  }, [state.snapshot?.geofences, alertSettings]); // eslint-disable-line react-hooks/exhaustive-deps

  // persist (debounced)
  React.useEffect(() => {
    if (!state.snapshot) return;
    const h = setTimeout(() => { void api.save(state.snapshot!); }, 400);
    return () => clearTimeout(h);
  }, [state.snapshot]);

  const patch = React.useCallback((fn: (s: FleetSnapshot) => FleetSnapshot) => dispatch({ type: "patch", fn }), []);

  const actions = React.useMemo<FleetActions>(() => ({
    setRange: (p) => dispatch({ type: "range", preset: p }),
    setFleetFilter: (v) => dispatch({ type: "fleetFilter", value: v }),
    addVehicle: (input) => {
      const id = input.id ?? `V-${100 + Math.floor(Math.random() * 800) + 100}`;
      const v: Vehicle = {
        ...input, id, status: "offline", position: { lat: 43.4354, lng: -79.7085 }, heading: 0, speedKmh: 0, ignitionOn: false,
        lastUpdate: new Date().toISOString(), device: { id: "pending", model: "Awaiting device assignment", installedOn: new Date().toISOString(), source: "demo" },
      };
      patch((s) => ({ ...s, vehicles: [...s.vehicles, v], audit: audit(s, "Added vehicle", `${v.name} (${v.registration})`) }));
      return v;
    },
    updateVehicle: (id, p) => patch((s) => ({ ...s, vehicles: s.vehicles.map((v) => (v.id === id ? { ...v, ...p } : v)), audit: audit(s, "Edited vehicle", id) })),
    archiveVehicle: (id) => patch((s) => ({ ...s, vehicles: s.vehicles.map((v) => (v.id === id ? { ...v, archived: true, driverId: undefined } : v)), drivers: s.drivers.map((d) => (d.vehicleId === id ? { ...d, vehicleId: undefined } : d)), audit: audit(s, "Archived vehicle", id) })),
    assignDriver: (vehicleId, driverId) => patch((s) => ({
      ...s,
      vehicles: s.vehicles.map((v) => (v.id === vehicleId ? { ...v, driverId } : v.driverId === driverId ? { ...v, driverId: undefined } : v)),
      drivers: s.drivers.map((d) => (d.id === driverId ? { ...d, vehicleId } : d.vehicleId === vehicleId ? { ...d, vehicleId: undefined } : d)),
      audit: audit(s, "Assigned driver", `${driverId ?? "none"} → ${vehicleId}`),
    })),
    addDriver: (input) => {
      const d: Driver = { ...input, id: `D-${String(Math.floor(Math.random() * 900) + 100)}`, status: "available", coaching: [] };
      patch((s) => ({ ...s, drivers: [...s.drivers, d], audit: audit(s, "Added driver", d.name) }));
      return d;
    },
    updateDriver: (id, p) => patch((s) => ({ ...s, drivers: s.drivers.map((d) => (d.id === id ? { ...d, ...p } : d)) })),
    addCoaching: (driverId, topic, notes) => patch((s) => ({ ...s, drivers: s.drivers.map((d) => (d.id === driverId ? { ...d, coaching: [{ id: uid("C"), date: new Date().toISOString(), topic, notes, coach: s.users[0]?.name ?? "You" }, ...d.coaching] } : d)), audit: audit(s, "Logged coaching", driverId) })),
    scheduleMaintenance: (m, status = "scheduled") => patch((s) => ({ ...s, maintenance: [{ ...m, id: uid("M"), status }, ...s.maintenance], audit: audit(s, status === "completed" ? "Recorded service" : "Scheduled maintenance", `${m.vehicleId} · ${m.type}`) })),
    completeMaintenance: (id, cost, provider, notes) => patch((s) => {
      const rec = s.maintenance.find((m) => m.id === id);
      const vehicles = rec && rec.type === "Oil Change" ? s.vehicles.map((v) => (v.id === rec.vehicleId ? { ...v, lastServiceDate: new Date().toISOString(), nextServiceKm: v.odometerKm + 8000, nextServiceDate: new Date(Date.now() + 180 * 864e5).toISOString() } : v)) : s.vehicles;
      return { ...s, vehicles, maintenance: s.maintenance.map((m) => (m.id === id ? { ...m, status: "completed", cost, provider, notes, date: new Date().toISOString() } : m)), audit: audit(s, "Completed maintenance", id) };
    }),
    addGeofence: (g) => patch((s) => ({ ...s, geofences: [...s.geofences, { ...g, id: uid("G") }], audit: audit(s, "Created geofence", g.name) })),
    updateGeofence: (id, p) => patch((s) => ({ ...s, geofences: s.geofences.map((g) => (g.id === id ? { ...g, ...p } : g)) })),
    deleteGeofence: (id) => patch((s) => ({ ...s, geofences: s.geofences.filter((g) => g.id !== id), audit: audit(s, "Deleted geofence", id) })),
    acknowledgeSafety: (id, note) => patch((s) => ({ ...s, safety: s.safety.map((e): SafetyEvent => (e.id === id ? { ...e, acknowledged: true, reviewNote: note, reviewedBy: s.users[0]?.name } : e)), audit: audit(s, "Acknowledged safety event", id) })),
    markNotification: (id, read) => { if (id.startsWith("AL-")) rememberRead([id], read); patch((s) => ({ ...s, notifications: s.notifications.map((n): Notification => (n.id === id ? { ...n, read } : n)) })); },
    markAllRead: () => patch((s) => { rememberRead(s.notifications.filter((n) => n.id.startsWith("AL-")).map((n) => n.id), true); return { ...s, notifications: s.notifications.map((n) => ({ ...n, read: true })) }; }),
    updateSettings: (p) => patch((s) => ({ ...s, settings: { ...s.settings, ...p }, audit: audit(s, "Changed settings", Object.keys(p).join(", ")) })),
    addUser: (u) => patch((s) => ({ ...s, users: [...s.users, { ...u, id: uid("U"), lastActive: new Date().toISOString(), active: true }], audit: audit(s, "Invited user", `${u.email} (${u.role})`) })),
    updateUser: (id, p) => patch((s) => ({ ...s, users: s.users.map((u) => (u.id === id ? { ...u, ...p } : u)) })),
    addApiKey: (name, scopes) => {
      const k: ApiKey = { id: uid("K"), name, prefix: `fp_live_${Math.random().toString(36).slice(2, 6)}`, created: new Date().toISOString(), scopes };
      patch((s) => ({ ...s, apiKeys: [...s.apiKeys, k], audit: audit(s, "Created API key", name) }));
      return k;
    },
    revokeApiKey: (id) => patch((s) => ({ ...s, apiKeys: s.apiKeys.filter((k) => k.id !== id), audit: audit(s, "Revoked API key", id) })),
    setIntegrationStatus: (id, status) => patch((s) => ({ ...s, integrations: s.integrations.map((i) => (i.id === id ? { ...i, status } : i)), audit: audit(s, status === "connected" ? "Connected integration (demo)" : "Disconnected integration", id) })),
    saveConversation: (c) => patch((s) => ({ ...s, conversations: [c, ...s.conversations.filter((x) => x.id !== c.id)].slice(0, 30) })),
    appendMessage: (convId, m) => patch((s) => ({ ...s, conversations: s.conversations.map((c) => (c.id === convId ? { ...c, messages: [...c.messages, m] } : c)) })),
    addScheduledReport: (r) => patch((s) => ({ ...s, scheduledReports: [...s.scheduledReports, { ...r, id: uid("SR") }] })),
    removeScheduledReport: (id) => patch((s) => ({ ...s, scheduledReports: s.scheduledReports.filter((r) => r.id !== id) })),
    resetDemo: async () => { const snapshot = await api.reset(); dispatch({ type: "loaded", snapshot }); },
    applyLive: (resp) => patch((s) => applyLivePositions(s, resp)),
    saveAlertSettings: async (st) => { const saved = await saveAlertSettings(st); fenceSent.current = JSON.stringify(saved.geofences); setAlertSettings(saved); return saved; },
  }), [patch]);

  const fmt = React.useMemo(() => makeFormatter(state.snapshot?.settings ?? ({ country: "CA", currency: "CAD", distanceUnit: "km", volumeUnit: "L", tempUnit: "C", timezone: "America/Toronto", dateFormat: "YYYY-MM-DD" } as Settings)), [state.snapshot?.settings]);

  return <Ctx.Provider value={{ ...state, mode, alertSettings, liveStatus, fmt, actions }}>{children}</Ctx.Provider>;
}

export function useFleetRaw() {
  const c = React.useContext(Ctx);
  if (!c) throw new Error("useFleet outside FleetProvider");
  return c;
}

/** Use inside pages (snapshot guaranteed loaded by the shell). */
export function useFleet() {
  const c = useFleetRaw();
  if (!c.snapshot) throw new Error("snapshot not loaded");
  return { ...c, s: c.snapshot };
}
