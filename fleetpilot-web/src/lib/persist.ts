// Separate browser storage per mode so demo data can never leak into the live view (and vice versa).
const DEFAULT_KEY = "fleetpilot.demo.state";

export function loadState<T>(key = DEFAULT_KEY): T | null {
  try { const raw = localStorage.getItem(key); return raw ? (JSON.parse(raw) as T) : null; } catch { return null; }
}
export function saveState<T>(state: T, key = DEFAULT_KEY) {
  try { localStorage.setItem(key, JSON.stringify(state)); } catch { /* quota or private mode: keeps working in memory */ }
}
export function clearState(key = DEFAULT_KEY) {
  try { localStorage.removeItem(key); } catch { /* ignore */ }
}
