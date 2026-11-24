/**
 * Shared business calculations. Every page (dashboard, vehicle pages, analytics, reports,
 * AI assistant) calls these so the numbers agree everywhere.
 */
import type { DateRange, DateRangePreset, FleetSnapshot, SafetyEvent, Settings, Trip, Vehicle, VehicleStatus } from "@/types";

export const WORKDAY_HOURS = 10;

// ── Date ranges ───────────────────────────────────────────────────────────────
export function makeRange(preset: DateRangePreset, now = new Date()): DateRange {
  const end = new Date(now); end.setHours(23, 59, 59, 999);
  const start = new Date(now); start.setHours(0, 0, 0, 0);
  switch (preset) {
    case "today": break;
    case "7d": start.setDate(start.getDate() - 6); break;
    case "30d": start.setDate(start.getDate() - 29); break;
    case "90d": start.setDate(start.getDate() - 89); break;
    case "month": start.setDate(1); break;
    case "last_month": { start.setMonth(start.getMonth() - 1, 1); end.setDate(0); end.setHours(23, 59, 59, 999); break; }
  }
  return { preset, from: start.toISOString(), to: end.toISOString() };
}

export function previousRange(r: DateRange): DateRange {
  const from = new Date(r.from), to = new Date(r.to);
  const len = to.getTime() - from.getTime() + 1;
  return { preset: r.preset, from: new Date(from.getTime() - len).toISOString(), to: new Date(from.getTime() - 1).toISOString() };
}

export const inRange = (iso: string, r: DateRange) => iso >= r.from && iso <= r.to;
export const rangeDays = (r: DateRange) => Math.max(1, Math.round((new Date(r.to).getTime() - new Date(r.from).getTime()) / 864e5));

// ── Core aggregates ───────────────────────────────────────────────────────────
export const tripsIn = (s: FleetSnapshot, r: DateRange, vehicleId?: string) =>
  s.trips.filter((t) => inRange(t.startTime, r) && (!vehicleId || t.vehicleId === vehicleId));

export const fuelIn = (s: FleetSnapshot, r: DateRange, vehicleId?: string) =>
  s.fuel.filter((f) => inRange(f.date, r) && (!vehicleId || f.vehicleId === vehicleId));

export const maintenanceIn = (s: FleetSnapshot, r: DateRange, vehicleId?: string) =>
  s.maintenance.filter((m) => m.status === "completed" && inRange(m.date, r) && (!vehicleId || m.vehicleId === vehicleId));

export const safetyIn = (s: FleetSnapshot, r: DateRange, f?: { vehicleId?: string; driverId?: string }) =>
  s.safety.filter((e) => inRange(e.time, r) && (!f?.vehicleId || e.vehicleId === f.vehicleId) && (!f?.driverId || e.driverId === f.driverId));

export const sum = (xs: number[]) => xs.reduce((a, b) => a + b, 0);
export const avg = (xs: number[]) => (xs.length ? sum(xs) / xs.length : 0);
export const pctChange = (cur: number, prev: number) => (prev === 0 ? (cur === 0 ? 0 : 100) : ((cur - prev) / prev) * 100);

export function statusCounts(vehicles: Vehicle[]): Record<VehicleStatus, number> {
  const c: Record<VehicleStatus, number> = { moving: 0, idle: 0, stopped: 0, offline: 0 };
  for (const v of vehicles) if (!v.archived) c[v.status]++;
  return c;
}

export function fleetKpis(s: FleetSnapshot, r: DateRange) {
  const prev = previousRange(r);
  const t = tripsIn(s, r), tp = tripsIn(s, prev);
  const distance = sum(t.map((x) => x.distanceKm)), distancePrev = sum(tp.map((x) => x.distanceKm));
  const fuelL = sum(t.map((x) => x.fuelL)), fuelPrev = sum(tp.map((x) => x.fuelL));
  const fuelSpend = sum(fuelIn(s, r).map((f) => f.totalCost)), fuelSpendPrev = sum(fuelIn(s, prev).map((f) => f.totalCost));
  const idleMin = sum(t.map((x) => x.idleMin)), idlePrev = sum(tp.map((x) => x.idleMin));
  const safety = safetyIn(s, r).length, safetyPrev = safetyIn(s, prev).length;
  const active = s.vehicles.filter((v) => !v.archived);
  const maintenanceDue = s.maintenance.filter((m) => m.status !== "completed" && !s.vehicles.find((v) => v.id === m.vehicleId)?.archived).length;
  const overdue = s.maintenance.filter((m) => m.status === "overdue").length;
  return {
    totalVehicles: active.length, status: statusCounts(active),
    distance, distancePrev, fuelL, fuelPrev, fuelSpend, fuelSpendPrev, idleMin, idlePrev,
    trips: t.length, tripsPrev: tp.length, safety, safetyPrev, maintenanceDue, overdue,
    activeDiagnostics: s.diagnostics.filter((d) => d.active).length,
  };
}

// ── Per-vehicle analytics ─────────────────────────────────────────────────────
export function vehicleStats(s: FleetSnapshot, v: Vehicle, r: DateRange) {
  const t = tripsIn(s, r, v.id);
  const distance = sum(t.map((x) => x.distanceKm));
  const driveMin = sum(t.map((x) => x.durationMin));
  const idleMin = sum(t.map((x) => x.idleMin));
  const days = rangeDays(r);
  const workingDays = Math.max(1, Math.round(days * 6 / 7));
  const utilization = Math.min(100, (driveMin / 60 / (workingDays * WORKDAY_HOURS)) * 100);
  const fuelSpend = sum(fuelIn(s, r, v.id).map((f) => f.totalCost));
  const fuelL = sum(fuelIn(s, r, v.id).map((f) => f.litres));
  const fuelLEst = sum(t.map((x) => x.fuelL));
  const maintSpend = sum(maintenanceIn(s, r, v.id).map((m) => m.cost));
  const opCost = fuelSpend + maintSpend;
  const costPerKm = distance > 0 ? opCost / distance : 0;
  const l100 = distance > 0 ? (fuelL / distance) * 100 : 0;
  const idleFuelL = (idleMin / 60) * s.settings.idleFuelLPerHour;
  const idleCost = idleFuelL * s.settings.fuelPricePerL;
  const safety = safetyIn(s, r, { vehicleId: v.id });
  return { trips: t.length, distance, driveMin, idleMin, utilization, fuelSpend, fuelL, fuelLEst, maintSpend, opCost, costPerKm, l100, idleFuelL, idleCost, safetyEvents: safety.length, maxSpeed: Math.max(0, ...t.map((x) => x.maxSpeedKmh)) };
}

export type VehicleStat = ReturnType<typeof vehicleStats> & { vehicle: Vehicle };

export const allVehicleStats = (s: FleetSnapshot, r: DateRange): VehicleStat[] =>
  s.vehicles.filter((v) => !v.archived).map((v) => ({ vehicle: v, ...vehicleStats(s, v, r) }));

export function median(xs: number[]) {
  if (!xs.length) return 0;
  const a = [...xs].sort((x, y) => x - y), m = Math.floor(a.length / 2);
  return a.length % 2 ? a[m]! : (a[m - 1]! + a[m]!) / 2;
}

/** Vehicles flagged for replacement review: old, expensive per km, or many diagnostics. */
export function replacementReview(s: FleetSnapshot, stats: VehicleStat[], now = new Date()) {
  const med = median(stats.filter((x) => x.distance > 50).map((x) => x.costPerKm));
  return stats.filter((x) => {
    const age = now.getFullYear() - x.vehicle.year;
    const diag = s.diagnostics.filter((d) => d.vehicleId === x.vehicle.id).length;
    return age >= 8 || (med > 0 && x.costPerKm > med * 1.5 && x.distance > 200) || diag >= 2 || x.vehicle.odometerKm > 240000;
  }).map((x) => ({
    ...x,
    reasons: [
      now.getFullYear() - x.vehicle.year >= 8 ? `${now.getFullYear() - x.vehicle.year} years old` : null,
      med > 0 && x.costPerKm > med * 1.5 && x.distance > 200 ? `cost/km ${(x.costPerKm / med).toFixed(1)}× fleet median` : null,
      s.diagnostics.filter((d) => d.vehicleId === x.vehicle.id).length >= 2 ? "repeat diagnostic codes" : null,
      x.vehicle.odometerKm > 240000 ? "over 240,000 km" : null,
    ].filter(Boolean) as string[],
  }));
}

// ── Driver safety scoring ─────────────────────────────────────────────────────
/** 100 minus weighted events per 100 km, clamped. Weights are configurable in Settings. */
export function driverSafety(s: FleetSnapshot, driverId: string, r: DateRange) {
  const events = safetyIn(s, r, { driverId });
  const km = sum(s.trips.filter((t) => t.driverId === driverId && inRange(t.startTime, r)).map((t) => t.distanceKm));
  const w = s.settings.safetyWeights;
  const counts = { speeding: 0, harsh_braking: 0, harsh_acceleration: 0, excessive_idling: 0, distracted: 0 } as Record<SafetyEvent["type"], number>;
  for (const e of events) counts[e.type]++;
  const penalty = km > 0 ? ((counts.speeding * w.speeding + counts.harsh_braking * w.harsh_braking + counts.harsh_acceleration * w.harsh_acceleration + counts.excessive_idling * w.excessive_idling + counts.distracted * w.distracted) / km) * 100 : 0;
  const score = Math.round(Math.max(0, Math.min(100, 100 - penalty * 1.8)));
  return { score, km, events: events.length, counts, trips: s.trips.filter((t) => t.driverId === driverId && inRange(t.startTime, r)).length };
}

export const scoreTone = (score: number): "success" | "warning" | "destructive" => (score >= 85 ? "success" : score >= 70 ? "warning" : "destructive");

/** Weekly score trend for a driver over the last n weeks. */
export function driverWeeklyScores(s: FleetSnapshot, driverId: string, weeks = 6, now = new Date()) {
  const out: { week: string; score: number }[] = [];
  for (let i = weeks - 1; i >= 0; i--) {
    const to = new Date(now); to.setDate(to.getDate() - i * 7); to.setHours(23, 59, 59, 999);
    const from = new Date(to); from.setDate(from.getDate() - 6); from.setHours(0, 0, 0, 0);
    const r: DateRange = { preset: "7d", from: from.toISOString(), to: to.toISOString() };
    out.push({ week: `${from.getMonth() + 1}/${from.getDate()}`, score: driverSafety(s, driverId, r).score });
  }
  return out;
}

// ── Time series for charts ────────────────────────────────────────────────────
export function dailySeries(s: FleetSnapshot, r: DateRange) {
  const days = rangeDays(r);
  const from = new Date(r.from);
  const buckets = Array.from({ length: days }, (_, i) => {
    const d = new Date(from); d.setDate(d.getDate() + i);
    return { key: d.toISOString().slice(0, 10), label: `${d.toLocaleDateString("en-CA", { month: "short", day: "numeric" })}`, distance: 0, fuelL: 0, idleMin: 0, trips: 0, active: new Set<string>(), safety: 0 };
  });
  const idx = new Map(buckets.map((b, i) => [b.key, i]));
  for (const t of tripsIn(s, r)) {
    const b = buckets[idx.get(t.startTime.slice(0, 10)) ?? -1]; if (!b) continue;
    b.distance += t.distanceKm; b.fuelL += t.fuelL; b.idleMin += t.idleMin; b.trips++; b.active.add(t.vehicleId);
  }
  for (const e of safetyIn(s, r)) { const b = buckets[idx.get(e.time.slice(0, 10)) ?? -1]; if (b) b.safety++; }
  const total = s.vehicles.filter((v) => !v.archived).length;
  return buckets.map((b) => ({ date: b.label, key: b.key, distance: Math.round(b.distance), fuelL: Math.round(b.fuelL), idleMin: Math.round(b.idleMin), trips: b.trips, active: b.active.size, inactive: Math.max(0, total - b.active.size), safety: b.safety }));
}

export function weeklySeries(s: FleetSnapshot, weeks = 8, now = new Date()) {
  const out: { week: string; distance: number; fuelL: number; fuelCost: number; idleMin: number; safety: number }[] = [];
  for (let i = weeks - 1; i >= 0; i--) {
    const to = new Date(now); to.setDate(to.getDate() - i * 7); to.setHours(23, 59, 59, 999);
    const from = new Date(to); from.setDate(from.getDate() - 6); from.setHours(0, 0, 0, 0);
    const r: DateRange = { preset: "7d", from: from.toISOString(), to: to.toISOString() };
    const t = tripsIn(s, r);
    out.push({ week: `${from.toLocaleDateString("en-CA", { month: "short", day: "numeric" })}`, distance: Math.round(sum(t.map((x) => x.distanceKm))), fuelL: Math.round(sum(t.map((x) => x.fuelL))), fuelCost: Math.round(sum(fuelIn(s, r).map((f) => f.totalCost))), idleMin: sum(t.map((x) => x.idleMin)), safety: safetyIn(s, r).length });
  }
  return out;
}

export function monthlyCosts(s: FleetSnapshot, months = 6, now = new Date()) {
  const out: { month: string; fuel: number; maintenance: number }[] = [];
  for (let i = months - 1; i >= 0; i--) {
    const from = new Date(now.getFullYear(), now.getMonth() - i, 1), to = new Date(now.getFullYear(), now.getMonth() - i + 1, 0, 23, 59, 59, 999);
    const r: DateRange = { preset: "month", from: from.toISOString(), to: to.toISOString() };
    out.push({ month: from.toLocaleDateString("en-CA", { month: "short" }), fuel: Math.round(sum(fuelIn(s, r).map((f) => f.totalCost))), maintenance: Math.round(sum(maintenanceIn(s, r).map((m) => m.cost))) });
  }
  return out;
}

// ── Helpers used by several pages ─────────────────────────────────────────────
export const vehicleById = (s: FleetSnapshot, id?: string) => s.vehicles.find((v) => v.id === id);
export const driverById = (s: FleetSnapshot, id?: string) => s.drivers.find((d) => d.id === id);
export const geofenceById = (s: FleetSnapshot, id?: string) => s.geofences.find((g) => g.id === id);

export const isAfterHours = (iso: string, settings: Settings) => {
  const d = new Date(iso);
  const [sh, sm] = settings.businessHours.start.split(":").map(Number), [eh, em] = settings.businessHours.end.split(":").map(Number);
  const mins = d.getHours() * 60 + d.getMinutes();
  return !settings.businessHours.days.includes(d.getDay()) || mins < sh! * 60 + sm! || mins > eh! * 60 + em!;
};

export const todayDistanceFor = (s: FleetSnapshot, vehicleId: string, now = new Date()) => sum(tripsIn(s, makeRange("today", now), vehicleId).map((t) => t.distanceKm));
export const currentTrip = (s: FleetSnapshot, vehicleId: string): Trip | undefined => s.trips.find((t) => t.vehicleId === vehicleId && t.status === "in_progress");
export const serviceStatus = (v: Vehicle) => (v.nextServiceKm < v.odometerKm ? "overdue" : v.nextServiceKm - v.odometerKm < 1000 ? "due_soon" : "ok");
