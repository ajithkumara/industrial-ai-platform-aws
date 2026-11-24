/**
 * Route smoke tests: every module mounts with the demo dataset, renders real
 * numbers, and the dataset itself is internally consistent.
 */
import { describe, it, expect, beforeAll, vi } from "vitest";
import * as React from "react";
import { render, screen, waitFor, fireEvent, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { TooltipProvider } from "@/components/ui/tooltip";
import { ToastProvider } from "@/components/ui/toast";
import { FleetProvider } from "@/store/FleetStore";
import App from "@/App";
import { generateSnapshot } from "@/data/seed";
import { fleetKpis, allVehicleStats, makeRange, sum, driverSafety } from "@/lib/metrics";
import { makeFormatter } from "@/lib/format";
import { answer } from "@/lib/assistant";

// Leaflet's SVG renderer needs real layout; stub react-leaflet so map pages still mount their panels.
vi.mock("react-leaflet", () => {
  const Box = ({ children }: { children?: React.ReactNode }) => <div data-testid="map">{children}</div>;
  const Nil = () => null;
  return { MapContainer: Box, TileLayer: Nil, Marker: Box, Popup: Nil, Circle: Nil, Polygon: Nil, Polyline: Nil, CircleMarker: Nil, Tooltip: Nil, useMap: () => ({ flyTo() {}, fitBounds() {}, invalidateSize() {}, getZoom: () => 12, setView() {} }) };
});

beforeAll(() => {
  // jsdom lacks layout APIs Leaflet/Recharts touch
  Object.defineProperty(HTMLElement.prototype, "clientWidth", { configurable: true, get: () => 800 });
  Object.defineProperty(HTMLElement.prototype, "clientHeight", { configurable: true, get: () => 600 });
  (globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = class { observe() {} unobserve() {} disconnect() {} };
  window.scrollTo = vi.fn();
  Element.prototype.scrollIntoView = vi.fn();
  (window as unknown as { matchMedia: unknown }).matchMedia = (q: string) => ({ matches: false, media: q, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {}, onchange: null, dispatchEvent: () => false });
});

const mount = (path: string) => render(
  <MemoryRouter initialEntries={[path]}><FleetProvider><TooltipProvider><ToastProvider><App /></ToastProvider></TooltipProvider></FleetProvider></MemoryRouter>,
);

const ROUTES: [string, string][] = [
  ["/", "AI daily fleet summary"], ["/map", "Vehicle status"], ["/vehicles", "Add vehicle"], ["/vehicles/V-104", "Van 104"], ["/drivers", "Safety ranking"], ["/drivers/D-01", "John Mercer"],
  ["/trips", "Trips & Routes"], ["/geofences", "Create geofence"], ["/health", "Fleet health"], ["/maintenance", "Work items and history"], ["/fuel", "Fuel transactions"],
  ["/safety", "Driver comparison"], ["/analytics", "Replacement review"], ["/assistant", "FleetPilot Assistant"], ["/reports", "Scheduled reports"], ["/integrations", "QuickBooks Online"],
  ["/notifications", "Notifications"], ["/settings", "Company profile"],
];

describe("routes render with demo data", () => {
  for (const [path, text] of ROUTES) {
    it(`renders ${path}`, async () => {
      const errors: unknown[] = [];
      const orig = console.error; console.error = (...a: unknown[]) => { errors.push(a[0]); };
      const { unmount } = mount(path);
      await waitFor(() => expect(screen.getAllByText(text, { exact: false }).length).toBeGreaterThan(0), { timeout: 4000 });
      console.error = orig; unmount();
      const real = errors.filter((e) => typeof e === "string" && !/act\(|Warning:|not wrapped/.test(e));
      expect(real, `console errors on ${path}`).toEqual([]);
    });
  }
});

describe("interactions change shared state", () => {
  it("adding a vehicle updates the vehicle list and dashboard count", async () => {
    localStorage.clear();
    const { unmount } = mount("/vehicles");
    await waitFor(() => screen.getByText("Add vehicle"));
    const before = generateSnapshot().vehicles.length;
    fireEvent.click(screen.getByRole("button", { name: /add vehicle/i }));
    const dlg = await screen.findByRole("dialog");
    fireEvent.change(within(dlg).getByPlaceholderText("Van 116"), { target: { value: "Van 116" } });
    fireEvent.change(within(dlg).getByPlaceholderText("CXYZ 123"), { target: { value: "CXYZ 123" } });
    fireEvent.click(within(dlg).getByRole("button", { name: /^add vehicle$/i }));
    await waitFor(() => expect(screen.getAllByText("Van 116").length).toBeGreaterThan(0));
    await waitFor(() => expect(JSON.parse(localStorage.getItem("fleetpilot.demo.state")!).vehicles.length).toBe(before + 1), { timeout: 3000 }); // persistence is debounced
    unmount();
    mount("/");
    await waitFor(() => expect(screen.getAllByText(String(before + 1)).length).toBeGreaterThan(0));
  });
  it("vehicle form validates duplicate plate", async () => {
    localStorage.clear();
    mount("/vehicles");
    await waitFor(() => screen.getByText("Add vehicle"));
    fireEvent.click(screen.getByRole("button", { name: /add vehicle/i }));
    const dlg = await screen.findByRole("dialog");
    fireEvent.change(within(dlg).getByPlaceholderText("Van 116"), { target: { value: "Dup" } });
    fireEvent.change(within(dlg).getByPlaceholderText("CXYZ 123"), { target: { value: "CPZL 418" } });
    fireEvent.click(within(dlg).getByRole("button", { name: /^add vehicle$/i }));
    expect(await within(dlg).findByText(/already uses this plate/)).toBeTruthy();
  });
});

describe("demo dataset consistency", () => {
  const s = generateSnapshot(new Date("2026-11-09T15:00:00"));
  const fmt = makeFormatter(s.settings);
  it("has 15 vehicles, 15 drivers, GTA coordinates, and flags V-104/V-108 as overdue", () => {
    expect(s.vehicles).toHaveLength(15); expect(s.drivers).toHaveLength(15);
    for (const v of s.vehicles) { expect(v.position.lat).toBeGreaterThan(43.1); expect(v.position.lat).toBeLessThan(43.9); expect(v.position.lng).toBeGreaterThan(-80.1); expect(v.position.lng).toBeLessThan(-79.3); }
    expect(s.maintenance.filter((m) => m.status === "overdue").map((m) => m.vehicleId).sort()).toEqual(["V-104", "V-108"]);
  });
  it("is deterministic", () => { expect(JSON.stringify(generateSnapshot(new Date("2026-11-09T15:00:00")).trips.slice(0, 20))).toBe(JSON.stringify(s.trips.slice(0, 20))); });
  it("dashboard distance equals the sum of per-vehicle distances", () => {
    const r = makeRange("30d", new Date("2026-11-09T15:00:00"));
    const k = fleetKpis(s, r); const st = allVehicleStats(s, r);
    expect(Math.round(k.distance)).toBe(Math.round(sum(st.map((x) => x.distance))));
    expect(Math.round(k.fuelSpend)).toBe(Math.round(sum(st.map((x) => x.fuelSpend))));
  });
  it("John Mercer is the harsh-braking outlier and scores lowest", () => {
    const r = makeRange("30d", new Date("2026-11-09T15:00:00"));
    const scores = s.drivers.map((d) => ({ d: d.name, ...driverSafety(s, d.id, r) })).sort((a, b) => a.score - b.score);
    expect(scores[0]!.d).toBe("John Mercer");
    expect(scores[0]!.counts.harsh_braking).toBeGreaterThan(scores[Math.floor(scores.length / 2)]!.counts.harsh_braking * 2);
  });
  it("assistant answers agree with metrics and expose calculations", () => {
    const a = answer("Which vehicles should I consider replacing?", s, fmt);
    expect(a.text).toMatch(/Van 108|Van 104/); expect(a.calc).toBeTruthy(); expect(a.sources!.length).toBeGreaterThan(0);
    const idle = answer("How much money did unnecessary idling cost us?", s, fmt);
    expect(idle.chart?.data.length).toBeGreaterThan(0);
  });
  it("formatter switches units and currency for a US configuration", () => {
    const us = makeFormatter({ ...s.settings, country: "US", currency: "USD", distanceUnit: "mi", volumeUnit: "gal", tempUnit: "F", dateFormat: "MM/DD/YYYY", timezone: "America/New_York" });
    expect(us.dist(100)).toBe("62 mi"); expect(us.vol(10)).toMatch(/2\.6|3 gal/); expect(us.temp(100)).toBe("212 °F"); expect(us.money(10)).toMatch(/\$10/);
  });
});
