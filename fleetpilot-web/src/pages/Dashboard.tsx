import * as React from "react";
import { useNavigate } from "react-router-dom";
import { Area, AreaChart, Bar, BarChart, Line, Cell, ResponsiveContainer } from "recharts";
import { Truck, Activity, PauseCircle, WifiOff, Route, Fuel, Wrench, ShieldAlert, Sparkles, ArrowRight, MapPin, LogIn, LogOut, AlertTriangle, Power, Clock } from "lucide-react";
import { KpiCard } from "@/components/shared/KpiCard";
import { PageHeader } from "@/components/shared/PageHeader";
import { ChartCard, C, grid, tip, xAxis, yAxis, Legend } from "@/components/shared/Charts";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/misc";
import { SeverityBadge } from "@/components/shared/StatusBadge";
import { useFleet } from "@/store/FleetStore";
import { allVehicleStats, dailySeries, driverSafety, fleetKpis, pctChange, scoreTone, serviceStatus, makeRange, tripsIn, sum, weeklySeries } from "@/lib/metrics";
import type { FleetSnapshot, Severity } from "@/types";
import { cn } from "@/lib/utils";
import LiveDashboard from "./LiveDashboard";

type Activity = { time: string; icon: React.ComponentType<{ className?: string }>; label: string; vehicle: string; severity: Severity; to?: string };

function buildActivity(s: FleetSnapshot, now = new Date()): Activity[] {
  const out: Activity[] = [];
  const vn = (id: string) => s.vehicles.find((v) => v.id === id)?.name ?? id;
  const since = new Date(now.getTime() - 36 * 3600e3).toISOString();
  for (const t of s.trips.filter((x) => x.startTime > since)) {
    out.push({ time: t.startTime, icon: Power, label: `Trip started · ${t.startLabel.split(" — ")[0]}`, vehicle: vn(t.vehicleId), severity: "info", to: `/trips/${t.id}` });
    if (t.status === "completed") out.push({ time: t.endTime, icon: MapPin, label: `Trip ended · ${t.endLabel.split(" — ")[0]}`, vehicle: vn(t.vehicleId), severity: "info", to: `/trips/${t.id}` });
  }
  for (const g of s.geofenceEvents.filter((x) => x.time > since)) {
    const gf = s.geofences.find((x) => x.id === g.geofenceId);
    out.push({ time: g.time, icon: g.type === "enter" ? LogIn : LogOut, label: `${g.type === "enter" ? "Entered" : "Exited"} ${gf?.name ?? "geofence"}`, vehicle: vn(g.vehicleId), severity: "low", to: `/geofences?focus=${g.geofenceId}` });
  }
  for (const e of s.safety.filter((x) => x.time > since && (x.type === "harsh_braking" || x.severity === "high" || x.severity === "critical"))) {
    out.push({ time: e.time, icon: AlertTriangle, label: e.type === "harsh_braking" ? "Harsh braking detected" : e.type === "speeding" ? `Speeding +${e.value} km/h` : e.type.replace("_", " "), vehicle: vn(e.vehicleId), severity: e.severity, to: "/safety" });
  }
  for (const n of s.notifications.filter((x) => x.time > since && (x.category === "maintenance_due" || x.category === "vehicle_offline"))) {
    out.push({ time: n.time, icon: n.category === "vehicle_offline" ? WifiOff : Wrench, label: n.title, vehicle: n.vehicleId ? vn(n.vehicleId) : "", severity: n.severity, to: "/notifications" });
  }
  return out.sort((a, b) => b.time.localeCompare(a.time)).slice(0, 14);
}

export function aiDailySummary(s: FleetSnapshot, fmt: ReturnType<typeof useFleet>["fmt"], now = new Date()) {
  const y = new Date(now); y.setDate(y.getDate() - 1);
  const yr = makeRange("today", y);
  const yt = tripsIn(s, yr);
  const km = sum(yt.map((t) => t.distanceKm));
  const activeVehicles = new Set(yt.map((t) => t.vehicleId)).size;
  const idleByVehicle = new Map<string, number>();
  for (const t of yt) idleByVehicle.set(t.vehicleId, (idleByVehicle.get(t.vehicleId) ?? 0) + t.idleMin);
  const worstIdle = [...idleByVehicle.entries()].sort((a, b) => b[1] - a[1])[0];
  const dueSoon = s.vehicles.filter((v) => !v.archived && serviceStatus(v) === "due_soon");
  const overdue = s.vehicles.filter((v) => !v.archived && serviceStatus(v) === "overdue");
  const wk = makeRange("7d", now);
  const brakers = s.drivers.map((d) => ({ d, n: s.safety.filter((e) => e.driverId === d.id && e.type === "harsh_braking" && e.time >= wk.from).length })).sort((a, b) => b.n - a.n);
  const top = brakers[0];
  const medianBrake = brakers.map((b) => b.n).sort((a, b) => a - b)[Math.floor(brakers.length / 2)] ?? 0;
  const vn = (id: string) => s.vehicles.find((v) => v.id === id)?.name ?? id;
  const hour = now.getHours();
  const greet = hour < 12 ? "Good morning" : hour < 17 ? "Good afternoon" : "Good evening";
  const lines: string[] = [];
  lines.push(`${greet}! Your fleet completed ${fmt.dist(km)} yesterday across ${activeVehicles} active vehicle${activeVehicles === 1 ? "" : "s"} in ${yt.length} trips.`);
  if (worstIdle && worstIdle[1] >= 20) lines.push(`${vn(worstIdle[0])} had ${worstIdle[1]} minutes of idling, about ${fmt.money2((worstIdle[1] / 60) * s.settings.idleFuelLPerHour * s.settings.fuelPricePerL)} of fuel.`);
  if (overdue.length) lines.push(`${overdue.map((v) => v.name).join(" and ")} ${overdue.length === 1 ? "is" : "are"} overdue for service.`);
  if (dueSoon.length) lines.push(`${dueSoon.map((v) => v.name).join(" and ")} ${dueSoon.length === 1 ? "is" : "are"} approaching the next service interval.`);
  if (top && top.n >= 3 && top.n > medianBrake * 2) lines.push(`${top.d.name} has ${top.n} harsh-braking events this week, well above the fleet median of ${medianBrake}.`);
  const actions: string[] = [];
  if (worstIdle && worstIdle[1] >= 20) actions.push(`review ${vn(worstIdle[0])} idle behaviour`);
  if (overdue.length) actions.push(`book service for ${overdue.map((v) => v.name).join(", ")}`);
  if (top && top.n >= 3 && top.n > medianBrake * 2) actions.push(`schedule a coaching conversation with ${top.d.name.split(" ")[0]}`);
  return { lines, action: actions.length ? `Recommended action: ${actions.join("; ")}.` : "No urgent actions today." };
}

export default function DashboardPage() {
  const { mode } = useFleet();
  return mode === "live" ? <LiveDashboard /> : <DemoDashboard />;
}

function DemoDashboard() {
  const { s, range, fmt, fleetFilter } = useFleet();
  const nav = useNavigate();
  const snap = React.useMemo<FleetSnapshot>(() => (fleetFilter === "all" ? s : { ...s, vehicles: s.vehicles.filter((v) => v.type === fleetFilter), trips: s.trips.filter((t) => s.vehicles.find((v) => v.id === t.vehicleId)?.type === fleetFilter) }), [s, fleetFilter]);
  const k = React.useMemo(() => fleetKpis(snap, range), [snap, range]);
  const daily = React.useMemo(() => dailySeries(snap, range), [snap, range]);
  const weekly = React.useMemo(() => weeklySeries(snap, 8), [snap]);
  const stats = React.useMemo(() => allVehicleStats(snap, range).sort((a, b) => b.utilization - a.utilization), [snap, range]);
  const safety = React.useMemo(() => snap.drivers.map((d) => ({ d, ...driverSafety(snap, d.id, range) })).filter((x) => x.km > 0).sort((a, b) => a.score - b.score), [snap, range]);
  const activity = React.useMemo(() => buildActivity(snap), [snap]);
  const ai = React.useMemo(() => aiDailySummary(snap, fmt), [snap, fmt]);
  const upcoming = snap.maintenance.filter((m) => m.status !== "completed").sort((a, b) => (a.status === "overdue" ? -1 : 1) - (b.status === "overdue" ? -1 : 1) || a.date.localeCompare(b.date)).slice(0, 5);
  const spark = (key: "distance" | "fuelL" | "safety" | "trips") => daily.map((d) => d[key]);
  const harsh = sum(safety.map((x) => x.counts.harsh_braking)), speeding = sum(safety.map((x) => x.counts.speeding));
  const avgScore = safety.length ? Math.round(sum(safety.map((x) => x.score)) / safety.length) : 0;

  return (
    <>
      <PageHeader title="Dashboard" description={`${s.settings.companyName} · ${fmt.shortDate(range.from)} – ${fmt.shortDate(range.to)}`} />

      <div className="grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-8">
        <KpiCard label="Total vehicles" value={String(k.totalVehicles)} sub={`${k.status.moving + k.status.idle} on the road`} icon={Truck} onClick={() => nav("/vehicles")} />
        <KpiCard label="Active" value={String(k.status.moving)} sub="moving now" icon={Activity} tone="success" onClick={() => nav("/map")} />
        <KpiCard label="Idle" value={String(k.status.idle)} sub="engine on, stopped" icon={PauseCircle} tone="warning" onClick={() => nav("/map")} />
        <KpiCard label="Offline" value={String(k.status.offline)} sub={k.status.offline ? "no telemetry > 1 h" : "all reporting"} icon={WifiOff} tone={k.status.offline ? "destructive" : "default"} onClick={() => nav("/map")} />
        <KpiCard label="Distance" value={fmt.dist(k.distance)} change={pctChange(k.distance, k.distancePrev)} sub="vs prev." icon={Route} tone="info" spark={spark("distance")} onClick={() => nav("/trips")} />
        <KpiCard label="Fuel used (est.)" value={fmt.vol(k.fuelL)} change={pctChange(k.fuelL, k.fuelPrev)} invert sub={fmt.money(k.fuelSpend)} icon={Fuel} spark={spark("fuelL")} onClick={() => nav("/fuel")} />
        <KpiCard label="Maintenance due" value={String(k.maintenanceDue)} sub={k.overdue ? `${k.overdue} overdue` : "none overdue"} icon={Wrench} tone={k.overdue ? "destructive" : "warning"} onClick={() => nav("/maintenance")} />
        <KpiCard label="Safety alerts" value={String(k.safety)} change={pctChange(k.safety, k.safetyPrev)} invert sub="vs prev." icon={ShieldAlert} tone={k.safety > k.safetyPrev ? "destructive" : "success"} spark={spark("safety")} onClick={() => nav("/safety")} />
      </div>

      <div className="mt-4 grid gap-4 xl:grid-cols-3">
        <Card className="xl:col-span-2 overflow-hidden border-brand/30 bg-gradient-to-br from-teal-50/70 via-card to-card">
          <CardHeader className="flex-row items-start justify-between space-y-0 pb-2">
            <div className="flex items-center gap-2">
              <div className="rounded-md bg-brand/15 p-1.5"><Sparkles className="h-4 w-4 text-brand" /></div>
              <div><CardTitle>AI daily fleet summary</CardTitle><CardDescription className="mt-0.5">Generated from yesterday’s trips and this week’s events · simulated assistant</CardDescription></div>
            </div>
            <Badge variant="muted">Demo</Badge>
          </CardHeader>
          <CardContent>
            <p className="text-sm leading-6">{ai.lines.join(" ")}</p>
            <p className="mt-2 text-sm font-medium text-primary">{ai.action}</p>
            <Button variant="brand" size="sm" className="mt-4" onClick={() => nav("/assistant")}>View all AI insights <ArrowRight className="h-3.5 w-3.5" /></Button>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2"><CardTitle>Fleet status now</CardTitle><CardDescription>Live status (simulated positions)</CardDescription></CardHeader>
          <CardContent className="space-y-3">
            {([["moving", "Moving", C.green], ["idle", "Idle", C.amber], ["stopped", "Stopped", C.slate], ["offline", "Offline", C.red]] as const).map(([key, label, color]) => (
              <div key={key} className="flex items-center gap-3 text-sm">
                <span className="h-2.5 w-2.5 rounded-full" style={{ background: color }} />
                <span className="w-16">{label}</span>
                <div className="flex-1"><Progress value={(k.status[key] / Math.max(1, k.totalVehicles)) * 100} tone={key === "moving" ? "success" : key === "idle" ? "warning" : key === "offline" ? "destructive" : "secondary"} /></div>
                <span className="w-6 text-right tabular font-medium">{k.status[key]}</span>
              </div>
            ))}
            <Button variant="outline" size="sm" className="mt-1 w-full" onClick={() => nav("/map")}>Open live map</Button>
          </CardContent>
        </Card>
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <ChartCard title="Fleet activity" description="Vehicles with at least one trip per day" actions={<Legend items={[{ color: C.blue, label: "Active" }, { color: "#cbd5e1", label: "Inactive" }]} />}>
          <BarChart data={daily} barCategoryGap={daily.length > 14 ? 2 : 8}>
            {grid}{xAxis("date")}{yAxis(undefined, 28)}{tip()}
            <Bar dataKey="active" name="Active" stackId="a" fill={C.blue} radius={[0, 0, 0, 0]} />
            <Bar dataKey="inactive" name="Inactive" stackId="a" fill="#e2e8f0" radius={[3, 3, 0, 0]} />
          </BarChart>
        </ChartCard>
        <ChartCard title="Fuel consumption trend" description={`Estimated litres per week · last 8 weeks · ${fmt.money(k.fuelSpend)} spent in period`} actions={<Legend items={[{ color: C.teal, label: "Litres (est.)" }, { color: C.navy, label: "Fuel cost" }]} />}>
          <AreaChart data={weekly}>
            <defs><linearGradient id="fuelg" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor={C.teal} stopOpacity={0.35} /><stop offset="100%" stopColor={C.teal} stopOpacity={0} /></linearGradient></defs>
            {grid}{xAxis("week")}{yAxis(undefined, 36)}{tip((v, n) => (n === "Fuel cost" ? fmt.money(v) : fmt.vol(v)))}
            <Area type="monotone" dataKey="fuelL" name="Litres (est.)" stroke={C.teal} strokeWidth={2} fill="url(#fuelg)" />
            <Line type="monotone" dataKey="fuelCost" name="Fuel cost" stroke={C.navy} strokeWidth={1.5} dot={false} />
          </AreaChart>
        </ChartCard>
      </div>

      <div className="mt-4 grid gap-4 xl:grid-cols-3">
        <Card>
          <CardHeader className="pb-3"><CardTitle>Vehicle utilization</CardTitle><CardDescription>Driving hours ÷ {10} h workday · underutilized &lt; 40%</CardDescription></CardHeader>
          <CardContent className="space-y-2.5">
            {stats.slice(0, 8).map((x) => (
              <button key={x.vehicle.id} onClick={() => nav(`/vehicles/${x.vehicle.id}`)} className="flex w-full items-center gap-3 text-left text-sm">
                <span className="w-20 truncate font-medium">{x.vehicle.name}</span>
                <div className="flex-1"><Progress value={x.utilization} tone={x.utilization < 40 ? "warning" : "secondary"} /></div>
                <span className={cn("w-10 text-right tabular text-xs", x.utilization < 40 ? "text-amber-700 font-semibold" : "text-muted-foreground")}>{Math.round(x.utilization)}%</span>
              </button>
            ))}
            {stats.filter((x) => x.utilization < 40).length > 0 && <p className="pt-1 text-xs text-amber-700">{stats.filter((x) => x.utilization < 40).map((x) => x.vehicle.name).join(", ")} underutilized this period.</p>}
            <Button variant="link" size="sm" className="h-auto p-0" onClick={() => nav("/analytics")}>Full utilization analysis →</Button>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-3"><CardTitle>Driver safety overview</CardTitle><CardDescription>Fleet average score {avgScore} · {harsh} harsh braking · {speeding} speeding</CardDescription></CardHeader>
          <CardContent>
            <div className="h-24">
              <ResponsiveSafety data={daily.map((d) => ({ date: d.date, events: d.safety }))} />
            </div>
            <div className="mt-2 space-y-2">
              {safety.slice(0, 4).map((x) => (
                <button key={x.d.id} onClick={() => nav(`/drivers/${x.d.id}`)} className="flex w-full items-center justify-between text-sm">
                  <span className="truncate">{x.d.name}</span>
                  <span className="flex items-center gap-2 text-xs text-muted-foreground"><span>{x.counts.harsh_braking} brake · {x.counts.speeding} speed</span><Badge variant={scoreTone(x.score)}>{x.score}</Badge></span>
                </button>
              ))}
            </div>
            <Button variant="link" size="sm" className="mt-1 h-auto p-0" onClick={() => nav("/safety")}>Driver safety →</Button>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-3"><CardTitle>Maintenance overview</CardTitle><CardDescription>{k.overdue} overdue · {k.maintenanceDue - k.overdue} upcoming · {k.activeDiagnostics} active diagnostic codes</CardDescription></CardHeader>
          <CardContent className="space-y-2">
            {upcoming.map((m) => {
              const v = s.vehicles.find((x) => x.id === m.vehicleId)!;
              return (
                <button key={m.id} onClick={() => nav("/maintenance")} className="flex w-full items-center justify-between rounded-md border px-3 py-2 text-left text-sm hover:bg-accent/50">
                  <div><div className="font-medium">{v.name} · {m.type}</div><div className="text-xs text-muted-foreground">{m.status === "overdue" ? m.notes : `Due ${fmt.shortDate(m.date)} · ${fmt.dist(m.odometerKm)}`}</div></div>
                  <Badge variant={m.status === "overdue" ? "destructive" : "info"}>{m.status}</Badge>
                </button>
              );
            })}
            {s.diagnostics.filter((d) => d.active).slice(0, 2).map((d) => (
              <button key={d.id} onClick={() => nav("/health")} className="flex w-full items-center justify-between rounded-md border border-amber-200 bg-amber-50/50 px-3 py-2 text-left text-sm">
                <div><div className="font-medium">{s.vehicles.find((v) => v.id === d.vehicleId)?.name} · {d.code}</div><div className="text-xs text-muted-foreground">{d.description}</div></div>
                <SeverityBadge severity={d.severity} />
              </button>
            ))}
          </CardContent>
        </Card>
      </div>

      <Card className="mt-4">
        <CardHeader className="flex-row items-center justify-between space-y-0 pb-3"><div><CardTitle>Recent activity</CardTitle><CardDescription>Last 36 hours across the fleet</CardDescription></div><Button variant="outline" size="sm" onClick={() => nav("/notifications")}>Notification centre</Button></CardHeader>
        <CardContent>
          <ul className="divide-y">
            {activity.map((a, i) => (
              <li key={i}>
                <button className="flex w-full items-center gap-3 py-2 text-left text-sm hover:bg-accent/40" onClick={() => a.to && nav(a.to)}>
                  <span className="w-[4.5rem] shrink-0 text-xs tabular text-muted-foreground"><Clock className="mr-1 inline h-3 w-3" />{fmt.time(a.time)}</span>
                  <a.icon className={cn("h-4 w-4 shrink-0", a.severity === "high" || a.severity === "critical" ? "text-red-500" : a.severity === "medium" ? "text-amber-500" : "text-muted-foreground")} />
                  <span className="w-20 shrink-0 font-medium">{a.vehicle}</span>
                  <span className="flex-1 truncate">{a.label}</span>
                  <SeverityBadge severity={a.severity} />
                </button>
              </li>
            ))}
          </ul>
        </CardContent>
      </Card>
    </>
  );
}

function ResponsiveSafety({ data }: { data: { date: string; events: number }[] }) {
  return (
    <ResponsiveContainer width="100%" height="100%">
      <BarChart data={data} margin={{ top: 4, right: 0, left: 0, bottom: 0 }}>
        {tip()}
        <Bar dataKey="events" name="Safety events" radius={[2, 2, 0, 0]}>
          {data.map((d, i) => <Cell key={i} fill={d.events >= 6 ? C.red : d.events >= 3 ? C.amber : C.blue} />)}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
