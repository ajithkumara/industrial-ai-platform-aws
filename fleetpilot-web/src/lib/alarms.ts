/** Human labels for MP91 status/alarm flags (decoded on the backend by h02_parser). */
const LABELS: Record<string, string> = {
  alarm_towed: "towing detected", fuel_power_cut: "fuel/power cut", alarm_battery_removed: "tracker removed from power",
  alarm_shake: "vibration", external_power_disconnected: "tracker unplugged", door_open: "door open", alarm_fence: "geofence",
  alarm_sos: "SOS", alarm_overspeed: "over speed", alarm_unauthorized_ignition: "unauthorized ignition",
  alarm_unauthorized_door: "unauthorized door", vehicle_battery_low: "vehicle battery low", backup_battery_low: "tracker battery low",
};
export const alarmLabel = (a: string) => LABELS[a] ?? a.replace(/_/g, " ");
