import { describe, expect, it } from "vitest";
import { generateSnapshot } from "@/data/seed";
import { applyLivePositions, freshnessOf, mergeLive, _clearOverlayForTests, type Gold, type LiveResp } from "@/services/live";
import { emptyLiveSnapshot } from "@/services/api";

const NOW = Date.parse("2026-11-10T15:00:00Z");
const gold = (fix: string, speed: number, acc: boolean): Gold => ({
  account_id: "a1", account_name: "Test", kind: "personal", generated_at: "2026-11-10T15:00:00Z",
  vehicles: [{
    device_id: "7018532019", vehicle_id: "v1", name: "My Car", plate: "ABCD 123", driver: null,
    current: { fix_time: fix, lat: 43.45, lon: -79.7, acc_on: acc, speed_kmh: speed, battery_pct: 100 },
    trips: [{ trip_no: 1, start: "2026-11-10T13:00:00Z", end: "2026-11-10T13:20:00Z", duration_min: 20, distance_km: 12.5, max_speed_kmh: 88,
      start_lat: 43.4, start_lon: -79.7, end_lat: 43.5, end_lon: -79.8, points: [[43.4, -79.7, 10, "2026-11-10T13:00:00Z"], [43.5, -79.8, 60, "2026-11-10T13:20:00Z"]] }],
  }],
});

describe("mergeLive", () => {
  const s = generateSnapshot();
  it("adds the live vehicle and trip, keeps demo data", () => {
    const m = mergeLive(s, gold("2026-11-10T14:59:00Z", 55, true), NOW);
    const v = m.vehicles.find((x) => x.id === "LV-v1")!;
    expect(v.status).toBe("moving");
    expect(v.device.source).toBe("obd");
    expect(m.vehicles.length).toBe(s.vehicles.length + 1);
    expect(m.trips.filter((t) => t.id.startsWith("LT-"))).toHaveLength(1);
    expect(m.trips.find((t) => t.id.startsWith("LT-"))!.path).toHaveLength(2);
  });
  it("is idempotent across polls", () => {
    const once = mergeLive(s, gold("2026-11-10T14:59:00Z", 0, false), NOW);
    const twice = mergeLive(once, gold("2026-11-10T14:59:00Z", 0, false), NOW);
    expect(twice.vehicles.length).toBe(once.vehicles.length);
    expect(twice.trips.length).toBe(once.trips.length);
  });
  it("marks stale or parked vehicles correctly", () => {
    expect(mergeLive(s, gold("2026-11-10T14:59:00Z", 0, false), NOW).vehicles.find((x) => x.id === "LV-v1")!.status).toBe("stopped");
    expect(mergeLive(s, gold("2026-11-10T14:59:00Z", 0, true), NOW).vehicles.find((x) => x.id === "LV-v1")!.status).toBe("idle");
    expect(mergeLive(s, gold("2026-11-10T09:00:00Z", 0, false), NOW).vehicles.find((x) => x.id === "LV-v1")!.status).toBe("offline");
  });
});

describe("hot path overlay", () => {
  const s = generateSnapshot();
  const resp = (fix: string, speed: number | null): LiveResp => ({
    now: 0, vehicles: [{ vehicle_id: "v1", device_id: "7018532019", live: speed === null ? null : { lat: 43.5, lon: -79.8, speed_kmh: speed, course: 123, acc_on: true, fix_time: fix, age_s: 1 } }],
  });
  it("moves the live vehicle and survives the slower 15 s snapshot", () => {
    _clearOverlayForTests();
    const base = mergeLive(s, gold("2026-11-10T14:59:00Z", 0, false), NOW);
    const hot = applyLivePositions(base, resp("2026-11-10T14:59:30Z", 55));
    const v = hot.vehicles.find((x) => x.id === "LV-v1")!;
    expect(v.position).toEqual({ lat: 43.5, lng: -79.8 });
    expect(v.status).toBe("moving");
    expect(v.heading).toBe(123);
    // the next snapshot (older fix) must not drag the dot backwards
    const again = mergeLive(hot, gold("2026-11-10T14:59:10Z", 0, false), NOW);
    expect(again.vehicles.find((x) => x.id === "LV-v1")!.position).toEqual({ lat: 43.5, lng: -79.8 });
  });
  it("falls back to the snapshot when the car stops being live", () => {
    _clearOverlayForTests();
    const base = mergeLive(s, gold("2026-11-10T14:59:00Z", 0, false), NOW);
    applyLivePositions(base, resp("2026-11-10T14:59:30Z", 55));
    applyLivePositions(base, resp("", null));
    const again = mergeLive(base, gold("2026-11-10T14:59:50Z", 0, false), NOW);
    expect(again.vehicles.find((x) => x.id === "LV-v1")!.position).toEqual({ lat: 43.45, lng: -79.7 });
  });
});

describe("freshness", () => {
  it("parked trackers sleep ~20 min, so 25 min is still live when parked but not when driving", () => {
    expect(freshnessOf(25, false)).toBe("live");
    expect(freshnessOf(25, true)).toBe("stale");
    expect(freshnessOf(5, true)).toBe("delayed");
    expect(freshnessOf(1, true)).toBe("live");
    expect(freshnessOf(240, false)).toBe("stale");
    expect(freshnessOf(25 * 60, false)).toBe("offline");
    expect(freshnessOf(Infinity, false)).toBe("offline");
  });
  it("device faults win over age", () => {
    expect(freshnessOf(1, true, false)).toBe("error");
    expect(freshnessOf(1, false, true, ["external_power_disconnected"])).toBe("error");
    expect(freshnessOf(1, false, true, ["alarm_shake"])).toBe("live");
  });
  it("a stale vehicle never shows as moving", () => {
    const now = Date.parse("2026-11-10T15:00:00Z");
    const g = gold("2026-11-10T14:40:00Z", 60, true);   // last seen driving 20 min ago
    const v = mergeLive(emptyLiveSnapshot(), g, now).vehicles[0]!;
    expect(v.freshness).toBe("stale");
    expect(v.status).toBe("offline");
  });
  it("uses the device block for last contact, battery, odometer and alarms", () => {
    const g = gold("2026-11-10T14:00:00Z", 0, false);
    g.vehicles[0]!.device = { last_contact: "2026-11-10T14:59:00Z", gps_valid: true, battery_pct: 80, odometer_km: 12345.6, alarms: ["vehicle_battery_low"], messages: 10 };
    const v = mergeLive(emptyLiveSnapshot(), g, NOW).vehicles[0]!;
    expect(v.freshness).toBe("live");
    expect(v.lastContact).toBe("2026-11-10T14:59:00Z");
    expect(v.batteryPct).toBe(80);
    expect(v.odometerKm).toBe(12345.6);
    expect(v.alarms).toEqual(["vehicle_battery_low"]);
  });
});

describe("live snapshot", () => {
  it("contains no generated demo records", () => {
    const s = emptyLiveSnapshot();
    for (const k of ["vehicles", "drivers", "trips", "fuel", "maintenance", "diagnostics", "safety", "geofences", "notifications", "users", "audit"] as const) expect(s[k]).toHaveLength(0);
  });
});
