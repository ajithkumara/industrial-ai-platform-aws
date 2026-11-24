import * as React from "react";
import { useNavigate } from "react-router-dom";
import { Plus, ClipboardCheck, Wrench, CalendarClock, AlertOctagon, Paperclip } from "lucide-react";
import { Bar, BarChart } from "recharts";
import { PageHeader, Field } from "@/components/shared/PageHeader";
import { KpiCard } from "@/components/shared/KpiCard";
import { DataTable, type Column } from "@/components/shared/DataTable";
import { MaintenanceStatusBadge } from "@/components/shared/StatusBadge";
import { ChartCard, C, grid, tip, xAxis, yAxis } from "@/components/shared/Charts";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input, Textarea } from "@/components/ui/input";
import { MaintenanceDialog } from "@/components/forms/MaintenanceForm";
import { useFleet } from "@/store/FleetStore";
import { useToast } from "@/components/ui/toast";
import { monthlyCosts, maintenanceIn, sum } from "@/lib/metrics";
import { DeviceLimitNotice } from "@/components/shared/DeviceLimitNotice";
import type { MaintenanceRecord } from "@/types";

export default function MaintenancePage() {
  const { s, fmt, range, actions } = useFleet();
  const nav = useNavigate();
  const { toast } = useToast();
  const [dlg, setDlg] = React.useState<"schedule" | "record" | null>(null);
  const [complete, setComplete] = React.useState<MaintenanceRecord | undefined>();
  const [cost, setCost] = React.useState(""); const [notes, setNotes] = React.useState("");
  const vn = (id: string) => s.vehicles.find((v) => v.id === id)?.name ?? id;
  const open = s.maintenance.filter((m) => m.status !== "completed");
  const overdue = open.filter((m) => m.status === "overdue");
  const next30 = open.filter((m) => m.status === "scheduled" && new Date(m.date).getTime() - Date.now() < 30 * 864e5);
  const inspections = open.filter((m) => m.type === "Safety Inspection");
  const spend = sum(maintenanceIn(s, range).map((m) => m.cost));
  const monthly = monthlyCosts(s, 6);
  const byType = Object.entries(s.maintenance.filter((m) => m.status === "completed").reduce((a, m) => ((a[m.type] = (a[m.type] ?? 0) + m.cost), a), {} as Record<string, number>)).map(([type, c]) => ({ type, cost: Math.round(c) })).sort((a, b) => b.cost - a.cost);

  const columns: Column<MaintenanceRecord>[] = [
    { key: "date", header: "Date", cell: (m) => <div>{fmt.date(m.date)}{m.status === "scheduled" && <div className="text-xs text-muted-foreground">in {Math.max(0, Math.round((new Date(m.date).getTime() - Date.now()) / 864e5))} days</div>}</div>, sortValue: (m) => m.date, csv: (m) => m.date.slice(0, 10) },
    { key: "v", header: "Vehicle", cell: (m) => <button className="font-medium hover:underline" onClick={(e) => { e.stopPropagation(); nav(`/vehicles/${m.vehicleId}`); }}>{vn(m.vehicleId)}</button>, sortValue: (m) => vn(m.vehicleId) },
    { key: "type", header: "Type", cell: (m) => m.type, sortValue: (m) => m.type },
    { key: "odo", header: "Odometer", cell: (m) => fmt.dist(m.odometerKm), sortValue: (m) => m.odometerKm, align: "right" },
    { key: "prov", header: "Provider", cell: (m) => <span className="text-xs">{m.provider}</span>, sortValue: (m) => m.provider },
    { key: "cost", header: "Cost", cell: (m) => (m.status === "completed" ? fmt.money2(m.cost) : <span className="text-muted-foreground">—</span>), sortValue: (m) => m.cost, align: "right" },
    { key: "next", header: "Next", cell: (m) => <span className="text-xs text-muted-foreground">{m.nextKm ? fmt.dist(m.nextKm) : ""}{m.nextKm && m.nextDate ? " · " : ""}{m.nextDate ? fmt.date(m.nextDate) : ""}</span> },
    { key: "status", header: "Status", cell: (m) => <MaintenanceStatusBadge status={m.status} />, sortValue: (m) => m.status },
    { key: "notes", header: "Notes", cell: (m) => <span className="text-xs text-muted-foreground">{m.notes}{m.invoiceName && <span className="ml-1 inline-flex items-center gap-0.5 text-secondary"><Paperclip className="h-3 w-3" />{m.invoiceName}</span>}</span> },
    { key: "act", header: "", cell: (m) => (m.status !== "completed" ? <Button size="sm" variant="outline" onClick={(e) => { e.stopPropagation(); setComplete(m); setCost(""); setNotes(""); }}><ClipboardCheck className="h-3.5 w-3.5" />Complete</Button> : null), width: "w-28" },
  ];

  return (
    <>
      <PageHeader title="Maintenance" description="Schedules, reminders and service history. Records here are manually entered; see Vehicle Health for OBD diagnostics." actions={<><Button variant="outline" size="sm" onClick={() => setDlg("record")}>Record service</Button><Button size="sm" onClick={() => setDlg("schedule")}><Plus className="h-4 w-4" />Schedule maintenance</Button></>} />
      <DeviceLimitNotice>Your tracker counts distance since it was installed, not the vehicle’s odometer. Mileage-based service reminders arrive in a later release, once you enter the vehicle odometer at install. Service records you add yourself are kept here.</DeviceLimitNotice>
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <KpiCard label="Maintenance due" value={String(open.length)} sub="open work items" icon={Wrench} tone="info" />
        <KpiCard label="Overdue" value={String(overdue.length)} sub={overdue.map((m) => vn(m.vehicleId)).join(", ") || "none"} icon={AlertOctagon} tone={overdue.length ? "destructive" : "success"} />
        <KpiCard label="Due in 30 days" value={String(next30.length)} sub={`${inspections.length} inspections`} icon={CalendarClock} tone="warning" />
        <KpiCard label="Spend in period" value={fmt.money(spend)} sub={`${maintenanceIn(s, range).length} completed services`} icon={ClipboardCheck} />
      </div>
      <div className="mt-4 grid gap-4 lg:grid-cols-3">
        <ChartCard title="Maintenance spend by month" description="Completed services, last 6 months" className="lg:col-span-2" height={200}>
          <BarChart data={monthly}>{grid}{xAxis("month")}{yAxis((x) => fmt.money(x), 56)}{tip((v) => fmt.money(v))}<Bar dataKey="maintenance" name="Maintenance" fill={C.navy} radius={[3, 3, 0, 0]} /></BarChart>
        </ChartCard>
        <Card><CardHeader className="pb-2"><CardTitle>Spend by service type</CardTitle><CardDescription>All time (demo)</CardDescription></CardHeader><CardContent className="space-y-1.5 text-sm">{byType.slice(0, 6).map((t) => <div key={t.type} className="flex items-center justify-between"><span>{t.type}</span><span className="tabular text-muted-foreground">{fmt.money(t.cost)}</span></div>)}</CardContent></Card>
      </div>
      <section className="mt-5"><h3 className="mb-2 text-sm font-semibold">Work items and history</h3>
        <DataTable rows={s.maintenance} columns={columns} rowKey={(m) => m.id} exportName="maintenance" pageSize={12} dense initialSort={{ key: "date", dir: "desc" }}
          searchKeys={(m) => `${vn(m.vehicleId)} ${m.type} ${m.provider} ${m.notes ?? ""}`}
          filters={[{ key: "status", label: "Status", options: [{ value: "overdue", label: "Overdue" }, { value: "scheduled", label: "Scheduled" }, { value: "completed", label: "Completed" }], predicate: (m, v) => m.status === v },
            { key: "vehicle", label: "Vehicle", options: s.vehicles.filter((v) => !v.archived).map((v) => ({ value: v.id, label: v.name })), predicate: (m, v) => m.vehicleId === v },
            { key: "type", label: "Type", options: [...new Set(s.maintenance.map((m) => m.type))].map((t) => ({ value: t, label: t })), predicate: (m, v) => m.type === v }]} />
      </section>
      <MaintenanceDialog open={!!dlg} onOpenChange={(o) => !o && setDlg(null)} mode={dlg ?? "schedule"} />
      <Dialog open={!!complete} onOpenChange={(o) => !o && setComplete(undefined)}><DialogContent className="max-w-sm"><DialogHeader><DialogTitle>Complete {complete?.type}</DialogTitle></DialogHeader>
        <div className="text-sm text-muted-foreground">{complete && vn(complete.vehicleId)} · {complete?.provider}</div>
        <Field label="Invoice total"><Input inputMode="decimal" value={cost} onChange={(e) => setCost(e.target.value)} placeholder="0.00" /></Field>
        <Field label="Notes"><Textarea value={notes} onChange={(e) => setNotes(e.target.value)} /></Field>
        {complete?.type === "Oil Change" && <Badge variant="info">Completing resets the vehicle’s 8,000 km service interval</Badge>}
        <DialogFooter><Button variant="outline" onClick={() => setComplete(undefined)}>Cancel</Button><Button disabled={!(Number(cost) >= 0) || cost === ""} onClick={() => { if (complete) { actions.completeMaintenance(complete.id, Number(cost), complete.provider, notes || undefined); toast({ title: "Service completed", description: `${vn(complete.vehicleId)} · ${complete.type}` }); } setComplete(undefined); }}>Mark completed</Button></DialogFooter></DialogContent></Dialog>
    </>
  );
}
