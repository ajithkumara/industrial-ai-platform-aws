import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import type { DriverStatus, Freshness, MaintenanceStatus, Severity, VehicleStatus } from "@/types";
import { isDemo } from "@/services/mode";

export const STATUS_META: Record<VehicleStatus, { label: string; color: string; badge: "success" | "warning" | "muted" | "destructive" }> = {
  moving: { label: "Moving", color: "#16a34a", badge: "success" },
  idle: { label: "Idle", color: "#d97706", badge: "warning" },
  stopped: { label: "Stopped", color: "#64748b", badge: "muted" },
  offline: { label: "Offline", color: "#dc2626", badge: "destructive" },
};

export function VehicleStatusBadge({ status, freshness, dot = true }: { status: VehicleStatus; freshness?: Freshness; dot?: boolean }) {
  const m = STATUS_META[status];
  // Real devices: when data is not current, the freshness badge replaces the motion badge entirely.
  if (freshness && freshness !== "live" && freshness !== "delayed") return <FreshnessBadge freshness={freshness} />;
  return (
    <span className="inline-flex items-center gap-1">
      <Badge variant={m.badge}>
        {dot && <span className={cn("h-1.5 w-1.5 rounded-full", status === "moving" && freshness !== "delayed" && "animate-pulse")} style={{ background: m.color }} />}
        {m.label}
      </Badge>
      {freshness === "delayed" && <FreshnessBadge freshness="delayed" />}
    </span>
  );
}

export function DriverStatusBadge({ status }: { status: DriverStatus }) {
  const v = status === "driving" ? "success" : status === "available" ? "info" : "muted";
  return <Badge variant={v}>{status === "off-duty" ? "Off duty" : status[0]!.toUpperCase() + status.slice(1)}</Badge>;
}

export function SeverityBadge({ severity }: { severity: Severity }) {
  const v = severity === "critical" || severity === "high" ? "destructive" : severity === "medium" ? "warning" : severity === "low" ? "info" : "muted";
  return <Badge variant={v}>{severity[0]!.toUpperCase() + severity.slice(1)}</Badge>;
}

export function MaintenanceStatusBadge({ status }: { status: MaintenanceStatus }) {
  const v = status === "overdue" ? "destructive" : status === "scheduled" ? "info" : "success";
  return <Badge variant={v}>{status[0]!.toUpperCase() + status.slice(1)}</Badge>;
}

/** Shown only in demo mode: in live mode every figure is the account's own data. */
export const DemoTag = ({ className }: { className?: string }) => !isDemo() ? null : (
  <span className={cn("inline-flex items-center rounded border border-dashed border-amber-400/70 bg-amber-50 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-amber-700", className)}>Demo data</span>
);

export const FRESHNESS_META: Record<Freshness, { label: string; badge: "success" | "info" | "warning" | "muted" | "destructive"; hint: string }> = {
  live: { label: "Live", badge: "success", hint: "Reporting on schedule" },
  delayed: { label: "Delayed", badge: "info", hint: "Last report is later than expected" },
  stale: { label: "Stale", badge: "warning", hint: "No recent report: position may be out of date" },
  offline: { label: "Offline", badge: "destructive", hint: "No report for over 24 hours" },
  error: { label: "Device error", badge: "destructive", hint: "Device reports a fault (no GPS fix or power disconnected)" },
};

export function FreshnessBadge({ freshness, title }: { freshness?: Freshness; title?: string }) {
  if (!freshness) return null;
  const m = FRESHNESS_META[freshness];
  return <Badge variant={m.badge} title={title ?? m.hint}>{m.label}</Badge>;
}
