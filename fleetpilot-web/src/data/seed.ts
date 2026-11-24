/**
 * DEMO DATA generator — NorthStar Mechanical Services, Oakville ON.
 * Deterministic (seeded PRNG) so every screen agrees: all KPIs are derived from
 * these trips, fuel transactions, maintenance records and events via lib/metrics.
 * Nothing here is live GPS or measured fuel; the UI labels it DEMO DATA.
 */
import type {
  Vehicle, Driver, Trip, FuelTransaction, MaintenanceRecord, DiagnosticEvent, SafetyEvent, Geofence, GeofenceEvent,
  Notification, Settings, AppUser, Integration, ApiKey, AuditEntry, FleetSnapshot, LatLng, TripStop, Severity, MaintenanceType,
} from "@/types";
import { PLACES, CUSTOMER_SITES, haversineKm, bearing, simulatedPath, pointInCircle } from "./geo";

export const SNAPSHOT_VERSION = 3;

function mulberry32(seed: number) {
  return () => {
    seed |= 0; seed = (seed + 0x6d2b79f5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

const iso = (d: Date) => d.toISOString();
const addMin = (d: Date, m: number) => new Date(d.getTime() + m * 60000);
const dayStart = (d: Date) => { const x = new Date(d); x.setHours(0, 0, 0, 0); return x; };
const r2 = (n: number) => Math.round(n * 100) / 100;

const DEPOT = PLACES[0]!;

const VEHICLE_SPECS: Omit<Vehicle, "driverId" | "status" | "position" | "heading" | "speedKmh" | "ignitionOn" | "lastUpdate" | "odometerKm" | "lastServiceDate" | "nextServiceKm" | "nextServiceDate" | "device" | "fuelLevelPct" | "batteryV" | "engineTempC">[] = [
  { id: "V-101", name: "Van 101", registration: "CPZL 418", type: "Cargo Van", make: "Ford", model: "Transit 250", year: 2022, vin: "1FTBR1C86NKA10231", fuelType: "Gasoline", tankL: 95, purchasePrice: 58900 },
  { id: "V-102", name: "Van 102", registration: "CRKM 902", type: "Cargo Van", make: "Ford", model: "Transit 250", year: 2021, vin: "1FTBR1C80MKA55018", fuelType: "Gasoline", tankL: 95, purchasePrice: 54200 },
  { id: "V-103", name: "Van 103", registration: "CTAD 377", type: "Cargo Van", make: "Mercedes-Benz", model: "Sprinter 2500", year: 2023, vin: "W1Y4EBHY5PT122904", fuelType: "Diesel", tankL: 92, purchasePrice: 72400 },
  { id: "V-104", name: "Van 104", registration: "BZXT 115", type: "Cargo Van", make: "Chevrolet", model: "Express 2500", year: 2017, vin: "1GCWGAFP4H1221706", fuelType: "Gasoline", tankL: 117, purchasePrice: 41800 },
  { id: "V-105", name: "Van 105", registration: "CSNW 640", type: "Cargo Van", make: "Ford", model: "Transit 350", year: 2022, vin: "1FTBW3X88NKA73311", fuelType: "Gasoline", tankL: 95, purchasePrice: 61500 },
  { id: "V-106", name: "Truck 106", registration: "CVJP 288", type: "Pickup Truck", make: "Ford", model: "F-150 XLT", year: 2023, vin: "1FTFW1E85PFA20934", fuelType: "Gasoline", tankL: 98, purchasePrice: 63900 },
  { id: "V-107", name: "Van 107", registration: "CQHB 731", type: "Cargo Van", make: "Mercedes-Benz", model: "Sprinter 2500", year: 2020, vin: "WD4PF0CD9LP246551", fuelType: "Diesel", tankL: 92, purchasePrice: 66800 },
  { id: "V-108", name: "Van 108", registration: "BWRC 553", type: "Cargo Van", make: "Chevrolet", model: "Express 3500", year: 2016, vin: "1GCZGHFG9G1281440", fuelType: "Gasoline", tankL: 117, purchasePrice: 39900 },
  { id: "V-109", name: "Van 109", registration: "CUEF 196", type: "Cargo Van", make: "Ford", model: "Transit 250", year: 2024, vin: "1FTBR1C83RKA00917", fuelType: "Gasoline", tankL: 95, purchasePrice: 62700 },
  { id: "V-110", name: "Truck 110", registration: "CNLD 804", type: "Pickup Truck", make: "Ford", model: "F-150 XL", year: 2021, vin: "1FTEW1EP2MFA60172", fuelType: "Gasoline", tankL: 87, purchasePrice: 52300 },
  { id: "V-111", name: "Van 111", registration: "CPDS 462", type: "Cargo Van", make: "Ford", model: "Transit 350", year: 2021, vin: "1FTBW3X84MKA81129", fuelType: "Gasoline", tankL: 95, purchasePrice: 57600 },
  { id: "V-112", name: "Van 112", registration: "BYGK 039", type: "Cargo Van", make: "Chevrolet", model: "Express 2500", year: 2018, vin: "1GCWGAFP6J1150827", fuelType: "Gasoline", tankL: 117, purchasePrice: 43500 },
  { id: "V-113", name: "Van 113", registration: "CTMX 215", type: "Cargo Van", make: "Mercedes-Benz", model: "Sprinter 3500", year: 2022, vin: "W1Y5ECHY8NT089463", fuelType: "Diesel", tankL: 92, purchasePrice: 78200 },
  { id: "V-114", name: "Truck 114", registration: "CWBA 677", type: "Service Truck", make: "Ford", model: "F-150 XLT", year: 2022, vin: "1FTFW1E57NFB44810", fuelType: "Gasoline", tankL: 98, purchasePrice: 60100 },
  { id: "V-115", name: "Van 115", registration: "CSQR 320", type: "Cargo Van", make: "Ford", model: "Transit 250", year: 2023, vin: "1FTBR1C88PKA31572", fuelType: "Gasoline", tankL: 95, purchasePrice: 60400 },
];

const DRIVER_NAMES = [
  "John Mercer", "Priya Natarajan", "Marcus Lindqvist", "Daniel Okafor", "Sofia Marchetti",
  "Liam O'Connell", "Amara Diallo", "Tomasz Kowalski", "Hannah Reyes", "Kevin Tran",
  "Fatima Haddad", "Ryan MacLeod", "Elena Petrova", "Jordan Blake", "Samuel Adeyemi",
];

/** Driver behaviour profiles: events per 100 km. John Mercer is the harsh-braking outlier the demo narrative refers to. */
const DRIVER_PROFILE: Record<string, { speeding: number; brake: number; accel: number; idle: number }> = {
  "D-01": { speeding: 1.1, brake: 3.4, accel: 1.2, idle: 1.0 },
  "D-04": { speeding: 1.8, brake: 1.0, accel: 1.6, idle: 0.6 },
  "D-08": { speeding: 0.6, brake: 0.7, accel: 0.5, idle: 2.6 },
  "D-12": { speeding: 1.4, brake: 1.2, accel: 1.1, idle: 0.9 },
};
const DEFAULT_PROFILE = { speeding: 0.5, brake: 0.5, accel: 0.4, idle: 0.5 };

const FUEL_ECONOMY_L100: Record<string, number> = { "Cargo Van": 13.8, "Pickup Truck": 12.9, "Service Truck": 14.6 };
const STATIONS = ["Petro-Canada — Dorval Dr", "Esso — Trafalgar Rd", "Shell — Dundas St W", "Pioneer — Speers Rd", "Costco Gas — Burloak", "Canadian Tire Gas+ — Third Line", "Husky — Derry Rd"];

export function generateSnapshot(now = new Date()): FleetSnapshot {
  const rnd = mulberry32(20261108);
  const pick = <T,>(a: T[]) => a[Math.floor(rnd() * a.length)]!;
  const between = (lo: number, hi: number) => lo + rnd() * (hi - lo);
  let seq = 0;
  const id = (p: string) => `${p}-${(++seq).toString(36).toUpperCase().padStart(5, "0")}`;

  const today = dayStart(now);
  const DAYS = 45;

  // ── Drivers ────────────────────────────────────────────────────────────────
  const drivers: Driver[] = DRIVER_NAMES.map((name, i) => {
    const first = name.split(" ")[0]!.toLowerCase().replace("'", ""), last = name.split(" ")[1]!.toLowerCase();
    return {
      id: `D-${String(i + 1).padStart(2, "0")}`, name, employeeId: `NS-${1040 + i * 7}`,
      email: `${first}.${last}@northstarmech.ca`, phone: `(905) 55${i % 10}-${String(1200 + i * 37).slice(-4)}`,
      vehicleId: `V-${101 + i}`, status: "available", licenseClass: i % 5 === 0 ? "DZ" : "G",
      licenseExpiry: iso(new Date(today.getFullYear() + 1 + (i % 4), (i * 3) % 12, 1 + (i % 27))),
      hireDate: iso(new Date(today.getFullYear() - 1 - (i % 7), (i * 5) % 12, 1 + (i % 27))),
      coaching: [],
    };
  });
  drivers[0]!.coaching.push({ id: id("C"), date: iso(new Date(today.getTime() - 9 * 864e5)), topic: "Following distance and braking", coach: "Fleet Manager", notes: "Reviewed 6 harsh-braking events on QEW. Agreed on 3-second following distance." });
  drivers[7]!.coaching.push({ id: id("C"), date: iso(new Date(today.getTime() - 20 * 864e5)), topic: "Idle reduction", coach: "Fleet Manager", notes: "Engine-off policy at job sites over 5 minutes." });

  // ── Vehicles (status + telemetry fixed by the generator; labelled DEMO) ────
  const STATUS: Vehicle["status"][] = ["moving", "moving", "idle", "moving", "stopped", "moving", "moving", "stopped", "idle", "moving", "moving", "offline", "moving", "stopped", "moving"];
  const vehicles: Vehicle[] = VEHICLE_SPECS.map((s, i) => {
    const ageYears = today.getFullYear() - s.year + 0.6;
    const odo = Math.round(ageYears * between(26000, 34000));
    const lastSvcKm = odo - Math.round(between(800, 6800)); // within the 8,000 km interval; overdue vehicles are set explicitly below
    const svcDaysAgo = Math.round(between(10, 160));
    const status = STATUS[i]!;
    const at = status === "offline" ? addMin(now, -1395) : status === "stopped" ? addMin(now, -between(10, 90)) : addMin(now, -between(0.2, 2.5));
    const place = status === "stopped" ? DEPOT : pick(PLACES.slice(1));
    return {
      ...s, driverId: drivers[i]!.id, status,
      odometerKm: odo,
      fuelLevelPct: s.make === "Chevrolet" && s.year < 2018 ? undefined : Math.round(between(22, 92)),
      position: { lat: +(place.pos.lat + (rnd() - 0.5) * 0.02).toFixed(5), lng: +(place.pos.lng + (rnd() - 0.5) * 0.02).toFixed(5) },
      heading: Math.round(rnd() * 360),
      speedKmh: status === "moving" ? Math.round(between(28, 88)) : 0,
      ignitionOn: status === "moving" || status === "idle",
      batteryV: s.id === "V-108" ? 11.9 : r2(between(12.4, 14.3)),
      engineTempC: status === "offline" ? undefined : Math.round(status === "stopped" ? between(18, 40) : between(86, 97)),
      lastUpdate: iso(at),
      lastServiceDate: iso(new Date(today.getTime() - svcDaysAgo * 864e5)),
      nextServiceKm: lastSvcKm + 8000,
      nextServiceDate: iso(new Date(today.getTime() + (180 - svcDaysAgo) * 864e5)),
      device: { id: `MT-${(70185000 + i * 1313).toString()}`, model: "Mictrack MP91 (OBD-II)", installedOn: iso(new Date(today.getTime() - between(60, 400) * 864e5)), source: "demo" },
    };
  });
  // V-108 and V-104 are overdue for service; V-103 and V-111 approaching
  const v108 = vehicles.find((v) => v.id === "V-108")!; v108.nextServiceKm = v108.odometerKm - 640;
  const v104 = vehicles.find((v) => v.id === "V-104")!; v104.nextServiceKm = v104.odometerKm - 1210;
  const v103 = vehicles.find((v) => v.id === "V-103")!; v103.nextServiceKm = v103.odometerKm + 310;
  const v111 = vehicles.find((v) => v.id === "V-111")!; v111.nextServiceKm = v111.odometerKm + 480;
  for (const v of vehicles) { if (v.status === "moving") drivers.find((d) => d.id === v.driverId)!.status = "driving"; }
  drivers[11]!.status = "off-duty"; // V-112 offline, driver off today

  // ── Geofences ─────────────────────────────────────────────────────────────
  const geofences: Geofence[] = [
    { id: "G-01", name: "NorthStar Depot", category: "depot", shape: "circle", center: DEPOT.pos, radiusM: 220, address: "2275 Speers Rd, Oakville, ON L6L 2X9", vehicleIds: [], alertOnEntry: false, alertOnExit: true },
    ...CUSTOMER_SITES.map((c, i) => ({ id: `G-${String(i + 2).padStart(2, "0")}`, name: c.name, category: "customer" as const, shape: "circle" as const, center: c.pos, radiusM: 180, address: c.address, vehicleIds: [], alertOnEntry: true, alertOnExit: true })),
    { id: "G-08", name: "Wolseley Supply (Mississauga)", category: "warehouse", shape: "circle", center: PLACES[18]!.pos, radiusM: 160, address: "6505 Mississauga Rd, Mississauga, ON", vehicleIds: [], alertOnEntry: true, alertOnExit: false },
    { id: "G-09", name: "Noble Plumbing Supply", category: "warehouse", shape: "circle", center: PLACES[19]!.pos, radiusM: 150, address: "3425 Harvester Rd, Burlington, ON", vehicleIds: [], alertOnEntry: true, alertOnExit: false },
    { id: "G-10", name: "Downtown Toronto — Restricted (tolls/parking)", category: "restricted", shape: "polygon", center: { lat: 43.651, lng: -79.383 }, radiusM: 0,
      polygon: [{ lat: 43.665, lng: -79.405 }, { lat: 43.665, lng: -79.36 }, { lat: 43.64, lng: -79.36 }, { lat: 43.64, lng: -79.405 }], address: "Bounded by Bloor, Jarvis, Lake Shore and Bathurst, Toronto", vehicleIds: [], alertOnEntry: true, alertOnExit: false },
  ];

  // ── Trips, safety events, geofence events ─────────────────────────────────
  const trips: Trip[] = [];
  const safety: SafetyEvent[] = [];
  const geofenceEvents: GeofenceEvent[] = [];
  const destinations = [...PLACES.slice(1), ...CUSTOMER_SITES.map((c) => ({ name: c.name, pos: c.pos, kind: "customer" as const }))];
  const sevFor = (over: number): Severity => (over > 30 ? "critical" : over > 20 ? "high" : over > 10 ? "medium" : "low");

  for (const v of vehicles) {
    const driver = drivers.find((d) => d.id === v.driverId)!;
    const profile = DRIVER_PROFILE[driver.id] ?? DEFAULT_PROFILE;
    const econ = FUEL_ECONOMY_L100[v.type]! * (v.year < 2019 ? 1.12 : 1);
    const heavyIdler = v.id === "V-104" || v.id === "V-108";
    for (let d = DAYS; d >= 0; d--) {
      const day = new Date(today.getTime() - d * 864e5);
      const dow = day.getDay();
      if (dow === 0) continue;                                  // Sundays off
      if (dow === 6 && rnd() < 0.55) continue;                  // some Saturdays
      if (v.id === "V-112" && d < 2) continue;                  // offline vehicle: no trips last 2 days
      if (d === 0 && (v.status === "stopped" || v.status === "offline") && rnd() < 0.5) continue;
      const nTrips = d === 0 ? (v.status === "stopped" ? 1 : 2) : 2 + Math.floor(rnd() * 3);
      let cursor = addMin(day, 7 * 60 + Math.round(between(0, 75)));
      let from: { name: string; pos: LatLng } = DEPOT;
      for (let t = 0; t < nTrips; t++) {
        if (d === 0 && cursor > now) break;
        const last = t === nTrips - 1;
        const to = last && rnd() < 0.8 ? DEPOT : pick(destinations);
        if (to.name === from.name) continue;
        const straight = haversineKm(from.pos, to.pos);
        const distanceKm = r2(straight * between(1.22, 1.38));
        const avg = between(30, 52);
        const driveMin = Math.max(6, Math.round((distanceKm / avg) * 60));
        const idleMin = Math.round(between(2, heavyIdler ? 28 : 11));
        const durationMin = driveMin + idleMin;
        const start = cursor, end = addMin(start, durationMin);
        const inProgress = d === 0 && end > now && v.status === "moving";
        const path = simulatedPath(from.pos, to.pos, rnd);
        const maxSpeed = Math.round(Math.min(118, avg * between(1.5, 2.1)));
        const stops: TripStop[] = rnd() < 0.3 ? [{ label: pick(PLACES).name, position: path[Math.floor(path.length / 2)] ? { lat: path[Math.floor(path.length / 2)]![0], lng: path[Math.floor(path.length / 2)]![1] } : from.pos, arrival: iso(addMin(start, Math.round(driveMin / 2))), durationMin: Math.round(between(4, 18)) }] : [];
        const trip: Trip = {
          id: id("T"), vehicleId: v.id, driverId: driver.id,
          startTime: iso(start), endTime: iso(inProgress ? now : end), startLabel: from.name, endLabel: to.name,
          startPos: from.pos, endPos: to.pos, path, distanceKm, durationMin: inProgress ? Math.round((now.getTime() - start.getTime()) / 60000) : durationMin,
          idleMin, maxSpeedKmh: maxSpeed, avgSpeedKmh: r2(distanceKm / (driveMin / 60)),
          fuelL: r2((distanceKm * econ) / 100 + (idleMin / 60) * 0.8), stops, status: inProgress ? "in_progress" : "completed",
        };
        trips.push(trip);

        // safety events along the trip
        const per100 = distanceKm / 100;
        const emit = (type: SafetyEvent["type"], rate: number, sevFn: () => { severity: Severity; value?: number }) => {
          let n = Math.floor(rate * per100); if (rnd() < rate * per100 - n) n++;
          for (let k = 0; k < n; k++) {
            const idx = 1 + Math.floor(rnd() * (path.length - 2)), p = path[idx]!;
            const { severity, value } = sevFn();
            safety.push({ id: id("S"), type, vehicleId: v.id, driverId: driver.id, tripId: trip.id, time: iso(addMin(start, Math.round(durationMin * (idx / path.length)))), position: { lat: p[0], lng: p[1] }, locationLabel: `Near ${to.name.split(" — ")[0]}`, severity, value, acknowledged: d > 7 || rnd() < 0.5 });
          }
        };
        emit("speeding", profile.speeding, () => { const over = Math.round(between(8, 34)); return { severity: sevFor(over), value: over }; });
        emit("harsh_braking", profile.brake, () => ({ severity: rnd() < 0.2 ? "high" : "medium", value: r2(between(0.35, 0.62)) }));
        emit("harsh_acceleration", profile.accel, () => ({ severity: "low", value: r2(between(0.3, 0.45)) }));
        if (idleMin >= 15) safety.push({ id: id("S"), type: "excessive_idling", vehicleId: v.id, driverId: driver.id, tripId: trip.id, time: iso(addMin(end, -idleMin)), position: to.pos, locationLabel: to.name, severity: idleMin > 22 ? "medium" : "low", value: idleMin, acknowledged: d > 7 });

        // geofence events at trip ends
        for (const g of geofences) {
          if (g.shape !== "circle") continue;
          if (pointInCircle(to.pos, g.center, g.radiusM + 60)) geofenceEvents.push({ id: id("GE"), geofenceId: g.id, vehicleId: v.id, type: "enter", time: trip.endTime });
          if (pointInCircle(from.pos, g.center, g.radiusM + 60)) geofenceEvents.push({ id: id("GE"), geofenceId: g.id, vehicleId: v.id, type: "exit", time: trip.startTime });
        }
        from = to;
        cursor = addMin(end, Math.round(between(25, 110)));
        if (inProgress) break;
      }
    }
  }
  trips.sort((a, b) => a.startTime.localeCompare(b.startTime));

  // ── Fuel transactions: fill up when ~75% of tank consumed (estimated) ─────
  const fuel: FuelTransaction[] = [];
  for (const v of vehicles) {
    const vt = trips.filter((t) => t.vehicleId === v.id);
    let used = v.tankL * between(0.3, 0.6);
    let odo = v.odometerKm - vt.reduce((s, t) => s + t.distanceKm, 0);
    for (const t of vt) {
      used += t.fuelL; odo += t.distanceKm;
      if (used >= v.tankL * 0.72) {
        const litres = r2(used - between(4, 12));
        const unitPrice = r2(between(1.47, 1.68) + (v.fuelType === "Diesel" ? 0.14 : 0));
        fuel.push({ id: id("F"), date: t.endTime, vehicleId: v.id, driverId: t.driverId, station: pick(STATIONS), litres, unitPrice, totalCost: r2(litres * unitPrice), odometerKm: Math.round(odo), source: "fuel-card" });
        used -= litres;
      }
    }
  }
  fuel.sort((a, b) => b.date.localeCompare(a.date));

  // ── Maintenance ───────────────────────────────────────────────────────────
  const PROVIDERS = ["Oakville Ford Service", "Mister Transmission — Burlington", "Mercedes-Benz Oakville", "Kal Tire — Speers Rd", "Midas — Dundas St", "In-house (NorthStar shop)"];
  const maintenance: MaintenanceRecord[] = [];
  const MT: { type: MaintenanceType; cost: [number, number]; every: number }[] = [
    { type: "Oil Change", cost: [95, 160], every: 8000 }, { type: "Tire Rotation", cost: [60, 95], every: 12000 },
    { type: "Brake Service", cost: [420, 980], every: 45000 }, { type: "Safety Inspection", cost: [120, 180], every: 30000 },
    { type: "Coolant Flush", cost: [160, 240], every: 60000 }, { type: "Tire Replacement", cost: [900, 1650], every: 70000 },
  ];
  for (const v of vehicles) {
    const n = 3 + Math.floor(rnd() * 3);
    for (let k = 0; k < n; k++) {
      const daysAgo = Math.round(between(5, 330));
      const m = pick(MT);
      const kmAgo = Math.round(daysAgo * 95);
      maintenance.push({ id: id("M"), vehicleId: v.id, type: m.type, date: iso(new Date(today.getTime() - daysAgo * 864e5)), odometerKm: v.odometerKm - kmAgo, provider: pick(PROVIDERS), cost: Math.round(between(...m.cost)), nextKm: v.odometerKm - kmAgo + m.every, notes: k === 0 ? "Completed on schedule." : undefined, status: "completed", invoiceName: rnd() < 0.6 ? `INV-${Math.floor(between(20000, 29999))}.pdf` : undefined });
    }
    // the next service as a scheduled/overdue record
    const overdue = v.nextServiceKm < v.odometerKm;
    maintenance.push({ id: id("M"), vehicleId: v.id, type: "Oil Change", date: v.nextServiceDate, odometerKm: v.nextServiceKm, provider: "Oakville Ford Service", cost: 0, nextKm: v.nextServiceKm, status: overdue ? "overdue" : "scheduled", notes: overdue ? `Overdue by ${v.odometerKm - v.nextServiceKm} km` : "Scheduled by mileage interval (8,000 km)" });
  }
  maintenance.push({ id: id("M"), vehicleId: "V-108", type: "Battery Replacement", date: iso(new Date(today.getTime() + 2 * 864e5)), odometerKm: v108.odometerKm, provider: "In-house (NorthStar shop)", cost: 0, status: "scheduled", notes: "Battery voltage 11.9 V at rest. Replace before winter." });
  maintenance.sort((a, b) => b.date.localeCompare(a.date));

  // ── Diagnostics (simulated OBD codes) ─────────────────────────────────────
  const diagnostics: DiagnosticEvent[] = [
    { id: id("DG"), vehicleId: "V-104", code: "P0420", description: "Catalyst system efficiency below threshold (Bank 1)", severity: "medium", date: iso(new Date(today.getTime() - 6 * 864e5)), active: true, source: "obd" },
    { id: id("DG"), vehicleId: "V-108", code: "P0562", description: "System voltage low", severity: "high", date: iso(new Date(today.getTime() - 1 * 864e5)), active: true, source: "obd" },
    { id: id("DG"), vehicleId: "V-107", code: "P0171", description: "System too lean (Bank 1)", severity: "low", date: iso(new Date(today.getTime() - 3 * 864e5)), active: true, source: "obd" },
    { id: id("DG"), vehicleId: "V-102", code: "P0300", description: "Random/multiple cylinder misfire detected", severity: "high", date: iso(new Date(today.getTime() - 19 * 864e5)), active: false, source: "obd" },
    { id: id("DG"), vehicleId: "V-113", code: "P2463", description: "Diesel particulate filter restriction — soot accumulation", severity: "medium", date: iso(new Date(today.getTime() - 11 * 864e5)), active: false, source: "obd" },
  ];

  // ── Notifications (last 7 days) ───────────────────────────────────────────
  const notifications: Notification[] = [];
  const vName = (vid: string) => vehicles.find((v) => v.id === vid)!.name;
  notifications.push({ id: id("N"), category: "vehicle_offline", severity: "high", title: `${vName("V-112")} offline`, message: "No telemetry for 23 hours. Last seen at NorthStar Depot.", time: vehicles.find((v) => v.id === "V-112")!.lastUpdate, vehicleId: "V-112", read: false });
  notifications.push({ id: id("N"), category: "low_battery", severity: "medium", title: `${vName("V-108")} low battery voltage`, message: "11.9 V at rest. Battery replacement scheduled.", time: iso(addMin(now, -190)), vehicleId: "V-108", read: false });
  for (const d of diagnostics.filter((x) => x.active)) notifications.push({ id: id("N"), category: "diagnostic", severity: d.severity, title: `${vName(d.vehicleId)} diagnostic code ${d.code}`, message: d.description, time: d.date, vehicleId: d.vehicleId, read: rnd() < 0.5 });
  for (const m of maintenance.filter((x) => x.status === "overdue")) notifications.push({ id: id("N"), category: "maintenance_due", severity: "high", title: `${vName(m.vehicleId)} service overdue`, message: m.notes ?? "", time: iso(addMin(now, -between(300, 2800))), vehicleId: m.vehicleId, read: false });
  const weekAgo = now.getTime() - 7 * 864e5;
  for (const s of safety.filter((x) => new Date(x.time).getTime() > weekAgo && (x.severity === "high" || x.severity === "critical" || x.type === "excessive_idling"))) {
    const cat = s.type === "speeding" ? "speeding" : s.type === "excessive_idling" ? "excessive_idling" : "safety_incident";
    const dn = drivers.find((d) => d.id === s.driverId)!.name;
    notifications.push({ id: id("N"), category: cat, severity: s.severity, title: s.type === "speeding" ? `${vName(s.vehicleId)} speeding +${s.value} km/h` : s.type === "excessive_idling" ? `${vName(s.vehicleId)} idling ${s.value} min` : `${vName(s.vehicleId)} harsh braking`, message: `${dn} · ${s.locationLabel}`, time: s.time, vehicleId: s.vehicleId, driverId: s.driverId, read: rnd() < 0.6 });
  }
  for (const ge of geofenceEvents.filter((x) => new Date(x.time).getTime() > now.getTime() - 2 * 864e5).slice(-14)) {
    const g = geofences.find((x) => x.id === ge.geofenceId)!;
    if (g.category === "depot") continue;
    notifications.push({ id: id("N"), category: "geofence", severity: "info", title: `${vName(ge.vehicleId)} ${ge.type === "enter" ? "arrived at" : "left"} ${g.name}`, message: g.address, time: ge.time, vehicleId: ge.vehicleId, read: true });
  }
  notifications.push({ id: id("N"), category: "unauthorized_movement", severity: "critical", title: `${vName("V-110")} moved after hours`, message: "Ignition on at 11:42 PM, 4.2 km from depot. Outside business hours (7:00–18:00).", time: iso(new Date(today.getTime() - 3 * 864e5 + 23.7 * 3600e3)), vehicleId: "V-110", driverId: "D-10", read: false });
  notifications.sort((a, b) => b.time.localeCompare(a.time));

  // ── Settings, users, integrations, admin ─────────────────────────────────
  const prefs = Object.fromEntries((["vehicle_offline", "unauthorized_movement", "geofence", "maintenance_due", "diagnostic", "excessive_idling", "speeding", "safety_incident", "low_battery", "system"] as const).map((c) => [c, { email: true, push: c !== "geofence", sms: c === "unauthorized_movement" || c === "vehicle_offline" }])) as Settings["notificationPrefs"];
  const settings: Settings = {
    companyName: "NorthStar Mechanical Services", legalName: "NorthStar Mechanical Services Inc.", country: "CA", address: "2275 Speers Rd, Oakville, ON L6L 2X9",
    currency: "CAD", distanceUnit: "km", volumeUnit: "L", tempUnit: "C", timezone: "America/Toronto", dateFormat: "YYYY-MM-DD",
    businessHours: { start: "07:00", end: "18:00", days: [1, 2, 3, 4, 5, 6] }, speedLimitKmh: 100, idleThresholdMin: 10, fuelPricePerL: 1.58, idleFuelLPerHour: 0.8,
    dataRetentionMonths: 13, safetyWeights: { speeding: 4, harsh_braking: 3, harsh_acceleration: 2, excessive_idling: 1, distracted: 5 }, notificationPrefs: prefs,
  };
  const users: AppUser[] = [
    { id: "U-1", name: "Ajith Kumara", email: "owner@northstarmech.ca", role: "Company Owner", lastActive: iso(now), active: true },
    { id: "U-2", name: "Dana Whitfield", email: "dana.whitfield@northstarmech.ca", role: "Fleet Manager", lastActive: iso(addMin(now, -48)), active: true },
    { id: "U-3", name: "Carlos Mendes", email: "dispatch@northstarmech.ca", role: "Dispatcher", lastActive: iso(addMin(now, -12)), active: true },
    { id: "U-4", name: "Mike Sorensen", email: "shop@northstarmech.ca", role: "Maintenance Manager", lastActive: iso(addMin(now, -1500)), active: true },
    { id: "U-5", name: "John Mercer", email: "john.mercer@northstarmech.ca", role: "Driver", lastActive: iso(addMin(now, -30)), active: true },
  ];
  const integrations: Integration[] = [
    { id: "quickbooks", name: "QuickBooks Online", category: "Accounting", description: "Sync fuel and maintenance expenses to QuickBooks as bills and vehicle-level cost centres.", status: "available", demo: true },
    { id: "jobber", name: "Jobber", category: "Field Service", description: "Import today's jobs as geofences and match trips to work orders.", status: "available", demo: true },
    { id: "servicetitan", name: "ServiceTitan", category: "Field Service", description: "Technician dispatch, job locations and arrival confirmation from vehicle telemetry.", status: "coming_soon", demo: true },
    { id: "wex", name: "WEX Fleet Cards", category: "Fuel Cards", description: "Import fuel-card transactions nightly and reconcile against odometer readings.", status: "available", demo: true },
    { id: "petrocan", name: "Petro-Canada SuperPass", category: "Fuel Cards", description: "Canadian fuel-card transaction import.", status: "available", demo: true },
    { id: "mictrack", name: "Mictrack MP91 / MT-series", category: "GPS Hardware", description: "OBD-II and hardwired trackers (H02 protocol). Supported by the FleetPilot ingestion service.", status: "connected", demo: false },
    { id: "teltonika", name: "Teltonika FMB-series", category: "GPS Hardware", description: "Codec 8 trackers with CAN-bus data.", status: "coming_soon", demo: true },
    { id: "geotab", name: "Geotab GO devices", category: "GPS Hardware", description: "Import vehicle data from an existing Geotab database via the MyGeotab API.", status: "coming_soon", demo: true },
    { id: "lytx", name: "AI dashcam (Lytx / Netradyne)", category: "AI Dashcams", description: "Event video for harsh braking, speeding and distraction. Video stays with the camera provider.", status: "coming_soon", demo: true },
    { id: "fordpro", name: "Ford Pro Telematics", category: "OEM Data", description: "Factory telematics for Ford Transit and F-150: odometer, fuel level, oil life, DTCs.", status: "available", demo: true },
    { id: "gmobd", name: "GM OnStar Vehicle Insights", category: "OEM Data", description: "Chevrolet Express factory data.", status: "coming_soon", demo: true },
    { id: "eld", name: "ELD provider (ISAAC / BigRoad)", category: "Compliance", description: "Hours-of-service for fleets that need ELD compliance. FleetPilot does not provide an ELD.", status: "coming_soon", demo: true },
    { id: "chargepoint", name: "ChargePoint", category: "EV Charging", description: "Charging sessions and energy cost for EV vans.", status: "coming_soon", demo: true },
  ];
  const apiKeys: ApiKey[] = [{ id: "K-1", name: "Power BI reporting", prefix: "fp_live_7Qx3", created: iso(new Date(today.getTime() - 40 * 864e5)), lastUsed: iso(addMin(now, -600)), scopes: ["vehicles:read", "trips:read", "reports:read"] }];
  const audit: AuditEntry[] = [
    { id: id("A"), time: iso(addMin(now, -35)), actor: "Dana Whitfield", action: "Acknowledged safety event", target: "Van 101 · harsh braking" },
    { id: id("A"), time: iso(addMin(now, -400)), actor: "Carlos Mendes", action: "Created geofence", target: "Mapleview Centre" },
    { id: id("A"), time: iso(addMin(now, -1500)), actor: "Mike Sorensen", action: "Scheduled maintenance", target: "Van 108 · Battery Replacement" },
    { id: id("A"), time: iso(addMin(now, -2900)), actor: "Ajith Kumara", action: "Changed setting", target: "Speed limit threshold 95 → 100 km/h" },
    { id: id("A"), time: iso(addMin(now, -4300)), actor: "Ajith Kumara", action: "Invited user", target: "shop@northstarmech.ca (Maintenance Manager)" },
  ];

  return {
    version: SNAPSHOT_VERSION, generatedAt: iso(now), vehicles, drivers, trips, fuel, maintenance, diagnostics, safety, geofences, geofenceEvents,
    notifications, settings, users, integrations, apiKeys, audit, conversations: [], scheduledReports: [
      { id: "SR-1", reportId: "fuel", cadence: "weekly", recipients: "owner@northstarmech.ca", format: "pdf", nextRun: iso(new Date(today.getTime() + ((8 - today.getDay()) % 7 || 7) * 864e5)) },
    ],
  };
}

export { bearing };
