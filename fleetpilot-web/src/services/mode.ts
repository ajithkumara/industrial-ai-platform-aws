/**
 * Data mode. "live" = the signed-in account's real vehicles only (no generated data anywhere).
 * "demo" = the NorthStar Mechanical sample fleet, always labelled. The hosted app starts in live
 * mode; demo is an explicit choice (Settings → "Explore demo data") and is shown with a banner.
 * Without a backend (local dev, config.js empty) the app can only run in demo mode.
 */
import { liveConfigured } from "./auth";

export type DataMode = "live" | "demo";
const KEY = "fleetpilot.mode";

export function dataMode(): DataMode {
  if (!liveConfigured()) return "demo";
  try { return localStorage.getItem(KEY) === "demo" ? "demo" : "live"; } catch { return "live"; }
}

export const isDemo = () => dataMode() === "demo";
export const canSwitchMode = () => liveConfigured();

export function switchMode(m: DataMode) {
  try { if (m === "demo") localStorage.setItem(KEY, "demo"); else localStorage.removeItem(KEY); } catch { /* ignore */ }
  window.location.reload();
}
