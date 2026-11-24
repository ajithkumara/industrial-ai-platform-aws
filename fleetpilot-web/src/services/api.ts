/**
 * Data-access boundary. The UI only talks to a FleetApi. Today that is LocalDemoApi
 * (generated demo data persisted in the browser). A HttpFleetApi against the FleetPilot
 * AWS backend (Cognito-protected API Gateway, see lambda/mp91_processor) plugs in here
 * without touching pages or components.
 */
import type { FleetSnapshot } from "@/types";
import { generateSnapshot, SNAPSHOT_VERSION } from "@/data/seed";
import { clearState, loadState, saveState } from "@/lib/persist";
import { dataMode } from "./mode";
import { currentUser } from "./auth";

export interface FleetApi {
  load(): Promise<FleetSnapshot>;
  save(snapshot: FleetSnapshot): Promise<void>;
  reset(): Promise<FleetSnapshot>;
  readonly mode: "demo" | "live";
}

/**
 * Starting point for a real account: settings and the integrations catalogue only. Every vehicle,
 * trip, alert or figure the user then sees comes from their own tracker data (services/live.ts)
 * or from what they enter themselves. No generated records.
 */
export function emptyLiveSnapshot(): FleetSnapshot {
  const s = generateSnapshot();
  return {
    ...s,
    vehicles: [], drivers: [], trips: [], fuel: [], maintenance: [], diagnostics: [], safety: [],
    geofences: [], geofenceEvents: [], notifications: [], users: [], apiKeys: [], audit: [],
    conversations: [], scheduledReports: [],
    settings: { ...s.settings, companyName: "My fleet", legalName: "", address: "" },
    integrations: s.integrations.map((i) => ({ ...i, status: i.id === "mictrack" ? "connected" : i.status === "connected" ? "available" : i.status })),
  };
}

export class LocalApi implements FleetApi {
  constructor(readonly mode: "demo" | "live", private keyOf: string | (() => string), private fresh: () => FleetSnapshot) {}
  private get key() { return typeof this.keyOf === "string" ? this.keyOf : this.keyOf(); }
  async load() {
    const cached = loadState<FleetSnapshot>(this.key);
    if (cached && cached.version === SNAPSHOT_VERSION) return cached;
    const s = this.fresh();
    saveState(s, this.key);
    return s;
  }
  async save(snapshot: FleetSnapshot) { saveState(snapshot, this.key); }
  async reset() { clearState(this.key); const s = this.fresh(); saveState(s, this.key); return s; }
}

/** @deprecated kept for tests/back-compat */
export class LocalDemoApi extends LocalApi { constructor() { super("demo", "fleetpilot.demo.state", generateSnapshot); } }

/** Placeholder for the live backend. Not connected in the prototype. */
export class HttpFleetApi implements FleetApi {
  readonly mode = "live" as const;
  constructor(private baseUrl: string, private token: () => Promise<string>) {}
  async load(): Promise<FleetSnapshot> {
    const r = await fetch(`${this.baseUrl}/fleet/snapshot`, { headers: { Authorization: `Bearer ${await this.token()}` } });
    if (!r.ok) throw new Error(`Fleet API ${r.status}`);
    return (await r.json()) as FleetSnapshot;
  }
  async save() { /* server owns the data; mutations go through dedicated endpoints */ }
  async reset() { return this.load(); }
}

export const api: FleetApi = dataMode() === "live"
  ? new LocalApi("live", () => `fleetpilot.live.state.${currentUser()?.sub ?? "anon"}`, emptyLiveSnapshot)
  : new LocalDemoApi();
