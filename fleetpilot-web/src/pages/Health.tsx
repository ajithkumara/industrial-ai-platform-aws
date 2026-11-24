import * as React from "react";
import { useNavigate } from "react-router-dom";
import { HeartPulse, BatteryWarning, Thermometer, AlertTriangle, Wrench, WifiOff } from "lucide-react";
import { PageHeader } from "@/components/shared/PageHeader";
import { KpiCard } from "@/components/shared/KpiCard";
import { DataTable, type Column } from "@/components/shared/DataTable";
import { SeverityBadge, VehicleStatusBadge, DemoTag } from "@/components/shared/StatusBadge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { MaintenanceDialog } from "@/components/forms/MaintenanceForm";
import { useFleet } from "@/store/FleetStore";
import { serviceStatus } from "@/lib/metrics";
import { cn } from "@/lib/utils";
import { DeviceLimitNotice } from "@/components/shared/DeviceLimitNotice";
import type { DiagnosticEvent, Vehicle } from "@/types";

type HealthRow = { v: Vehicle; score: number; issues: string[]; activeCodes: DiagnosticEvent[] };

export function healthScore(v: Vehicle, diags: DiagnosticEvent[]) {
  let score = 100; const issues: string[] = [];
  const svc = serviceStatus(v);
  if (svc === "overdue") { score -= 25; issues.push("Service overdue"); } else if (svc === "due_soon") { score -= 8; issues.push("Service due soon"); }
  if (v.batteryV !== undefined && v.batteryV < 12.2) { score -= 20; issues.push("Low battery voltage"); }
  if (v.engineTempC !== undefined && v.engineTempC > 100) { score -= 20; issues.push("High engine temperature"); }
  for (const d of diags) score -= d.severity === "high" || d.severity === "critical" ? 20 : d.severity === "medium" ? 12 : 6;
  if (diags.length) issues.push(`${diags.length} active fault code${diags.length > 1 ? "s" : ""}`);
  if (v.status === "offline") { score -= 10; issues.push("Telemetry offline"); }
  return { score: Math.max(0, score), issues };
}

export default function HealthPage() {
  const { s, fmt } = useFleet();
  const nav = useNavigate();
  const [maint, setMaint] = React.useState<string | undefined>();
  const rows: HealthRow[] = s.vehicles.filter((v) => !v.archived).map((v) => { const ac = s.diagnostics.filter((d) => d.vehicleId === v.id && d.active); const h = healthScore(v, ac); return { v, ...h, activeCodes: ac }; }).sort((a, b) => a.score - b.score);
  const attention = rows.filter((r) => r.score < 80);
  const lowBatt = rows.filter((r) => r.v.batteryV !== undefined && r.v.batteryV < 12.2).length;
  const codes = s.diagnostics.filter((d) => d.active);

  const columns: Column<HealthRow>[] = [
    { key: "v", header: "Vehicle", cell: (r) => <div><div className="font-medium">{r.v.name}</div><div className="text-xs text-muted-foreground">{r.v.year} {r.v.make} {r.v.model}</div></div>, sortValue: (r) => r.v.name },
    { key: "score", header: "Health", cell: (r) => <div className="flex items-center gap-2"><div className="h-1.5 w-16 rounded-full bg-muted"><div className={cn("h-full rounded-full", r.score >= 80 ? "bg-emerald-500" : r.score >= 60 ? "bg-amber-500" : "bg-red-500")} style={{ width: `${r.score}%` }} /></div><span className="tabular text-xs font-medium">{r.score}</span></div>, sortValue: (r) => r.score },
    { key: "status", header: "Telemetry", cell: (r) => <VehicleStatusBadge status={r.v.status} freshness={r.v.freshness} />, sortValue: (r) => r.v.status },
    { key: "batt", header: "Battery", cell: (r) => (r.v.batteryV ? <span className={r.v.batteryV < 12.2 ? "font-medium text-red-600" : ""}>{r.v.batteryV.toFixed(1)} V</span> : "—"), sortValue: (r) => r.v.batteryV ?? 0, align: "right" },
    { key: "temp", header: "Engine temp", cell: (r) => (r.v.engineTempC !== undefined ? fmt.temp(r.v.engineTempC) : "—"), sortValue: (r) => r.v.engineTempC ?? 0, align: "right" },
    { key: "codes", header: "Fault codes", cell: (r) => (r.activeCodes.length ? <div className="flex flex-wrap gap-1">{r.activeCodes.map((d) => <Badge key={d.id} variant={d.severity === "high" ? "destructive" : "warning"} className="font-mono">{d.code}</Badge>)}</div> : <span className="text-xs text-muted-foreground">none</span>), sortValue: (r) => r.activeCodes.length },
    { key: "svc", header: "Maintenance", cell: (r) => { const st = serviceStatus(r.v); return st === "overdue" ? <Badge variant="destructive">Overdue {fmt.dist(r.v.odometerKm - r.v.nextServiceKm)}</Badge> : st === "due_soon" ? <Badge variant="warning">Due in {fmt.dist(r.v.nextServiceKm - r.v.odometerKm)}</Badge> : <Badge variant="success">OK</Badge>; }, sortValue: (r) => r.v.nextServiceKm - r.v.odometerKm },
    { key: "act", header: "", cell: (r) => <Button size="sm" variant="outline" onClick={(e) => { e.stopPropagation(); setMaint(r.v.id); }}><Wrench className="h-3.5 w-3.5" />Schedule</Button>, width: "w-28" },
  ];
  const codeCols: Column<DiagnosticEvent>[] = [
    { key: "date", header: "Detected", cell: (d) => fmt.dateTime(d.date), sortValue: (d) => d.date },
    { key: "v", header: "Vehicle", cell: (d) => <button className="hover:underline" onClick={() => nav(`/vehicles/${d.vehicleId}`)}>{s.vehicles.find((v) => v.id === d.vehicleId)?.name}</button>, sortValue: (d) => d.vehicleId },
    { key: "code", header: "Code", cell: (d) => <span className="font-mono font-medium">{d.code}</span>, sortValue: (d) => d.code },
    { key: "desc", header: "Description", cell: (d) => d.description },
    { key: "sev", header: "Severity", cell: (d) => <SeverityBadge severity={d.severity} />, sortValue: (d) => d.severity },
    { key: "src", header: "Source", cell: (d) => <Badge variant="muted">{d.source === "obd" ? "OBD-II (simulated)" : "Manual"}</Badge> },
    { key: "state", header: "State", cell: (d) => (d.active ? <Badge variant="warning">Active</Badge> : <Badge variant="success">Cleared</Badge>), sortValue: (d) => (d.active ? 0 : 1) },
  ];

  return (
    <>
      <PageHeader title="Vehicle Health" description="Health score blends OBD diagnostics, battery and temperature readings, telemetry status and maintenance due. Diagnostic codes are simulated OBD data; maintenance records are manually entered." />
      <DeviceLimitNotice>Your tracker (Mictrack MP91) does not read engine fault codes, engine temperature or battery voltage, so no health score is calculated. Tracker battery, device alarms and odometer are shown on each vehicle. A CAN-capable OBD device will unlock real diagnostics.</DeviceLimitNotice>
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <KpiCard label="Vehicles needing attention" value={String(attention.length)} sub="health below 80" icon={HeartPulse} tone={attention.length ? "warning" : "success"} />
        <KpiCard label="Active fault codes" value={String(codes.length)} sub={`${codes.filter((c) => c.severity === "high" || c.severity === "critical").length} high severity`} icon={AlertTriangle} tone={codes.length ? "destructive" : "success"} />
        <KpiCard label="Low battery" value={String(lowBatt)} sub="below 12.2 V at rest" icon={BatteryWarning} tone={lowBatt ? "warning" : "success"} />
        <KpiCard label="Offline" value={String(rows.filter((r) => r.v.status === "offline").length)} sub="no telemetry > 1 h" icon={WifiOff} tone={rows.some((r) => r.v.status === "offline") ? "destructive" : "success"} />
      </div>
      {attention.length > 0 && (
        <Card className="mt-4 border-amber-200 bg-amber-50/40"><CardHeader className="pb-2"><CardTitle>Requires attention</CardTitle><CardDescription>Ordered by health score</CardDescription></CardHeader>
          <CardContent className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">{attention.map((r) => <button key={r.v.id} onClick={() => nav(`/vehicles/${r.v.id}`)} className="rounded-md border bg-card p-3 text-left text-sm hover:bg-accent/40"><div className="flex items-center justify-between"><span className="font-medium">{r.v.name}</span><Badge variant={r.score < 60 ? "destructive" : "warning"}>{r.score}</Badge></div><ul className="mt-1 text-xs text-muted-foreground">{r.issues.map((i) => <li key={i}>• {i}</li>)}</ul></button>)}</CardContent></Card>
      )}
      <section className="mt-5"><h3 className="mb-2 flex items-center gap-2 text-sm font-semibold">Fleet health <DemoTag /></h3><DataTable rows={rows} columns={columns} rowKey={(r) => r.v.id} onRowClick={(r) => nav(`/vehicles/${r.v.id}`)} exportName="vehicle-health" pageSize={15} dense searchKeys={(r) => `${r.v.name} ${r.v.registration}`} filters={[{ key: "band", label: "Health", options: [{ value: "good", label: "80+" }, { value: "watch", label: "60–79" }, { value: "bad", label: "Below 60" }], predicate: (r, v) => (v === "good" ? r.score >= 80 : v === "watch" ? r.score >= 60 && r.score < 80 : r.score < 60) }]} /></section>
      <section className="mt-6"><h3 className="mb-2 flex items-center gap-2 text-sm font-semibold"><Thermometer className="h-4 w-4 text-muted-foreground" />Diagnostic codes</h3><DataTable rows={s.diagnostics} columns={codeCols} rowKey={(d) => d.id} exportName="diagnostics" pageSize={8} dense initialSort={{ key: "date", dir: "desc" }} filters={[{ key: "state", label: "State", options: [{ value: "active", label: "Active" }, { value: "cleared", label: "Cleared" }], predicate: (d, v) => (v === "active" ? d.active : !d.active) }]} /></section>
      <MaintenanceDialog open={!!maint} onOpenChange={(o) => !o && setMaint(undefined)} vehicleId={maint} />
    </>
  );
}
