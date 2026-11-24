import { describe, expect, it } from "vitest";
import { emptyLiveSnapshot } from "@/services/api";
import { fromServerGeofence, mergeAlerts, rememberRead, toServerGeofence, type ServerAlert } from "@/services/alerts";

const al = (id: string, time: string): ServerAlert => ({ id, vehicle_id: "car1", vehicle_name: "My car", kind: "speeding", category: "speeding", severity: "medium", time, title: "Speed limit exceeded", message: "120 km/h" });

describe("server alerts", () => {
  it("become notifications, newest first, linked to the live vehicle", () => {
    const s = mergeAlerts(emptyLiveSnapshot(), [al("a", "2026-11-24T10:00:00Z"), al("b", "2026-11-24T11:00:00Z")]);
    expect(s.notifications.map((n) => n.id)).toEqual(["AL-b", "AL-a"]);
    expect(s.notifications[0]!.vehicleId).toBe("LV-car1");
    expect(s.notifications[0]!.title).toBe("My car: Speed limit exceeded");
  });
  it("keep read flags across polls and replace, not duplicate", () => {
    localStorage.clear();
    let s = mergeAlerts(emptyLiveSnapshot(), [al("a", "2026-11-24T10:00:00Z")]);
    rememberRead(["AL-a"], true);
    s = mergeAlerts(s, [al("a", "2026-11-24T10:00:00Z")]);
    expect(s.notifications).toHaveLength(1);
    expect(s.notifications[0]!.read).toBe(true);
  });
  it("geofences round-trip; polygons are not sent", () => {
    const g = fromServerGeofence({ id: "h", name: "Home", lat: 43.4, lon: -79.7, radius_m: 150, on_enter: true, on_exit: false });
    expect(toServerGeofence(g)).toEqual({ id: "h", name: "Home", lat: 43.4, lon: -79.7, radius_m: 150, on_enter: true, on_exit: false });
    expect(toServerGeofence({ ...g, shape: "polygon" })).toBeNull();
  });
});
