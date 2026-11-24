import * as React from "react";
import { useNavigate } from "react-router-dom";
import { Bar, BarChart, Line, LineChart, Cell, ScatterChart, Scatter, XAxis, YAxis, ZAxis } from "recharts";
import { TrendingDown, TrendingUp, Timer, Replace, Fuel, Wrench } from "lucide-react";
import { PageHeader, Stat } from "@/components/shared/PageHeader";
import { ChartCard, C, grid, tip, xAxis, yAxis, Legend } from "@/components/shared/Charts";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/misc";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { DataTable } from "@/components/shared/DataTable";
import { useFleet } from "@/store/FleetStore";
import { DeviceLimitNotice } from "@/components/shared/DeviceLimitNotice";
import { allVehicleStats, dailySeries, driverSafety, monthlyCosts, replacementReview, sum, weeklySeries, median, inRange, scoreTone, WORKDAY_HOURS } from "@/lib/metrics";

export default function AnalyticsPage() {
  const { s, fmt, range, fleetFilter } = useFleet();
  const nav = useNavigate();
  const [vehicleF, setVehicleF] = React.useState("all");
  const snap = React.useMemo(() => {
    const keep = (id: string) => (vehicleF === "all" || id === vehicleF) && (fleetFilter === "all" || s.vehicles.find((v) => v.id === id)?.type === fleetFilter);
    return { ...s, vehicles: s.vehicles.filter((v) => keep(v.id)), trips: s.trips.filter((t) => keep(t.vehicleId)), fuel: s.fuel.filter((f) => keep(f.vehicleId)), maintenance: s.maintenance.filter((m) => keep(m.vehicleId)), safety: s.safety.filter((e) => keep(e.vehicleId)) };
  }, [s, vehicleF, fleetFilter]);
  const stats = React.useMemo(() => allVehicleStats(snap, range), [snap, range]);
  const daily = dailySeries(snap, range), weekly = weeklySeries(snap, 8), monthly = monthlyCosts(snap, 6);
  const km = sum(stats.map((x) => x.distance)), opCost = sum(stats.map((x) => x.opCost)), driveH = sum(stats.map((x) => x.driveMin)) / 60, idleH = sum(stats.map((x) => x.idleMin)) / 60;
  const util = stats.length ? sum(stats.map((x) => x.utilization)) / stats.length : 0;
  const under = stats.filter((x) => x.utilization < 40);
  const tco = sum(stats.map((x) => x.vehicle.purchasePrice / 60)) + opCost; // straight-line 5-year capital + period operating
  const byCost = [...stats].sort((a, b) => b.costPerKm - a.costPerKm);
  const byIdle = [...stats].sort((a, b) => b.idleMin - a.idleMin);
  const medEcon = median(stats.filter((x) => x.distance > 100).map((x) => x.l100));
  const replace = replacementReview(snap, stats);
  const drivers = s.drivers.map((d) => { const sf = driverSafety(snap, d.id, range); const t = snap.trips.filter((x) => x.driverId === d.id && inRange(x.startTime, range)); const drive = sum(t.map((x) => x.durationMin)), idle = sum(t.map((x) => x.idleMin)); return { d, km: sf.km, trips: t.length, drive, idle, productive: drive ? ((drive - idle) / drive) * 100 : 0, score: sf.score, util: Math.min(100, (drive / 60 / (Math.max(1, Math.round(((new Date(range.to).getTime() - new Date(range.from).getTime()) / 864e5) * 6 / 7)) * WORKDAY_HOURS)) * 100) }; }).filter((x) => x.trips > 0).sort((a, b) => b.km - a.km);

  return (
    <>
      <PageHeader title="Fleet Analytics" description="Utilization, cost and profitability insights for the selected period. Filters: date range and fleet selector in the top bar, vehicle below." actions={<Select value={vehicleF} onValueChange={setVehicleF}><SelectTrigger className="h-9 w-48 bg-card"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="all">All vehicles</SelectItem>{s.vehicles.filter((v) => !v.archived).map((v) => <SelectItem key={v.id} value={v.id}>{v.name}</SelectItem>)}</SelectContent></Select>} />
      <DeviceLimitNotice>Only trip-based figures (distance, driving time, utilization) come from your trackers. Fuel and cost analysis needs fuel and expense records.</DeviceLimitNotice>
      <Tabs defaultValue="profit">
        <TabsList className="flex-wrap"><TabsTrigger value="profit">Profitability</TabsTrigger><TabsTrigger value="util">Utilization</TabsTrigger><TabsTrigger value="cost">Costs</TabsTrigger><TabsTrigger value="drivers">Driver productivity</TabsTrigger></TabsList>

        <TabsContent value="profit" className="space-y-4">
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <Stat label="Operating cost (period)" value={fmt.money(opCost)} sub={km ? `${fmt.perDist(opCost / km)} over ${fmt.dist(km)}` : "no distance"} />
            <Stat label="Idle cost (est.)" value={fmt.money(sum(stats.map((x) => x.idleCost)))} sub={`${fmt.duration(idleH * 60)} · ${fmt.vol(sum(stats.map((x) => x.idleFuelL)))}`} />
            <Stat label="Underutilized vehicles" value={under.length} sub="below 40% of a 10 h day" />
            <Stat label="Replacement review" value={replace.length} sub="vehicles flagged" />
          </div>
          <div className="grid gap-4 lg:grid-cols-2">
            <Card><CardHeader className="pb-2"><CardTitle className="flex items-center gap-2"><TrendingUp className="h-4 w-4 text-red-500" />Highest-cost vehicles</CardTitle><CardDescription>Cost per {fmt.distUnit}, fuel + maintenance</CardDescription></CardHeader>
              <CardContent className="space-y-2">{byCost.slice(0, 5).map((x) => <Row key={x.vehicle.id} onClick={() => nav(`/vehicles/${x.vehicle.id}`)} name={x.vehicle.name} sub={`${fmt.money(x.opCost)} · ${fmt.dist(x.distance)}`} value={x.distance ? fmt.perDist(x.costPerKm) : "—"} pct={byCost[0] ? (x.costPerKm / byCost[0].costPerKm) * 100 : 0} tone="destructive" />)}</CardContent></Card>
            <Card><CardHeader className="pb-2"><CardTitle className="flex items-center gap-2"><TrendingDown className="h-4 w-4 text-emerald-600" />Lowest-cost vehicles</CardTitle><CardDescription>Best performers this period</CardDescription></CardHeader>
              <CardContent className="space-y-2">{[...byCost].filter((x) => x.distance > 100).reverse().slice(0, 5).map((x) => <Row key={x.vehicle.id} onClick={() => nav(`/vehicles/${x.vehicle.id}`)} name={x.vehicle.name} sub={`${fmt.money(x.opCost)} · ${fmt.dist(x.distance)}`} value={fmt.perDist(x.costPerKm)} pct={byCost[0] ? (x.costPerKm / byCost[0].costPerKm) * 100 : 0} tone="success" />)}</CardContent></Card>
            <Card><CardHeader className="pb-2"><CardTitle className="flex items-center gap-2"><Timer className="h-4 w-4 text-amber-500" />Excessive idle time</CardTitle><CardDescription>Idle fuel at {fmt.vol(s.settings.idleFuelLPerHour, 1)}/h and {fmt.money2(s.settings.fuelPricePerL)}/{fmt.volUnit}</CardDescription></CardHeader>
              <CardContent className="space-y-2">{byIdle.slice(0, 5).map((x) => <Row key={x.vehicle.id} onClick={() => nav(`/vehicles/${x.vehicle.id}`)} name={x.vehicle.name} sub={`${x.trips} trips · ${x.driveMin ? Math.round((x.idleMin / x.driveMin) * 100) : 0}% of trip time`} value={`${fmt.duration(x.idleMin)} · ${fmt.money2(x.idleCost)}`} pct={byIdle[0] ? (x.idleMin / byIdle[0].idleMin) * 100 : 0} tone="warning" />)}</CardContent></Card>
            <Card><CardHeader className="pb-2"><CardTitle className="flex items-center gap-2"><Replace className="h-4 w-4 text-slate-500" />Replacement review</CardTitle><CardDescription>Age ≥ 8 yrs, cost/{fmt.distUnit} &gt; 1.5× median, repeat fault codes or &gt; 240,000 {fmt.distUnit}</CardDescription></CardHeader>
              <CardContent className="space-y-2">{replace.length === 0 && <div className="text-xs text-muted-foreground">No vehicles flagged for this period.</div>}{replace.map((x) => <button key={x.vehicle.id} onClick={() => nav(`/vehicles/${x.vehicle.id}`)} className="flex w-full items-center justify-between rounded-md border p-2.5 text-left text-sm hover:bg-accent/40"><div><div className="font-medium">{x.vehicle.name} <span className="font-normal text-muted-foreground">· {x.vehicle.year} {x.vehicle.make} {x.vehicle.model}</span></div><div className="text-xs text-muted-foreground">{x.reasons.join(" · ")}</div></div><Badge variant="warning">Review</Badge></button>)}</CardContent></Card>
          </div>
          <div className="grid gap-4 lg:grid-cols-2">
            <Card><CardHeader className="pb-2"><CardTitle className="flex items-center gap-2"><Fuel className="h-4 w-4 text-teal-600" />Unusual fuel consumption</CardTitle><CardDescription>Fleet median {fmt.economy(medEcon)}</CardDescription></CardHeader>
              <CardContent className="space-y-2">{stats.filter((x) => x.distance > 100 && x.l100 > medEcon * 1.2).sort((a, b) => b.l100 - a.l100).map((x) => <Row key={x.vehicle.id} onClick={() => nav(`/vehicles/${x.vehicle.id}`)} name={x.vehicle.name} sub={`${Math.round((x.l100 / medEcon - 1) * 100)}% above median`} value={fmt.economy(x.l100)} pct={(x.l100 / (medEcon * 1.6)) * 100} tone="warning" />)}{stats.filter((x) => x.distance > 100 && x.l100 > medEcon * 1.2).length === 0 && <div className="text-xs text-muted-foreground">No outliers.</div>}</CardContent></Card>
            <ChartCard title="Maintenance cost trend" description="Monthly, last 6 months" height={200}><LineChart data={monthly}>{grid}{xAxis("month")}{yAxis((x) => fmt.money(x), 56)}{tip((v) => fmt.money(v))}<Line type="monotone" dataKey="maintenance" name="Maintenance" stroke={C.navy} strokeWidth={2} /></LineChart></ChartCard>
          </div>
        </TabsContent>

        <TabsContent value="util" className="space-y-4">
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <Stat label="Average utilization" value={fmt.pct(util)} sub={`${stats.length} vehicles · ${WORKDAY_HOURS} h workday`} />
            <Stat label="Active hours" value={fmt.num(driveH, 1)} sub="driving time in trips" />
            <Stat label="Idle hours" value={fmt.num(idleH, 1)} sub={`${driveH ? Math.round((idleH / driveH) * 100) : 0}% of active`} />
            <Stat label="Distance" value={fmt.dist(km)} sub={`${fmt.dist(daily.length ? km / daily.length : 0)} per day`} />
          </div>
          <div className="grid gap-4 lg:grid-cols-2">
            <ChartCard title="Utilization by vehicle" description="Underutilized (< 40%) in amber" height={260}><BarChart data={[...stats].sort((a, b) => b.utilization - a.utilization).map((x) => ({ name: x.vehicle.name.replace("Truck ", "T").replace("Van ", "V"), util: Math.round(x.utilization) }))}>{grid}{xAxis("name")}{yAxis((x) => `${x}%`, 36)}{tip((v) => `${v}%`)}<Bar dataKey="util" name="Utilization" radius={[3, 3, 0, 0]}>{[...stats].sort((a, b) => b.utilization - a.utilization).map((x, i) => <Cell key={i} fill={x.utilization < 40 ? C.amber : C.blue} />)}</Bar></BarChart></ChartCard>
            <ChartCard title="Daily distance" description="This period" height={260}><BarChart data={daily}>{grid}{xAxis("date")}{yAxis(undefined, 36)}{tip((v) => fmt.dist(v))}<Bar dataKey="distance" name="Distance" fill={C.blue} radius={[3, 3, 0, 0]} /></BarChart></ChartCard>
            <ChartCard title="Weekly distance" description="Last 8 weeks" height={220}><LineChart data={weekly}>{grid}{xAxis("week")}{yAxis(undefined, 36)}{tip((v) => fmt.dist(v))}<Line type="monotone" dataKey="distance" name="Distance" stroke={C.blue} strokeWidth={2} /></LineChart></ChartCard>
            <Card><CardHeader className="pb-2"><CardTitle>Underutilized vehicles</CardTitle><CardDescription>Candidates for reassignment or disposal</CardDescription></CardHeader><CardContent className="space-y-2">{under.length === 0 && <div className="text-xs text-muted-foreground">All vehicles above 40%.</div>}{under.map((x) => <Row key={x.vehicle.id} onClick={() => nav(`/vehicles/${x.vehicle.id}`)} name={x.vehicle.name} sub={`${x.trips} trips · ${fmt.dist(x.distance)}`} value={fmt.pct(x.utilization)} pct={x.utilization} tone="warning" />)}</CardContent></Card>
          </div>
        </TabsContent>

        <TabsContent value="cost" className="space-y-4">
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <Stat label="Total cost of ownership" value={fmt.money(tco)} sub="period operating + straight-line capital (5 yr)" />
            <Stat label={`Cost per ${fmt.distUnit}`} value={km ? fmt.perDist(opCost / km) : "—"} sub="fuel + maintenance" />
            <Stat label="Fuel expenses" value={fmt.money(sum(stats.map((x) => x.fuelSpend)))} sub={`${Math.round(opCost ? (sum(stats.map((x) => x.fuelSpend)) / opCost) * 100 : 0)}% of operating`} />
            <Stat label="Maintenance expenses" value={fmt.money(sum(stats.map((x) => x.maintSpend)))} sub={<span className="inline-flex items-center gap-1"><Wrench className="h-3 w-3" />completed services</span>} />
          </div>
          <ChartCard title="Operating cost by vehicle" description="Stacked fuel and maintenance" height={260} actions={<Legend items={[{ color: C.teal, label: "Fuel" }, { color: C.navy, label: "Maintenance" }]} />}><BarChart data={[...stats].sort((a, b) => b.opCost - a.opCost).map((x) => ({ name: x.vehicle.name.replace("Truck ", "T").replace("Van ", "V"), fuel: Math.round(x.fuelSpend), maintenance: Math.round(x.maintSpend) }))}>{grid}{xAxis("name")}{yAxis((x) => fmt.money(x), 56)}{tip((v) => fmt.money(v))}<Bar dataKey="fuel" name="Fuel" stackId="a" fill={C.teal} /><Bar dataKey="maintenance" name="Maintenance" stackId="a" fill={C.navy} radius={[3, 3, 0, 0]} /></BarChart></ChartCard>
          <ChartCard title={`Cost per ${fmt.distUnit} vs distance`} description="Top-left = expensive and lightly used. Bubble size = idle minutes." height={280}>
            <ScatterChart margin={{ top: 10, right: 20, bottom: 10, left: 0 }}>{grid}<XAxis type="number" dataKey="km" name="Distance" tickLine={false} axisLine={false} tickFormatter={(x) => fmt.dist(x)} /><YAxis type="number" dataKey="cpk" name={`Cost/${fmt.distUnit}`} tickLine={false} axisLine={false} width={56} tickFormatter={(x) => fmt.money2(x)} /><ZAxis type="number" dataKey="idle" range={[40, 400]} />{tip((v, n) => (n === "Distance" ? fmt.dist(v) : n.startsWith("Cost") ? fmt.perDist(v) : `${v}`))}<Scatter data={stats.filter((x) => x.distance > 50).map((x) => ({ km: Math.round(x.distance), cpk: +x.costPerKm.toFixed(3), idle: x.idleMin, name: x.vehicle.name }))} fill={C.blue} /></ScatterChart>
          </ChartCard>
        </TabsContent>

        <TabsContent value="drivers">
          <DataTable rows={drivers} rowKey={(x) => x.d.id} onRowClick={(x) => nav(`/drivers/${x.d.id}`)} exportName="driver-productivity" pageSize={15} dense initialSort={{ key: "km", dir: "desc" }}
            columns={[
              { key: "d", header: "Driver", cell: (x) => <span className="font-medium">{x.d.name}</span>, sortValue: (x) => x.d.name },
              { key: "km", header: "Distance", cell: (x) => fmt.dist(x.km), sortValue: (x) => x.km, align: "right" },
              { key: "trips", header: "Trips", cell: (x) => x.trips, sortValue: (x) => x.trips, align: "right" },
              { key: "drive", header: "Drive time", cell: (x) => fmt.duration(x.drive), sortValue: (x) => x.drive, align: "right" },
              { key: "prod", header: "Productive vs idle", cell: (x) => <div className="flex items-center gap-2"><Progress value={x.productive} className="w-24" tone={x.productive < 80 ? "warning" : "success"} /><span className="text-xs tabular">{Math.round(x.productive)}%</span></div>, sortValue: (x) => x.productive },
              { key: "util", header: "Utilization", cell: (x) => fmt.pct(x.util), sortValue: (x) => x.util, align: "right" },
              { key: "score", header: "Safety", cell: (x) => <Badge variant={scoreTone(x.score)}>{x.score}</Badge>, sortValue: (x) => x.score, align: "right" },
            ]} />
        </TabsContent>
      </Tabs>
    </>
  );
}

function Row({ name, sub, value, pct, tone, onClick }: { name: string; sub: string; value: string; pct: number; tone: "success" | "warning" | "destructive"; onClick: () => void }) {
  return (
    <button onClick={onClick} className="w-full text-left text-sm">
      <div className="flex items-center justify-between"><span className="font-medium">{name}</span><span className="tabular text-xs">{value}</span></div>
      <div className="flex items-center gap-2"><Progress value={pct} tone={tone} className="flex-1" /><span className="w-40 truncate text-right text-[11px] text-muted-foreground">{sub}</span></div>
    </button>
  );
}
