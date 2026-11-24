import * as React from "react";
import { useNavigate, useParams } from "react-router-dom";
import { ArrowLeft, Pencil, UserPlus, Wrench, FileText, Archive, Map, Gauge, Fuel, Thermometer, BatteryMedium, Power, Navigation } from "lucide-react";
import { Bar, BarChart, LineChart, Line } from "recharts";
import { PageHeader, Stat, ConfirmDialog, EmptyState } from "@/components/shared/PageHeader";
import { VehicleStatusBadge, MaintenanceStatusBadge, SeverityBadge, DemoTag } from "@/components/shared/StatusBadge";
import { DataTable, type Column } from "@/components/shared/DataTable";
import { ChartCard, C, grid, tip, xAxis, yAxis } from "@/components/shared/Charts";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Avatar, Progress } from "@/components/ui/misc";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { BaseMap, FlyTo, Marker, TripPath, vehicleIcon } from "@/components/map/FleetMap";
import { VehicleDialog } from "@/components/forms/VehicleForm";
import { MaintenanceDialog } from "@/components/forms/MaintenanceForm";
import { useFleet } from "@/store/FleetStore";
import { useToast } from "@/components/ui/toast";
import { alarmLabel } from "@/lib/alarms";
import { vehicleStats, tripsIn, currentTrip, serviceStatus, dailySeries } from "@/lib/metrics";
import { nearestPlace } from "./LiveMap";
import type { Trip, MaintenanceRecord, FuelTransaction } from "@/types";

export default function VehicleDetailPage() {
  const { id } = useParams();
  const { s, fmt, range, actions } = useFleet();
  const nav = useNavigate();
  const { toast } = useToast();
  const v = s.vehicles.find((x) => x.id === id);
  const [edit, setEdit] = React.useState(false);
  const [maint, setMaint] = React.useState<"schedule" | "record" | null>(null);
  const [archive, setArchive] = React.useState(false);
  const [assign, setAssign] = React.useState(false);
  const [assignTo, setAssignTo] = React.useState("none");

  if (!v) return <EmptyState icon={Map} title="Vehicle not found" description="It may have been removed from this demo." action={<Button onClick={() => nav("/vehicles")}>Back to vehicles</Button>} />;

  const st = vehicleStats(s, v, range);
  const driver = s.drivers.find((d) => d.id === v.driverId);
  const trips = tripsIn(s, range, v.id).sort((a, b) => b.startTime.localeCompare(a.startTime));
  const live = currentTrip(s, v.id);
  const maintenance = s.maintenance.filter((m) => m.vehicleId === v.id);
  const fuel = s.fuel.filter((f) => f.vehicleId === v.id);
  const diags = s.diagnostics.filter((d) => d.vehicleId === v.id);
  const daily = dailySeries({ ...s, trips: s.trips.filter((t) => t.vehicleId === v.id) }, range);
  const svc = serviceStatus(v);
  const assignments = React.useMemo(() => {
    const out: { driverId: string; from: string; to: string; trips: number }[] = [];
    for (const t of [...s.trips].filter((t) => t.vehicleId === v.id).sort((a, b) => a.startTime.localeCompare(b.startTime))) {
      const last = out[out.length - 1];
      if (last && last.driverId === t.driverId) { last.to = t.endTime; last.trips++; } else out.push({ driverId: t.driverId, from: t.startTime, to: t.endTime, trips: 1 });
    }
    return out.reverse();
  }, [s.trips, v.id]);

  const tripCols: Column<Trip>[] = [
    { key: "start", header: "Start", cell: (t) => <div><div>{fmt.shortDate(t.startTime)} · {fmt.time(t.startTime)}</div><div className="text-xs text-muted-foreground">{t.startLabel.split(" — ")[0]}</div></div>, sortValue: (t) => t.startTime, csv: (t) => t.startTime },
    { key: "end", header: "End", cell: (t) => <div><div>{t.status === "in_progress" ? <Badge variant="success">In progress</Badge> : fmt.time(t.endTime)}</div><div className="text-xs text-muted-foreground">{t.endLabel.split(" — ")[0]}</div></div>, sortValue: (t) => t.endTime },
    { key: "driver", header: "Driver", cell: (t) => s.drivers.find((d) => d.id === t.driverId)?.name ?? "—", sortValue: (t) => s.drivers.find((d) => d.id === t.driverId)?.name ?? "" },
    { key: "dist", header: "Distance", cell: (t) => fmt.dist(t.distanceKm, 1), sortValue: (t) => t.distanceKm, align: "right" },
    { key: "dur", header: "Duration", cell: (t) => fmt.duration(t.durationMin), sortValue: (t) => t.durationMin, align: "right" },
    { key: "idle", header: "Idle", cell: (t) => `${t.idleMin} min`, sortValue: (t) => t.idleMin, align: "right" },
    { key: "max", header: "Max speed", cell: (t) => fmt.speed(t.maxSpeedKmh), sortValue: (t) => t.maxSpeedKmh, align: "right" },
  ];
  const maintCols: Column<MaintenanceRecord>[] = [
    { key: "date", header: "Date", cell: (m) => fmt.date(m.date), sortValue: (m) => m.date },
    { key: "type", header: "Type", cell: (m) => m.type, sortValue: (m) => m.type },
    { key: "odo", header: "Odometer", cell: (m) => fmt.dist(m.odometerKm), sortValue: (m) => m.odometerKm, align: "right" },
    { key: "provider", header: "Provider", cell: (m) => m.provider, sortValue: (m) => m.provider },
    { key: "cost", header: "Cost", cell: (m) => (m.status === "completed" ? fmt.money2(m.cost) : "—"), sortValue: (m) => m.cost, align: "right" },
    { key: "status", header: "Status", cell: (m) => <MaintenanceStatusBadge status={m.status} />, sortValue: (m) => m.status },
    { key: "notes", header: "Notes", cell: (m) => <span className="text-xs text-muted-foreground">{m.notes ?? m.invoiceName ?? ""}</span> },
  ];
  const fuelCols: Column<FuelTransaction>[] = [
    { key: "date", header: "Date", cell: (f) => fmt.dateTime(f.date), sortValue: (f) => f.date },
    { key: "station", header: "Station", cell: (f) => f.station, sortValue: (f) => f.station },
    { key: "l", header: "Volume", cell: (f) => fmt.vol(f.litres, 1), sortValue: (f) => f.litres, align: "right" },
    { key: "p", header: "Unit price", cell: (f) => fmt.money2(f.unitPrice), sortValue: (f) => f.unitPrice, align: "right" },
    { key: "t", header: "Total", cell: (f) => fmt.money2(f.totalCost), sortValue: (f) => f.totalCost, align: "right" },
    { key: "src", header: "Source", cell: (f) => <Badge variant="muted">{f.source}</Badge> },
  ];

  return (
    <>
      <Button variant="ghost" size="sm" className="-ml-2 mb-2" onClick={() => nav("/vehicles")}><ArrowLeft className="h-4 w-4" />Vehicles</Button>
      <PageHeader title={v.name} description={`${v.registration} · ${v.year} ${v.make} ${v.model} · ${v.type}`}
        actions={<>
          <Button variant="outline" size="sm" onClick={() => nav(`/map?vehicle=${v.id}`)}><Map className="h-4 w-4" />Map</Button>
          <Button variant="outline" size="sm" onClick={() => setEdit(true)}><Pencil className="h-4 w-4" />Edit</Button>
          <Button variant="outline" size="sm" onClick={() => { setAssignTo(v.driverId ?? "none"); setAssign(true); }}><UserPlus className="h-4 w-4" />Assign driver</Button>
          <Button variant="outline" size="sm" onClick={() => setMaint("schedule")}><Wrench className="h-4 w-4" />Schedule maintenance</Button>
          <Button variant="outline" size="sm" onClick={() => nav(`/reports?vehicle=${v.id}`)}><FileText className="h-4 w-4" />Reports</Button>
          {!v.archived && <Button variant="ghost" size="sm" className="text-destructive" onClick={() => setArchive(true)}><Archive className="h-4 w-4" />Archive</Button>}
        </>} />

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4 xl:grid-cols-6">
        <Stat label="Status" value={<VehicleStatusBadge status={v.status} freshness={v.freshness} />} sub={`Last message ${fmt.relative(v.lastContact ?? v.lastUpdate)}`} />
        {v.device.source === "obd"
          ? <Stat label="Tracker distance" value={v.odometerSource === "device" ? fmt.dist(v.odometerKm) : "not reported"} sub="counted by the tracker since install, not the vehicle odometer" />
          : <Stat label="Odometer" value={fmt.dist(v.odometerKm)} sub={svc === "overdue" ? <span className="text-red-600">Service overdue</span> : `Next service in ${fmt.dist(v.nextServiceKm - v.odometerKm)}`} />}
        <Stat label={`Distance (${range.preset === "today" ? "today" : "period"})`} value={fmt.dist(st.distance)} sub={`${st.trips} trips`} />
        <Stat label="Utilization" value={fmt.pct(st.utilization)} sub={`${fmt.duration(st.driveMin)} driving`} />
        {v.device.source === "obd"
          ? <Stat label="Tracker" value={v.batteryPct != null ? `${v.batteryPct}% battery` : "battery n/a"} sub={(v.alarms ?? []).length ? <span className="text-red-600">{v.alarms!.map(alarmLabel).join(", ")}</span> : "no device alarms"} />
          : <><Stat label="Operating cost" value={fmt.money(st.opCost)} sub={st.distance ? fmt.perDist(st.costPerKm) : "no distance"} />
        <Stat label="Idle time" value={fmt.duration(st.idleMin)} sub={`≈ ${fmt.money2(st.idleCost)} fuel`} /></>}
      </div>

      <Tabs defaultValue="overview" className="mt-5">
        <TabsList className="flex-wrap"><TabsTrigger value="overview">Overview</TabsTrigger><TabsTrigger value="telemetry">Telemetry</TabsTrigger><TabsTrigger value="history">History</TabsTrigger><TabsTrigger value="financial">Financial</TabsTrigger></TabsList>

        <TabsContent value="overview" className="grid gap-4 lg:grid-cols-3">
          <Card className="lg:col-span-2">
            <CardHeader><CardTitle>Vehicle profile</CardTitle></CardHeader>
            <CardContent className="grid grid-cols-2 gap-x-6 gap-y-3 text-sm sm:grid-cols-3">
              {[["Vehicle ID", v.id], ["Registration", v.registration], ["VIN", v.vin], ["Make / model", `${v.make} ${v.model}`], ["Model year", String(v.year)], ["Type", v.type], ["Fuel type", v.fuelType], ["Tank", fmt.vol(v.tankL)], ["Purchase price", fmt.money(v.purchasePrice)], ["Device", v.device.model], ["Device ID", v.device.id], ["Installed", fmt.date(v.device.installedOn)]].map(([l, val]) => (
                <div key={l}><div className="text-xs text-muted-foreground">{l}</div><div className="font-medium break-all">{val}</div></div>
              ))}
              <div className="col-span-full text-xs text-muted-foreground">Device source: {v.device.source === "demo" ? <DemoTag /> : "OBD-II telemetry"}</div>
            </CardContent>
          </Card>
          <Card>
            <CardHeader><CardTitle>Assigned driver</CardTitle></CardHeader>
            <CardContent>
              {driver ? (
                <button className="flex w-full items-center gap-3 rounded-md border p-3 text-left hover:bg-accent/40" onClick={() => nav(`/drivers/${driver.id}`)}>
                  <Avatar name={driver.name} size="lg" /><div><div className="font-medium">{driver.name}</div><div className="text-xs text-muted-foreground">{driver.employeeId} · {driver.phone}</div><div className="text-xs text-muted-foreground">{driver.email}</div></div>
                </button>
              ) : <EmptyState icon={UserPlus} title="No driver assigned" action={<Button size="sm" onClick={() => setAssign(true)}>Assign driver</Button>} />}
              <div className="mt-4 text-xs font-semibold uppercase tracking-wide text-muted-foreground">Active diagnostics</div>
              {diags.filter((d) => d.active).length === 0 ? <div className="mt-1 text-sm text-muted-foreground">No active fault codes.</div> : diags.filter((d) => d.active).map((d) => <div key={d.id} className="mt-2 flex items-start justify-between rounded-md border border-amber-200 bg-amber-50/40 p-2 text-sm"><div><span className="font-mono font-medium">{d.code}</span> {d.description}</div><SeverityBadge severity={d.severity} /></div>)}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="telemetry" className="grid gap-4 lg:grid-cols-3">
          <Card className="lg:col-span-2 overflow-hidden"><div className="h-[380px]"><BaseMap center={v.position} zoom={13}><FlyTo target={v.position} zoom={13} /><Marker position={[v.position.lat, v.position.lng]} icon={vehicleIcon(v, true)} />{live && <TripPath trip={live} />}</BaseMap></div></Card>
          <div className="space-y-3">
            <Card><CardContent className="grid grid-cols-2 gap-3 p-4 text-sm">
              <Tel icon={Navigation} label="GPS" value={nearestPlace(v.position)} sub={`${v.position.lat.toFixed(5)}, ${v.position.lng.toFixed(5)}`} />
              <Tel icon={Gauge} label="Speed" value={fmt.speed(v.speedKmh)} sub={`Heading ${v.heading}°`} />
              <Tel icon={Power} label="Ignition" value={v.ignitionOn ? "On" : "Off"} />
              <Tel icon={Fuel} label="Fuel level" value={v.fuelLevelPct !== undefined ? `${v.fuelLevelPct}%` : "Not reported"} sub={v.fuelLevelPct !== undefined ? `≈ ${fmt.vol((v.fuelLevelPct / 100) * v.tankL)}` : "vehicle does not expose fuel level"} />
              <Tel icon={Thermometer} label="Engine temp" value={v.engineTempC !== undefined ? fmt.temp(v.engineTempC) : "—"} />
              <Tel icon={BatteryMedium} label="Battery" value={v.batteryV ? `${v.batteryV.toFixed(1)} V` : "—"} sub={v.batteryV && v.batteryV < 12.2 ? "Low — check charging system" : undefined} />
            </CardContent></Card>
            <Card><CardHeader className="pb-2"><CardTitle>Telemetry source</CardTitle></CardHeader><CardContent className="text-xs text-muted-foreground">Positions and readings on this screen are <DemoTag className="mx-1" /> generated for the prototype. Connect a GPS device under Integrations to replace them with live OBD-II data.</CardContent></Card>
          </div>
          <ChartCard title="Daily distance and idle" description="This period" className="lg:col-span-3" height={200}>
            <BarChart data={daily}>{grid}{xAxis("date")}{yAxis(undefined, 36)}{tip((val, n) => (n === "Idle (min)" ? `${val} min` : fmt.dist(val)))}<Bar dataKey="distance" name="Distance" fill={C.blue} radius={[3, 3, 0, 0]} /><Bar dataKey="idleMin" name="Idle (min)" fill={C.amber} radius={[3, 3, 0, 0]} /></BarChart>
          </ChartCard>
        </TabsContent>

        <TabsContent value="history" className="space-y-6">
          <section><h3 className="mb-2 text-sm font-semibold">Trip history <span className="font-normal text-muted-foreground">· {trips.length} trips in period</span></h3>
            <DataTable rows={trips} columns={tripCols} rowKey={(t) => t.id} onRowClick={(t) => nav(`/trips/${t.id}`)} exportName={`${v.id}-trips`} pageSize={8} dense initialSort={{ key: "start", dir: "desc" }} /></section>
          <section><h3 className="mb-2 text-sm font-semibold">Location history <span className="font-normal text-muted-foreground">· trip end points</span></h3>
            <Card><CardContent className="p-0"><ul className="divide-y text-sm">{trips.slice(0, 8).map((t) => <li key={t.id} className="flex items-center justify-between px-4 py-2"><span><span className="text-muted-foreground">{fmt.shortDate(t.endTime)} {fmt.time(t.endTime)}</span> · {t.endLabel}</span><span className="text-xs tabular text-muted-foreground">{t.endPos.lat.toFixed(4)}, {t.endPos.lng.toFixed(4)}</span></li>)}</ul></CardContent></Card></section>
          <section><h3 className="mb-2 text-sm font-semibold">Maintenance history</h3><DataTable rows={maintenance} columns={maintCols} rowKey={(m) => m.id} exportName={`${v.id}-maintenance`} pageSize={8} dense initialSort={{ key: "date", dir: "desc" }} toolbar={<Button size="sm" variant="outline" onClick={() => setMaint("record")}>Record service</Button>} /></section>
          <section><h3 className="mb-2 text-sm font-semibold">Driver assignments</h3>
            <Card><CardContent className="p-0"><ul className="divide-y text-sm">{assignments.slice(0, 6).map((a, i) => <li key={i} className="flex items-center justify-between px-4 py-2"><span className="font-medium">{s.drivers.find((d) => d.id === a.driverId)?.name}</span><span className="text-xs text-muted-foreground">{fmt.shortDate(a.from)} → {fmt.shortDate(a.to)} · {a.trips} trips</span></li>)}</ul></CardContent></Card></section>
        </TabsContent>

        <TabsContent value="financial" className="space-y-4">
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <Stat label="Fuel expenses" value={fmt.money(st.fuelSpend)} sub={`${fmt.vol(st.fuelL)} purchased · ${fmt.economy(st.l100)}`} />
            <Stat label="Maintenance expenses" value={fmt.money(st.maintSpend)} sub="completed services in period" />
            <Stat label="Total operating cost" value={fmt.money(st.opCost)} sub="fuel + maintenance" />
            <Stat label="Cost per distance" value={st.distance ? fmt.perDist(st.costPerKm) : "—"} sub={`over ${fmt.dist(st.distance)}`} />
          </div>
          <ChartCard title="Monthly expense trend" description="Fuel vs maintenance, last 6 months" height={220}>
            <LineChart data={monthly(s, v.id)}>{grid}{xAxis("month")}{yAxis((x) => fmt.money(x), 56)}{tip((val) => fmt.money(val))}<Line type="monotone" dataKey="fuel" name="Fuel" stroke={C.teal} strokeWidth={2} /><Line type="monotone" dataKey="maintenance" name="Maintenance" stroke={C.navy} strokeWidth={2} /></LineChart>
          </ChartCard>
          <section><h3 className="mb-2 text-sm font-semibold">Fuel transactions</h3><DataTable rows={fuel} columns={fuelCols} rowKey={(f) => f.id} exportName={`${v.id}-fuel`} pageSize={8} dense initialSort={{ key: "date", dir: "desc" }} /></section>
          <Card><CardHeader className="pb-2"><CardTitle>Fuel economy</CardTitle><CardDescription>Purchased fuel ÷ distance driven. Estimated consumption from trips: {fmt.vol(st.fuelLEst)}.</CardDescription></CardHeader><CardContent><Progress value={Math.min(100, (st.l100 / 20) * 100)} tone={st.l100 > 16 ? "warning" : "success"} /><div className="mt-1 text-xs text-muted-foreground">{fmt.economy(st.l100)} · fleet target under {fmt.economy(14)}</div></CardContent></Card>
        </TabsContent>
      </Tabs>

      <VehicleDialog open={edit} onOpenChange={setEdit} vehicle={v} />
      <MaintenanceDialog open={!!maint} onOpenChange={(o) => !o && setMaint(null)} vehicleId={v.id} mode={maint ?? "schedule"} />
      <ConfirmDialog open={archive} onOpenChange={setArchive} title={`Archive ${v.name}?`} description="Removed from the active fleet and reports. History is kept." confirmLabel="Archive" destructive onConfirm={() => { actions.archiveVehicle(v.id); toast({ title: `${v.name} archived` }); nav("/vehicles"); }} />
      <Dialog open={assign} onOpenChange={setAssign}><DialogContent className="max-w-sm"><DialogHeader><DialogTitle>Assign driver</DialogTitle></DialogHeader>
        <Select value={assignTo} onValueChange={setAssignTo}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent><SelectItem value="none">Unassigned</SelectItem>{s.drivers.map((d) => <SelectItem key={d.id} value={d.id}>{d.name}</SelectItem>)}</SelectContent></Select>
        <DialogFooter><Button variant="outline" onClick={() => setAssign(false)}>Cancel</Button><Button onClick={() => { actions.assignDriver(v.id, assignTo === "none" ? undefined : assignTo); toast({ title: "Driver assignment updated" }); setAssign(false); }}>Save</Button></DialogFooter></DialogContent></Dialog>
    </>
  );
}

function Tel({ icon: Icon, label, value, sub }: { icon: React.ComponentType<{ className?: string }>; label: string; value: string; sub?: string }) {
  return <div><div className="flex items-center gap-1.5 text-xs text-muted-foreground"><Icon className="h-3.5 w-3.5" />{label}</div><div className="font-medium">{value}</div>{sub && <div className="text-xs text-muted-foreground">{sub}</div>}</div>;
}

function monthly(s: ReturnType<typeof useFleet>["s"], vehicleId: string) {
  const now = new Date(); const out: { month: string; fuel: number; maintenance: number }[] = [];
  for (let i = 5; i >= 0; i--) {
    const from = new Date(now.getFullYear(), now.getMonth() - i, 1), to = new Date(now.getFullYear(), now.getMonth() - i + 1, 1);
    const f = s.fuel.filter((x) => x.vehicleId === vehicleId && new Date(x.date) >= from && new Date(x.date) < to).reduce((a, x) => a + x.totalCost, 0);
    const m = s.maintenance.filter((x) => x.vehicleId === vehicleId && x.status === "completed" && new Date(x.date) >= from && new Date(x.date) < to).reduce((a, x) => a + x.cost, 0);
    out.push({ month: from.toLocaleDateString("en-CA", { month: "short" }), fuel: Math.round(f), maintenance: Math.round(m) });
  }
  return out;
}
