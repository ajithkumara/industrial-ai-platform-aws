/** Regression: a live-tracker trip (no driver) must open in Trip detail, even when it arrives after first render. */
import { describe, it, expect, beforeAll, vi } from "vitest";
import * as React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { TooltipProvider } from "@/components/ui/tooltip";
import { ToastProvider } from "@/components/ui/toast";
import { FleetProvider } from "@/store/FleetStore";
import App from "@/App";

vi.mock("react-leaflet", () => {
  const Box = ({ children }: { children?: React.ReactNode }) => <div>{children}</div>;
  const Nil = () => null;
  return { MapContainer: Box, TileLayer: Nil, Marker: Box, Popup: Nil, Circle: Nil, Polygon: Nil, Polyline: Nil, CircleMarker: Nil, Tooltip: Nil, useMap: () => ({ flyTo() {}, fitBounds() {}, invalidateSize() {}, getZoom: () => 12, setView() {} }) };
});
vi.mock("@/services/auth", () => ({ liveConfigured: () => true, getToken: async () => "t", authConfig: () => ({}), currentUser: () => ({ sub: "u1", email: "me@example.com" }), logout: () => {} }));
vi.mock("@/services/live", async (orig) => {
  const real = await orig<typeof import("@/services/live")>();
  return {
    ...real,
    fetchGold: async () => ({
      account_id: "a", account_name: "T", kind: "personal", generated_at: new Date().toISOString(),
      vehicles: [{ device_id: "7018532019", vehicle_id: "car1", name: "My car", plate: null, driver: null,
        current: { fix_time: new Date().toISOString(), lat: 43.44, lon: -79.67, acc_on: false, speed_kmh: 0, battery_pct: 100 },
        trips: [{ trip_no: 1, start: "2026-11-14T20:17:03+00:00", end: "2026-11-14T20:43:00+00:00", duration_min: 26, distance_km: 11.8, max_speed_kmh: 50,
          start_lat: 43.44, start_lon: -79.67, end_lat: 43.4, end_lon: -79.74, points: [[43.44, -79.67, 10, "a"], [43.42, -79.7, 40, "b"], [43.4, -79.74, 5, "c"]] }] }],
    }),
  };
});

beforeAll(() => {
  Object.defineProperty(HTMLElement.prototype, "clientWidth", { configurable: true, get: () => 800 });
  Object.defineProperty(HTMLElement.prototype, "clientHeight", { configurable: true, get: () => 600 });
  (globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = class { observe() {} unobserve() {} disconnect() {} };
  window.scrollTo = vi.fn();
  (window as unknown as { matchMedia: unknown }).matchMedia = (q: string) => ({ matches: false, media: q, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {}, onchange: null, dispatchEvent: () => false });
});

describe("live trip detail", () => {
  it("opens a driverless live trip by deep link", async () => {
    render(<MemoryRouter initialEntries={["/trips/LT-car1-1-2026-11-14T20:17:03+00:00"]}><FleetProvider><TooltipProvider><ToastProvider><App /></ToastProvider></TooltipProvider></FleetProvider></MemoryRouter>);
    await waitFor(() => expect(screen.getAllByText("No driver assigned", { exact: false }).length).toBeGreaterThan(0), { timeout: 5000 });
  });

  it("live dashboard shows only the account's own vehicles and no demo labels", async () => {
    localStorage.clear();
    render(<MemoryRouter initialEntries={["/"]}><FleetProvider><TooltipProvider><ToastProvider><App /></ToastProvider></TooltipProvider></FleetProvider></MemoryRouter>);
    await waitFor(() => expect(screen.getAllByText("My car").length).toBeGreaterThan(0), { timeout: 5000 });
    expect(screen.queryByText(/Demo data/i)).toBeNull();
    expect(screen.queryByText(/NorthStar/)).toBeNull();
    expect(screen.queryByText("Van 101")).toBeNull();   // a demo vehicle name
    expect(screen.getByText("What your devices report")).toBeTruthy();
  });
});
