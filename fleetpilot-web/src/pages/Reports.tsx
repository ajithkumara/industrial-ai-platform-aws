import * as React from "react";
import { useSearchParams } from "react-router-dom";
import { FileText, Download, CalendarClock, Trash2, FileType } from "lucide-react";
import { PageHeader, Field } from "@/components/shared/PageHeader";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { useFleet } from "@/store/FleetStore";
import { useToast } from "@/components/ui/toast";
import { allVehicleStats, driverSafety, fuelIn, inRange, maintenanceIn, makeRange, replacementReview, safetyIn, sum, tripsIn } from "@/lib/metrics";
import { downloadCsv, cn } from "@/lib/utils";
import type { DateRangePreset, FleetSnapshot } from "@/types";
import type { Fmt } from "@/lib/format";

type Row = Record<string, string | number>;
const REPORTS: { id: string; name: string; description: string; build: (s: FleetSnapshot, fmt: Fmt, r: ReturnType<typeof makeRange>, vehicleId: string, driverId: string) => Row[] }[] = [
  { id: "utilization", name: "Fleet utilization", description: "Driving hours, idle hours, distance and utilization % per vehicle.", build: (s, fmt, r, v) => allVehicleStats(s, r).filter((x) => v === "all" || x.vehicle.id === v).map((x) => ({ Vehicle: x.vehicle.name, Registration: x.vehicle.registration, Trips: x.trips, [`Distance (${fmt.distUnit})`]: Math.round(fmt.distValue(x.distance)), "Drive hours": +(x.driveMin / 60).toFixed(1), "Idle hours": +(x.idleMin / 60).toFixed(1), "Utilization %": Math.round(x.utilization) })) },
  { id: "fuel", name: "Fuel consumption", description: "Purchased fuel, estimated consumption, economy and cost per vehicle.", build: (s, fmt, r, v) => allVehicleStats(s, r).filter((x) => v === "all" || x.vehicle.id === v).map((x) => ({ Vehicle: x.vehicle.name, [`Fuel purchased (${fmt.volUnit})`]: Math.round(x.fuelL), "Fuel cost": +x.fuelSpend.toFixed(2), [`Estimated consumption (${fmt.volUnit})`]: Math.round(x.fuelLEst), Economy: fmt.economy(x.l100), [`Idle fuel (${fmt.volUnit})`]: +x.idleFuelL.toFixed(1), "Idle cost": +x.idleCost.toFixed(2) })) },
  { id: "driver", name: "Driver performance", description: "Distance, trips, events and safety score per driver.", build: (s, fmt, r, _v, d) => s.drivers.filter((x) => d === "all" || x.id === d).map((x) => { const sf = driverSafety(s, x.id, r); return { Driver: x.name, "Employee ID": x.employeeId, Trips: sf.trips, [`Distance (${fmt.distUnit})`]: Math.round(fmt.distValue(sf.km)), Speeding: sf.counts.speeding, "Harsh braking": sf.counts.harsh_braking, "Harsh acceleration": sf.counts.harsh_acceleration, Idling: sf.counts.excessive_idling, "Safety score": sf.km ? sf.score : "" }; }) },
  { id: "maintenance", name: "Vehicle maintenance", description: "Completed, scheduled and overdue services with cost.", build: (s, fmt, r, v) => s.maintenance.filter((m) => (v === "all" || m.vehicleId === v) && (m.status !== "completed" || inRange(m.date, r))).map((m) => ({ Vehicle: s.vehicles.find((x) => x.id === m.vehicleId)?.name ?? m.vehicleId, Type: m.type, Date: fmt.date(m.date), Odometer: Math.round(fmt.distValue(m.odometerKm)), Provider: m.provider, Cost: m.status === "completed" ? +m.cost.toFixed(2) : "", Status: m.status, Notes: m.notes ?? "" })) },
  { id: "cost", name: "Vehicle cost", description: "Fuel, maintenance, operating cost and cost per distance.", build: (s, fmt, r, v) => allVehicleStats(s, r).filter((x) => v === "all" || x.vehicle.id === v).map((x) => ({ Vehicle: x.vehicle.name, Year: x.vehicle.year, [`Distance (${fmt.distUnit})`]: Math.round(fmt.distValue(x.distance)), "Fuel cost": +x.fuelSpend.toFixed(2), "Maintenance cost": +x.maintSpend.toFixed(2), "Operating cost": +x.opCost.toFixed(2), [`Cost per ${fmt.distUnit}`]: x.distance ? +(x.costPerKm / (fmt.distUnit === "mi" ? 0.621371 : 1)).toFixed(3) : "" })) },
  { id: "trips", name: "Trip report", description: "Every trip in the period with distance, duration and max speed.", build: (s, fmt, r, v, d) => tripsIn(s, r).filter((t) => (v === "all" || t.vehicleId === v) && (d === "all" || t.driverId === d)).map((t) => ({ Trip: t.id, Vehicle: s.vehicles.find((x) => x.id === t.vehicleId)?.name ?? "", Driver: s.drivers.find((x) => x.id === t.driverId)?.name ?? "", Start: fmt.dateTime(t.startTime), End: t.status === "completed" ? fmt.dateTime(t.endTime) : "in progress", From: t.startLabel, To: t.endLabel, [`Distance (${fmt.distUnit})`]: +fmt.distValue(t.distanceKm).toFixed(1), "Duration (min)": t.durationMin, "Idle (min)": t.idleMin, "Max speed": fmt.speed(t.maxSpeedKmh) })) },
  { id: "safety", name: "Safety incidents", description: "All safety events with severity and review status.", build: (s, fmt, r, v, d) => safetyIn(s, r, { vehicleId: v === "all" ? undefined : v, driverId: d === "all" ? undefined : d }).map((e) => ({ Time: fmt.dateTime(e.time), Type: e.type, Driver: s.drivers.find((x) => x.id === e.driverId)?.name ?? "", Vehicle: s.vehicles.find((x) => x.id === e.vehicleId)?.name ?? "", Severity: e.severity, Value: e.value ?? "", Location: e.locationLabel, Reviewed: e.acknowledged ? "yes" : "no" })) },
  { id: "profit", name: "Fleet profitability", description: "Operating cost, idle cost, utilization and replacement flags per vehicle.", build: (s, fmt, r, v) => { const st = allVehicleStats(s, r).filter((x) => v === "all" || x.vehicle.id === v); const flagged = new Set(replacementReview(s, st).map((x) => x.vehicle.id)); return st.map((x) => ({ Vehicle: x.vehicle.name, "Operating cost": +x.opCost.toFixed(2), [`Cost per ${fmt.distUnit}`]: x.distance ? +x.costPerKm.toFixed(3) : "", "Idle cost": +x.idleCost.toFixed(2), "Utilization %": Math.round(x.utilization), Economy: fmt.economy(x.l100), "Replacement review": flagged.has(x.vehicle.id) ? "yes" : "" })); } },
];

const PRESETS: { v: DateRangePreset; l: string }[] = [{ v: "today", l: "Today" }, { v: "7d", l: "Last 7 days" }, { v: "30d", l: "Last 30 days" }, { v: "month", l: "This month" }, { v: "last_month", l: "Last month" }, { v: "90d", l: "Last 90 days" }];

export default function ReportsPage() {
  const { s, fmt, range, actions } = useFleet();
  const { toast } = useToast();
  const [params] = useSearchParams();
  const [sel, setSel] = React.useState("utilization");
  const [preset, setPreset] = React.useState<DateRangePreset>(range.preset);
  const [vehicle, setVehicle] = React.useState(params.get("vehicle") ?? "all");
  const [driver, setDriver] = React.useState("all");
  const [sched, setSched] = React.useState(false);
  const [cadence, setCadence] = React.useState<"daily" | "weekly" | "monthly">("weekly");
  const [recipients, setRecipients] = React.useState(s.users[0]?.email ?? "");
  const [format, setFormat] = React.useState<"csv" | "pdf">("pdf");
  const report = REPORTS.find((r) => r.id === sel)!;
  const r = makeRange(preset);
  const rows = React.useMemo(() => report.build(s, fmt, r, vehicle, driver), [report, s, fmt, preset, vehicle, driver]); // eslint-disable-line react-hooks/exhaustive-deps
  const cols = rows[0] ? Object.keys(rows[0]) : [];
  const summary = { trips: tripsIn(s, r).length, fuel: sum(fuelIn(s, r).map((f) => f.totalCost)), maint: sum(maintenanceIn(s, r).map((m) => m.cost)) };

  return (
    <>
      <PageHeader title="Reports" description="Build a report, preview it, export CSV or schedule delivery." />
      <div className="grid gap-4 lg:grid-cols-4">
        <div className="space-y-2">
          {REPORTS.map((rp) => <button key={rp.id} onClick={() => setSel(rp.id)} className={cn("flex w-full items-start gap-2.5 rounded-lg border bg-card p-3 text-left hover:bg-accent/40", sel === rp.id && "ring-2 ring-secondary")}><FileText className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" /><div><div className="text-sm font-medium">{rp.name}</div><div className="text-xs text-muted-foreground">{rp.description}</div></div></button>)}
        </div>
        <div className="space-y-4 lg:col-span-3">
          <Card>
            <CardContent className="grid gap-3 p-4 sm:grid-cols-4">
              <Field label="Period"><Select value={preset} onValueChange={(v) => setPreset(v as DateRangePreset)}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent>{PRESETS.map((p) => <SelectItem key={p.v} value={p.v}>{p.l}</SelectItem>)}</SelectContent></Select></Field>
              <Field label="Vehicle"><Select value={vehicle} onValueChange={setVehicle}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent><SelectItem value="all">All vehicles</SelectItem>{s.vehicles.filter((v) => !v.archived).map((v) => <SelectItem key={v.id} value={v.id}>{v.name}</SelectItem>)}</SelectContent></Select></Field>
              <Field label="Driver"><Select value={driver} onValueChange={setDriver}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent><SelectItem value="all">All drivers</SelectItem>{s.drivers.map((d) => <SelectItem key={d.id} value={d.id}>{d.name}</SelectItem>)}</SelectContent></Select></Field>
              <div className="flex items-end gap-2">
                <Button className="flex-1" onClick={() => { downloadCsv(`${report.id}-${r.from.slice(0, 10)}.csv`, rows); toast({ title: "CSV exported", description: `${rows.length} rows` }); }} disabled={!rows.length}><Download className="h-4 w-4" />CSV</Button>
                <Button variant="outline" onClick={() => toast({ title: "PDF export not connected", description: "PDF rendering runs server-side in the hosted build. Use CSV for now.", tone: "info" })}><FileType className="h-4 w-4" />PDF</Button>
              </div>
            </CardContent>
          </Card>
          <Card>
            <CardHeader className="flex-row items-start justify-between space-y-0"><div><CardTitle>{report.name}</CardTitle><CardDescription>{s.settings.companyName} · {fmt.date(r.from)} – {fmt.date(r.to)} · {rows.length} rows · period totals: {summary.trips} trips, {fmt.money(summary.fuel)} fuel, {fmt.money(summary.maint)} maintenance</CardDescription></div><Button variant="outline" size="sm" onClick={() => setSched(true)}><CalendarClock className="h-4 w-4" />Schedule</Button></CardHeader>
            <CardContent className="p-0">
              <div className="max-h-[480px] overflow-auto border-t">
                <Table><TableHeader><TableRow>{cols.map((c) => <TableHead key={c} className="whitespace-nowrap">{c}</TableHead>)}</TableRow></TableHeader>
                  <TableBody>{rows.slice(0, 200).map((row, i) => <TableRow key={i}>{cols.map((c) => <TableCell key={c} className={cn("whitespace-nowrap text-xs", typeof row[c] === "number" && "text-right tabular")}>{String(row[c])}</TableCell>)}</TableRow>)}{rows.length === 0 && <TableRow><TableCell colSpan={Math.max(1, cols.length)} className="py-10 text-center text-sm text-muted-foreground">No data for these filters.</TableCell></TableRow>}</TableBody></Table>
              </div>
              {rows.length > 200 && <div className="border-t px-4 py-2 text-xs text-muted-foreground">Preview shows the first 200 rows; the CSV contains all {rows.length}.</div>}
            </CardContent>
          </Card>
          <Card>
            <CardHeader className="pb-2"><CardTitle>Scheduled reports</CardTitle><CardDescription>Delivery runs on the FleetPilot backend; in this prototype schedules are saved locally.</CardDescription></CardHeader>
            <CardContent className="space-y-2">
              {s.scheduledReports.length === 0 && <div className="text-xs text-muted-foreground">No schedules yet.</div>}
              {s.scheduledReports.map((sr) => <div key={sr.id} className="flex items-center justify-between rounded-md border p-2.5 text-sm"><div><span className="font-medium">{REPORTS.find((x) => x.id === sr.reportId)?.name}</span> <Badge variant="muted" className="ml-1">{sr.cadence}</Badge> <Badge variant="muted">{sr.format.toUpperCase()}</Badge><div className="text-xs text-muted-foreground">To {sr.recipients} · next {fmt.date(sr.nextRun)}</div></div><Button size="iconSm" variant="ghost" onClick={() => actions.removeScheduledReport(sr.id)}><Trash2 className="h-4 w-4" /></Button></div>)}
            </CardContent>
          </Card>
        </div>
      </div>
      <Dialog open={sched} onOpenChange={setSched}><DialogContent className="max-w-sm"><DialogHeader><DialogTitle>Schedule {report.name}</DialogTitle><DialogDescription>Filters above are saved with the schedule.</DialogDescription></DialogHeader>
        <Field label="Cadence"><Select value={cadence} onValueChange={(v) => setCadence(v as typeof cadence)}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent><SelectItem value="daily">Daily (6:00)</SelectItem><SelectItem value="weekly">Weekly (Monday 6:00)</SelectItem><SelectItem value="monthly">Monthly (1st)</SelectItem></SelectContent></Select></Field>
        <Field label="Recipients"><Input value={recipients} onChange={(e) => setRecipients(e.target.value)} placeholder="owner@company.ca, ops@company.ca" /></Field>
        <Field label="Format"><Select value={format} onValueChange={(v) => setFormat(v as typeof format)}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent><SelectItem value="pdf">PDF</SelectItem><SelectItem value="csv">CSV</SelectItem></SelectContent></Select></Field>
        <DialogFooter><Button variant="outline" onClick={() => setSched(false)}>Cancel</Button><Button disabled={!recipients.includes("@")} onClick={() => { const next = new Date(); next.setDate(next.getDate() + (cadence === "daily" ? 1 : cadence === "weekly" ? 7 : 30)); actions.addScheduledReport({ reportId: report.id, cadence, recipients, format, nextRun: next.toISOString() }); toast({ title: "Report scheduled" }); setSched(false); }}>Save schedule</Button></DialogFooter></DialogContent></Dialog>
    </>
  );
}
