/**
 * Server-side alerts (Phase 2). The processor Lambda evaluates the rules on every data pass and stores
 * alerts per account; the app lists them (GET /alerts) and edits the rules (GET/PUT /alert-settings).
 * Geofences are part of the alert settings, so the server — not this browser — is their source of truth.
 */
import type { FleetSnapshot, Geofence, Notification, NotificationCategory, Severity } from "@/types";
import { authConfig, getToken } from "./auth";

export interface ServerGeofence { id: string; name: string; lat: number; lon: number; radius_m: number; on_enter: boolean; on_exit: boolean }
export interface AlertSettings {
  enabled: boolean;
  offline_minutes: number;
  speed_limit_kmh: number;
  low_battery_pct: number;
  after_hours: { enabled: boolean; start: string; end: string; days: number[]; tz: string };
  geofences: ServerGeofence[];
  email: { enabled: boolean; to: string[] };
}
export interface ServerAlert {
  id: string; vehicle_id: string; vehicle_name?: string; kind: string; category: NotificationCategory;
  severity: Severity; time: string; title: string; message: string;
}

async function call<T>(method: "GET" | "PUT", path: string, body?: unknown): Promise<T> {
  const c = authConfig();
  if (!c) throw new Error("not configured");
  const r = await fetch(`${c.apiUrl}${path}`, {
    method, headers: { Authorization: `Bearer ${await getToken()}`, ...(body ? { "Content-Type": "application/json" } : {}) },
    body: body ? JSON.stringify(body) : undefined,
  });
  const j = (await r.json().catch(() => ({}))) as T & { error?: string };
  if (!r.ok) throw new Error(j.error ?? `API ${r.status}`);
  return j;
}

export const fetchAlerts = () => call<{ alerts: ServerAlert[] }>("GET", "/alerts").then((r) => r.alerts);
export const fetchAlertSettings = () => call<AlertSettings>("GET", "/alert-settings");
export const saveAlertSettings = (s: AlertSettings) => call<AlertSettings>("PUT", "/alert-settings", s);

/** Server alerts → notifications, keeping each one's read flag across polls (stored per browser). */
const READ_KEY = "fleetpilot.alerts.read";
const readSet = (): Set<string> => { try { return new Set(JSON.parse(localStorage.getItem(READ_KEY) ?? "[]") as string[]); } catch { return new Set(); } };
export function rememberRead(ids: string[], read: boolean) {
  const s = readSet();
  ids.forEach((id) => (read ? s.add(id) : s.delete(id)));
  try { localStorage.setItem(READ_KEY, JSON.stringify([...s].slice(-500))); } catch { /* ignore */ }
}

export function mergeAlerts(s: FleetSnapshot, alerts: ServerAlert[]): FleetSnapshot {
  const read = readSet();
  const own = s.notifications.filter((n) => !n.id.startsWith("AL-"));
  const server: Notification[] = alerts.map((a) => ({
    id: `AL-${a.id}`, category: a.category, severity: a.severity, title: a.vehicle_name ? `${a.vehicle_name}: ${a.title}` : a.title,
    message: a.message, time: a.time, vehicleId: `LV-${a.vehicle_id}`, read: read.has(`AL-${a.id}`),
  }));
  return { ...s, notifications: [...server, ...own].sort((a, b) => b.time.localeCompare(a.time)) };
}

export const toServerGeofence = (g: Geofence): ServerGeofence | null =>
  g.shape === "circle" ? { id: g.id, name: g.name, lat: g.center.lat, lon: g.center.lng, radius_m: Math.max(50, Math.round(g.radiusM)), on_enter: g.alertOnEntry, on_exit: g.alertOnExit } : null;

export const fromServerGeofence = (g: ServerGeofence): Geofence => ({
  id: g.id, name: g.name, category: "customer", shape: "circle", center: { lat: g.lat, lng: g.lon }, radiusM: g.radius_m,
  address: "", vehicleIds: [], alertOnEntry: g.on_enter, alertOnExit: g.on_exit,
});
