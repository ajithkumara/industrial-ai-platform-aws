import * as React from "react";
import { useNavigate } from "react-router-dom";
import { Plus, Trophy } from "lucide-react";
import { Bar, BarChart, Cell } from "recharts";
import { PageHeader } from "@/components/shared/PageHeader";
import { DataTable, type Column } from "@/components/shared/DataTable";
import { DriverStatusBadge } from "@/components/shared/StatusBadge";
import { ChartCard, grid, tip, xAxis, yAxis, C } from "@/components/shared/Charts";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Avatar } from "@/components/ui/misc";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { DriverDialog } from "@/components/forms/DriverForm";
import { useFleet } from "@/store/FleetStore";
import { driverSafety, scoreTone } from "@/lib/metrics";
import type { Driver } from "@/types";

export default function DriversPage() {
  const { s, fmt, range } = useFleet();
  const nav = useNavigate();
  const [add, setAdd] = React.useState(false);
  const rows = React.useMemo(() => s.drivers.map((d) => {
    const st = driverSafety(s, d.id, range);
    const last = [...s.trips].filter((t) => t.driverId === d.id).sort((a, b) => b.endTime.localeCompare(a.endTime))[0];
    return { d, st, last, vehicle: s.vehicles.find((v) => v.id === d.vehicleId) };
  }), [s, range]);
  type Row = (typeof rows)[number];
  const ranked = [...rows].filter((r) => r.st.km > 0).sort((a, b) => b.st.score - a.st.score);
  const fleetAvg = ranked.length ? Math.round(ranked.reduce((a, r) => a + r.st.score, 0) / ranked.length) : 0;

  const columns: Column<Row>[] = [
    { key: "name", header: "Driver", cell: (r) => <div className="flex items-center gap-2.5"><Avatar name={r.d.name} /><div><div className="font-medium">{r.d.name}</div><div className="text-xs text-muted-foreground">{r.d.employeeId} · Class {r.d.licenseClass}</div></div></div>, sortValue: (r) => r.d.name, csv: (r) => r.d.name },
    { key: "contact", header: "Contact", cell: (r) => <div className="text-xs"><div>{r.d.phone}</div><div className="text-muted-foreground">{r.d.email}</div></div>, csv: (r) => r.d.email },
    { key: "vehicle", header: "Vehicle", cell: (r) => (r.vehicle ? <button className="hover:underline" onClick={(e) => { e.stopPropagation(); nav(`/vehicles/${r.vehicle!.id}`); }}>{r.vehicle.name}</button> : <span className="text-muted-foreground">—</span>), sortValue: (r) => r.vehicle?.name ?? "" },
    { key: "status", header: "Status", cell: (r) => <DriverStatusBadge status={r.d.status} />, sortValue: (r) => r.d.status },
    { key: "score", header: "Safety score", cell: (r) => (r.st.km > 0 ? <Badge variant={scoreTone(r.st.score)}>{r.st.score}</Badge> : <span className="text-xs text-muted-foreground">no trips</span>), sortValue: (r) => r.st.score, align: "right" },
    { key: "events", header: "Events", cell: (r) => <span className="text-xs text-muted-foreground">{r.st.counts.speeding} spd · {r.st.counts.harsh_braking} brk · {r.st.counts.harsh_acceleration} acc</span>, sortValue: (r) => r.st.events },
    { key: "km", header: "Distance", cell: (r) => fmt.dist(r.st.km), sortValue: (r) => r.st.km, align: "right" },
    { key: "last", header: "Last activity", cell: (r) => (r.last ? <span className="text-xs">{fmt.relative(r.last.endTime)}</span> : "—"), sortValue: (r) => r.last?.endTime ?? "" },
  ];

  return (
    <>
      <PageHeader title="Drivers" description={`${s.drivers.length} drivers · fleet safety average ${fleetAvg}`} actions={<Button size="sm" onClick={() => setAdd(true)}><Plus className="h-4 w-4" />Add driver</Button>} />
      <div className="mb-4 grid gap-4 lg:grid-cols-3">
        <ChartCard title="Safety ranking" description="Score 0–100 for the selected period. Based on available telemetry and the weights in Settings." className="lg:col-span-2" height={220}>
          <BarChart data={ranked.map((r) => ({ name: r.d.name.split(" ")[0], score: r.st.score }))}>{grid}{xAxis("name")}{yAxis(undefined, 28)}{tip()}
            <Bar dataKey="score" name="Safety score" radius={[3, 3, 0, 0]}>{ranked.map((r, i) => <Cell key={i} fill={r.st.score >= 85 ? C.green : r.st.score >= 70 ? C.amber : C.red} />)}</Bar></BarChart>
        </ChartCard>
        <Card>
          <CardHeader className="pb-2"><CardTitle className="flex items-center gap-2"><Trophy className="h-4 w-4 text-amber-500" />Top and bottom</CardTitle><CardDescription>Needs coaching below 70</CardDescription></CardHeader>
          <CardContent className="space-y-2 text-sm">
            {ranked.slice(0, 3).map((r, i) => <button key={r.d.id} onClick={() => nav(`/drivers/${r.d.id}`)} className="flex w-full items-center gap-2"><span className="w-4 text-xs text-muted-foreground">{i + 1}</span><Avatar name={r.d.name} size="sm" /><span className="flex-1 truncate text-left">{r.d.name}</span><Badge variant="success">{r.st.score}</Badge></button>)}
            <div className="my-1 border-t" />
            {ranked.slice(-3).reverse().map((r) => <button key={r.d.id} onClick={() => nav(`/drivers/${r.d.id}`)} className="flex w-full items-center gap-2"><span className="w-4 text-xs text-muted-foreground">{ranked.indexOf(r) + 1}</span><Avatar name={r.d.name} size="sm" /><span className="flex-1 truncate text-left">{r.d.name}</span><Badge variant={scoreTone(r.st.score)}>{r.st.score}</Badge></button>)}
          </CardContent>
        </Card>
      </div>
      <DataTable rows={rows} columns={columns} rowKey={(r) => r.d.id} onRowClick={(r) => nav(`/drivers/${r.d.id}`)} exportName="drivers" pageSize={15}
        searchKeys={(r) => `${r.d.name} ${r.d.employeeId} ${r.d.email} ${r.vehicle?.name ?? ""}`}
        filters={[{ key: "status", label: "Status", options: [{ value: "driving", label: "Driving" }, { value: "available", label: "Available" }, { value: "off-duty", label: "Off duty" }], predicate: (r, v) => r.d.status === v },
          { key: "score", label: "Score band", options: [{ value: "good", label: "85+" }, { value: "watch", label: "70–84" }, { value: "coach", label: "Below 70" }], predicate: (r, v) => (v === "good" ? r.st.score >= 85 : v === "watch" ? r.st.score >= 70 && r.st.score < 85 : r.st.score < 70) }]} />
      <DriverDialog open={add} onOpenChange={setAdd} />
    </>
  );
}

export type { Driver };
