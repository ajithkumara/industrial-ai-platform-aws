/**
 * Live tracker data (MP91 via the FleetPilot backend). GET {apiUrl}/mp91 returns the caller's
 * account gold file; this module merges those vehicles into the snapshot. Everything the tracker
 * cannot supply (fuel, engine health, drivers...) stays demo data, and live vehicles are tagged
 * device.source = "obd" so they can be told apart.
 */
import type { FleetSnapshot, Freshness, Trip, Vehicle } from "@/types";
import { authConfig, getToken } from "./auth";

export interface GoldTrip { trip_no: number; start: string; end: string; duration_min: number; distance_km: number; max_speed_kmh: number; avg_moving_speed_kmh?: number; start_lat: number; start_lon: number; end_lat: number; end_lon: number; points: [number, number, number, string][] }
export interface GoldVehicle {
  device_id: string; vehicle_id: string; name: string; plate?: string | null; driver?: string | null;
  current: { fix_time: string; lat: number; lon: number; acc_on: boolean; speed_kmh: number; battery_pct?: number | null } | null;
  device?: { last_contact: string; gps_valid: boolean; battery_pct: number | null; odometer_km: number | null; alarms: string[]; messages: number } | null;
  trips: GoldTrip[];
}
export interface Gold { account_id: string; account_name: string; kind: string; generated_at: string; vehicles: GoldVehicle[] }

export async function fetchGold(): Promise<Gold> {
  const c = authConfig();
  if (!c) throw new Error("not configured");
  const r = await fetch(`${c.apiUrl}/mp91`, { headers: { Authorization: `Bearer ${await getToken()}` } });
  if (r.status === 404) return { account_id: "", account_name: "", kind: "fleet", generated_at: new Date().toISOString(), vehicles: [] };
  if (!r.ok) throw new Error(`API ${r.status}`);
  return (await r.json()) as Gold;
}

// ── Hot path: GET /live (latest *moving* position, written by the edge server only while watched) ──
export interface LivePos { lat: number; lon: number; speed_kmh: number; course: number; acc_on: boolean; fix_time: string; age_s: number }
export interface LiveResp { now: number; vehicles: { vehicle_id: string; device_id: string; live: LivePos | null }[] }

export async function fetchLive(): Promise<LiveResp> {
  const c = authConfig();
  if (!c) throw new Error("not configured");
  const r = await fetch(`${c.apiUrl}/live`, { headers: { Authorization: `Bearer ${await getToken()}` } });
  if (!r.ok) throw new Error(`API ${r.status}`);
  return (await r.json()) as LiveResp;
}

/** Newest hot-path position per vehicle, so the slower 15 s snapshot never moves the dot backwards. */
const overlay = new Map<string, LivePos>();

export function applyLivePositions(s: FleetSnapshot, resp: LiveResp): FleetSnapshot {
  for (const v of resp.vehicles) {
    if (v.live) overlay.set(`LV-${v.vehicle_id}`, v.live); else overlay.delete(`LV-${v.vehicle_id}`);
  }
  return { ...s, vehicles: s.vehicles.map((v) => withOverlay(v)) };
}

function withOverlay(v: Vehicle): Vehicle {
  const o = overlay.get(v.id);
  if (!o || new Date(o.fix_time).getTime() < new Date(v.lastUpdate).getTime()) return v;
  return { ...v, position: { lat: o.lat, lng: o.lon }, speedKmh: o.speed_kmh, heading: o.course, ignitionOn: o.acc_on, status: o.speed_kmh > 3 ? "moving" : "idle", lastUpdate: o.fix_time, lastContact: o.fix_time, freshness: "live" };
}

export const _clearOverlayForTests = () => overlay.clear();

/** Alarms that mean the tracker itself has a problem (not just an event worth noting). */
const DEVICE_FAULTS = ["external_power_disconnected", "alarm_battery_removed"];

/**
 * How current a vehicle's data is. The MP91 reports every 1–2 s while driving but sleeps when parked
 * (one heartbeat roughly every 20 min), so "on time" depends on whether it was last seen moving.
 *   moving/ignition on: live ≤ 2 min, delayed ≤ 10 min, then stale
 *   parked:             live ≤ 35 min, delayed ≤ 3 h,   then stale
 *   any:                offline after 24 h without any message
 *   error:              recent message but no GPS fix, or power-cut / battery-removed alarm
 */
export function freshnessOf(ageMin: number, active: boolean, gpsValid = true, alarms: string[] = []): Freshness {
  if (!Number.isFinite(ageMin) || ageMin > 24 * 60) return "offline";
  if (alarms.some((a) => DEVICE_FAULTS.includes(a))) return "error";
  if (!gpsValid && ageMin <= 35) return "error";
  const [live, delayed] = active ? [2, 10] : [35, 180];
  return ageMin <= live ? "live" : ageMin <= delayed ? "delayed" : "stale";
}

const coord = (lat: number, lng: number) => `${lat.toFixed(4)}, ${lng.toFixed(4)}`;
const liveVid = (g: GoldVehicle) => `LV-${g.vehicle_id}`;

export function mergeLive(s: FleetSnapshot, gold: Gold, now = Date.now()): FleetSnapshot {
  const base = s.vehicles.filter((v) => !v.id.startsWith("LV-"));
  const trips = s.trips.filter((t) => !t.id.startsWith("LT-"));
  const live: Vehicle[] = [];
  const liveTrips: Trip[] = [];
  for (const g of gold.vehicles) {
    const c = g.current;
    const d = g.device ?? null;
    const lastContact = d?.last_contact ?? c?.fix_time;
    const ageMin = lastContact ? (now - new Date(lastContact).getTime()) / 60_000 : Infinity;
    const active = !!c && (c.speed_kmh > 3 || c.acc_on);
    const freshness = freshnessOf(ageMin, active, d?.gps_valid ?? true, d?.alarms ?? []);
    // Never show a stale position as if the vehicle were moving or idling right now.
    const status: Vehicle["status"] = !c || freshness === "stale" || freshness === "offline" ? "offline" : c.speed_kmh > 3 ? "moving" : c.acc_on ? "idle" : "stopped";
    const id = liveVid(g);
    live.push({
      id, name: g.name, registration: g.plate ?? "—", type: "Cargo Van", make: "—", model: "—", year: new Date().getFullYear(), vin: "—",
      fuelType: "Gasoline", tankL: 0, status, odometerKm: d?.odometer_km ?? 0, position: c ? { lat: c.lat, lng: c.lon } : { lat: 43.4354, lng: -79.7085 },
      heading: 0, speedKmh: c?.speed_kmh ?? 0, ignitionOn: c?.acc_on ?? false, lastUpdate: c?.fix_time ?? gold.generated_at,
      lastServiceDate: gold.generated_at, nextServiceKm: 1e9, nextServiceDate: gold.generated_at,
      freshness, lastContact, gpsValid: d?.gps_valid, batteryPct: d?.battery_pct ?? c?.battery_pct ?? null, alarms: d?.alarms ?? [],
      odometerSource: d?.odometer_km ? "device" : "none",
      device: { id: g.device_id, model: "Mictrack MP91", installedOn: gold.generated_at, source: "obd" }, purchasePrice: 0,
    });
    for (const t of g.trips) {
      liveTrips.push({
        id: `LT-${g.vehicle_id}-${t.trip_no}-${t.start}`, vehicleId: id, driverId: "", startTime: t.start, endTime: t.end,
        startLabel: coord(t.start_lat, t.start_lon), endLabel: coord(t.end_lat, t.end_lon),
        startPos: { lat: t.start_lat, lng: t.start_lon }, endPos: { lat: t.end_lat, lng: t.end_lon },
        path: t.points.map((p) => [p[0], p[1]] as [number, number]), speeds: t.points.map((p) => p[2]), times: t.points.map((p) => p[3]), distanceKm: t.distance_km, durationMin: t.duration_min,
        idleMin: 0, maxSpeedKmh: t.max_speed_kmh, avgSpeedKmh: t.avg_moving_speed_kmh ?? 0, fuelL: 0, stops: [], status: "completed",
      });
    }
  }
  const settings = gold.account_name && s.settings.companyName !== gold.account_name ? { ...s.settings, companyName: gold.account_name } : s.settings;
  return { ...s, settings, vehicles: [...base, ...live.map(withOverlay)], trips: [...trips, ...liveTrips] };
}
