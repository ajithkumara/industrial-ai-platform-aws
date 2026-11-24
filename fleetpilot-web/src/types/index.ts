/** Shared data model. Every screen reads these types; calculations live in lib/metrics.ts. */

export type LatLng = { lat: number; lng: number };
export type ISODate = string;

export type VehicleStatus = "moving" | "idle" | "stopped" | "offline";
/** How current the tracker data is (live accounts only). */
export type Freshness = "live" | "delayed" | "stale" | "offline" | "error";
export type VehicleType = "Cargo Van" | "Pickup Truck" | "Service Truck";
export type FuelType = "Gasoline" | "Diesel";

export interface Vehicle {
  id: string;              // V-101
  name: string;            // "Van 101"
  registration: string;    // Ontario plate
  type: VehicleType;
  make: string;
  model: string;
  year: number;
  vin: string;
  fuelType: FuelType;
  tankL: number;
  driverId?: string;
  status: VehicleStatus;
  odometerKm: number;
  fuelLevelPct?: number;   // from OBD where supported; undefined = not available
  position: LatLng;
  heading: number;
  speedKmh: number;
  ignitionOn: boolean;
  batteryV?: number;
  engineTempC?: number;
  lastUpdate: ISODate;
  lastServiceDate: ISODate;
  nextServiceKm: number;
  nextServiceDate: ISODate;
  device: { id: string; model: string; installedOn: ISODate; source: "obd" | "demo" };
  purchasePrice: number;
  archived?: boolean;
  // ── real-device fields (live accounts; undefined for demo vehicles) ──
  freshness?: Freshness;
  lastContact?: ISODate;       // last message of any kind from the device
  gpsValid?: boolean;          // last message had a GPS fix
  batteryPct?: number | null;  // tracker battery (MP91 reports steps: 0/5/10/20/60/80/100 %)
  alarms?: string[];           // active alarm flags from the last message
  odometerSource?: "device" | "none";
}

export type DriverStatus = "driving" | "available" | "off-duty";

export interface Driver {
  id: string;              // D-01
  name: string;
  employeeId: string;
  email: string;
  phone: string;
  vehicleId?: string;
  status: DriverStatus;
  licenseClass: string;
  licenseExpiry: ISODate;
  hireDate: ISODate;
  coaching: CoachingRecord[];
}

export interface CoachingRecord { id: string; date: ISODate; topic: string; notes: string; coach: string }

export interface TripStop { label: string; position: LatLng; arrival: ISODate; durationMin: number }

export interface Trip {
  id: string;
  vehicleId: string;
  driverId: string;
  startTime: ISODate;
  endTime: ISODate;
  startLabel: string;
  endLabel: string;
  startPos: LatLng;
  endPos: LatLng;
  path: [number, number][];   // simulated polyline, not road-matched
  distanceKm: number;
  durationMin: number;
  idleMin: number;
  maxSpeedKmh: number;
  avgSpeedKmh: number;
  fuelL: number;              // estimated from distance + idle, not measured
  stops: TripStop[];
  status: "completed" | "in_progress";
  speeds?: number[];       // real per-point speed (live trackers)
  times?: ISODate[];       // real per-point fix time (live trackers)
}

export type FuelSource = "fuel-card" | "manual" | "estimated";
export interface FuelTransaction {
  id: string;
  date: ISODate;
  vehicleId: string;
  driverId: string;
  station: string;
  litres: number;
  unitPrice: number;
  totalCost: number;
  odometerKm: number;
  source: FuelSource;
}

export type MaintenanceType = "Oil Change" | "Brake Service" | "Tire Rotation" | "Tire Replacement" | "Safety Inspection" | "Battery Replacement" | "Transmission Service" | "Coolant Flush" | "Other";
export type MaintenanceStatus = "completed" | "scheduled" | "overdue";
export interface MaintenanceRecord {
  id: string;
  vehicleId: string;
  type: MaintenanceType;
  date: ISODate;
  odometerKm: number;
  provider: string;
  cost: number;
  nextDate?: ISODate;
  nextKm?: number;
  notes?: string;
  status: MaintenanceStatus;
  invoiceName?: string;
}

export type Severity = "info" | "low" | "medium" | "high" | "critical";

export interface DiagnosticEvent {
  id: string;
  vehicleId: string;
  code: string;
  description: string;
  severity: Severity;
  date: ISODate;
  active: boolean;
  source: "obd" | "manual";
}

export type SafetyEventType = "speeding" | "harsh_braking" | "harsh_acceleration" | "excessive_idling" | "distracted";
export interface SafetyEvent {
  id: string;
  type: SafetyEventType;
  vehicleId: string;
  driverId: string;
  tripId?: string;
  time: ISODate;
  position: LatLng;
  locationLabel: string;
  severity: Severity;
  value?: number;           // km/h over limit, g-force, idle minutes
  acknowledged: boolean;
  reviewNote?: string;
  reviewedBy?: string;
}

export type GeofenceCategory = "customer" | "depot" | "warehouse" | "restricted";
export interface Geofence {
  id: string;
  name: string;
  category: GeofenceCategory;
  shape: "circle" | "polygon";
  center: LatLng;
  radiusM: number;
  polygon?: LatLng[];
  address: string;
  vehicleIds: string[];     // empty = all vehicles
  alertOnEntry: boolean;
  alertOnExit: boolean;
}

export interface GeofenceEvent { id: string; geofenceId: string; vehicleId: string; type: "enter" | "exit"; time: ISODate }

export type NotificationCategory =
  | "vehicle_offline" | "unauthorized_movement" | "geofence" | "maintenance_due" | "diagnostic"
  | "excessive_idling" | "speeding" | "safety_incident" | "low_battery" | "system";

export interface Notification {
  id: string;
  category: NotificationCategory;
  severity: Severity;
  title: string;
  message: string;
  time: ISODate;
  vehicleId?: string;
  driverId?: string;
  read: boolean;
}

export type Role = "Super Admin" | "Company Owner" | "Fleet Manager" | "Dispatcher" | "Maintenance Manager" | "Driver";
export interface AppUser { id: string; name: string; email: string; role: Role; lastActive: ISODate; active: boolean }

export interface Settings {
  companyName: string;
  legalName: string;
  country: "CA" | "US";
  address: string;
  currency: "CAD" | "USD";
  distanceUnit: "km" | "mi";
  volumeUnit: "L" | "gal";
  tempUnit: "C" | "F";
  timezone: string;
  dateFormat: "YYYY-MM-DD" | "MM/DD/YYYY" | "DD/MM/YYYY";
  businessHours: { start: string; end: string; days: number[] }; // 0=Sun
  speedLimitKmh: number;
  idleThresholdMin: number;
  fuelPricePerL: number;
  idleFuelLPerHour: number;
  dataRetentionMonths: number;
  safetyWeights: { speeding: number; harsh_braking: number; harsh_acceleration: number; excessive_idling: number; distracted: number };
  notificationPrefs: Record<NotificationCategory, { email: boolean; push: boolean; sms: boolean }>;
}

export type IntegrationStatus = "connected" | "available" | "coming_soon";
export interface Integration {
  id: string;
  name: string;
  category: "Accounting" | "Field Service" | "Fuel Cards" | "GPS Hardware" | "AI Dashcams" | "OEM Data" | "Compliance" | "EV Charging";
  description: string;
  status: IntegrationStatus;
  demo: boolean;
}

export interface ApiKey { id: string; name: string; prefix: string; created: ISODate; lastUsed?: ISODate; scopes: string[] }
export interface AuditEntry { id: string; time: ISODate; actor: string; action: string; target: string }

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  text: string;
  time: ISODate;
  cards?: { label: string; value: string; sub?: string }[];
  chart?: { kind: "bar" | "line"; data: { name: string; value: number }[]; unit?: string };
  sources?: string[];
  calc?: string;
}
export interface Conversation { id: string; title: string; started: ISODate; messages: ChatMessage[] }

export interface ScheduledReport { id: string; reportId: string; cadence: "daily" | "weekly" | "monthly"; recipients: string; format: "csv" | "pdf"; nextRun: ISODate }

export type DateRangePreset = "today" | "7d" | "30d" | "month" | "last_month" | "90d";
export interface DateRange { preset: DateRangePreset; from: ISODate; to: ISODate }

export interface FleetSnapshot {
  version: number;
  generatedAt: ISODate;
  vehicles: Vehicle[];
  drivers: Driver[];
  trips: Trip[];
  fuel: FuelTransaction[];
  maintenance: MaintenanceRecord[];
  diagnostics: DiagnosticEvent[];
  safety: SafetyEvent[];
  geofences: Geofence[];
  geofenceEvents: GeofenceEvent[];
  notifications: Notification[];
  settings: Settings;
  users: AppUser[];
  integrations: Integration[];
  apiKeys: ApiKey[];
  audit: AuditEntry[];
  conversations: Conversation[];
  scheduledReports: ScheduledReport[];
}
