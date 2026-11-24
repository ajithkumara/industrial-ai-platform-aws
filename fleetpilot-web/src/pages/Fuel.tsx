import * as React from "react";
import { useNavigate } from "react-router-dom";
import { Fuel as FuelIcon, Droplets, Gauge, Coins, Timer, Upload, CreditCard } from "lucide-react";
import { Bar, BarChart, Line, ComposedChart, Cell } from "recharts";
import { PageHeader } from "@/components/shared/PageHeader";
import { KpiCard } from "@/components/shared/KpiCard";
import { DataTable, type Column } from "@/components/shared/DataTable";
import { ChartCard, C, grid, tip, xAxis, yAxis, Legend } from "@/components/shared/Charts";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { useFleet } from "@/store/FleetStore";
import { useToast } from "@/components/ui/toast";
import { allVehicleStats, fleetKpis, fuelIn, monthlyCosts, pctChange, sum, weeklySeries, median } from "@/lib/metrics";
import { DeviceLimitNotice } from "@/components/shared/DeviceLimitNotice";
import type { FuelTransaction } from "@/types";

export default function FuelPage() {
  const { s, fmt, range } = useFleet();
  const nav = useNavigate();
  const { toast } = useToast();
  const [importOpen, setImportOpen] = React.useState(false);
  const k = fleetKpis(s, range);
  const stats = allVehicleStats(s, range);
  const tx = fuelIn(s, range).sort((a, b) => b.date.localeCompare(a.date));
  const litres = sum(tx.map((t) => t.litres));
  const km = sum(stats.map((x) => x.distance));
  const l100 = km ? (litres / km) * 100 : 0;
  const idleL = sum(stats.map((x) => x.idleFuelL)), idleCost = sum(stats.map((x) => x.idleCost));
  const costPerKm = km ? sum(stats.map((x) => x.opCost)) / km : 0;
  const medEcon = median(stats.filter((x) => x.distance > 100).map((x) => x.l100));
  const unusual = stats.filter((x) => x.distance > 100 && x.l100 > medEcon * 1.2).sort((a, b) => b.l100 - a.l100);
  const vn = (id: string) => s.vehicles.find((v) => v.id === id)?.name ?? id;
  const dn = (id: string) => s.drivers.find((d) => d.id === id)?.name ?? id;
  const weekly = weeklySeries(s, 8), monthly = monthlyCosts(s, 6);
  const byVehicle = [...stats].sort((a, b) => b.opCost - a.opCost).map((x) => ({ name: x.vehicle.name.replace("Truck ", "T").replace("Van ", "V"), fuel: Math.round(x.fuelSpend), maintenance: Math.round(x.maintSpend), costPerKm: x.costPerKm, id: x.vehicle.id }));

  const cols: Column<FuelTransaction>[] = [
    { key: "date", header: "Date", cell: (f) => fmt.dateTime(f.date), sortValue: (f) => f.date, csv: (f) => f.date },
    { key: "v", header: "Vehicle", cell: (f) => <button className="font-medium hover:underline" onClick={(e) => { e.stopPropagation(); nav(`/vehicles/${f.vehicleId}`); }}>{vn(f.vehicleId)}</button>, sortValue: (f) => vn(f.vehicleId) },
    { key: "d", header: "Driver", cell: (f) => dn(f.driverId), sortValue: (f) => dn(f.driverId) },
    { key: "st", header: "Station", cell: (f) => <span className="text-xs">{f.station}</span>, sortValue: (f) => f.station },
    { key: "l", header: fmt.volUnit === "L" ? "Litres" : "Gallons", cell: (f) => fmt.vol(f.litres, 1), sortValue: (f) => f.litres, align: "right" },
    { key: "p", header: "Unit price", cell: (f) => fmt.money2(f.unitPrice), sortValue: (f) => f.unitPrice, align: "right" },
    { key: "t", header: "Total", cell: (f) => <span className="font-medium">{fmt.money2(f.totalCost)}</span>, sortValue: (f) => f.totalCost, align: "right" },
    { key: "o", header: "Odometer", cell: (f) => fmt.dist(f.odometerKm), sortValue: (f) => f.odometerKm, align: "right" },
    { key: "src", header: "Source", cell: (f) => <Badge variant="muted">{f.source === "fuel-card" ? "Fuel card (demo)" : f.source}</Badge>, sortValue: (f) => f.source },
  ];

  return (
    <>
      <PageHeader title="Fuel & Expenses" description="Purchased fuel comes from fuel-card transactions (demo). Consumption inside trips is estimated from distance and idle time and is labelled as such." actions={<><Button variant="outline" size="sm" onClick={() => setImportOpen(true)}><Upload className="h-4 w-4" />Import CSV</Button><Button variant="outline" size="sm" onClick={() => nav("/integrations")}><CreditCard className="h-4 w-4" />Connect fuel card</Button></>} />
      <DeviceLimitNotice>Your tracker does not measure fuel level or consumption, so no fuel figures are estimated here. Fuel purchases you record or import will appear in this ledger.</DeviceLimitNotice>
      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
        <KpiCard label="Fuel expenditure" value={fmt.money(k.fuelSpend)} change={pctChange(k.fuelSpend, k.fuelSpendPrev)} invert sub="vs prev." icon={Coins} />
        <KpiCard label="Fuel purchased" value={fmt.vol(litres)} sub={`${tx.length} transactions`} icon={Droplets} tone="info" />
        <KpiCard label="Fuel economy" value={fmt.economy(l100)} sub="purchased ÷ distance" icon={Gauge} tone={l100 > 15 ? "warning" : "success"} />
        <KpiCard label="Cost per distance" value={km ? fmt.perDist(costPerKm) : "—"} sub="fuel + maintenance" icon={FuelIcon} />
        <KpiCard label="Idle fuel (est.)" value={fmt.vol(idleL)} sub={`≈ ${fmt.money(idleCost)} · ${fmt.duration(k.idleMin)}`} icon={Timer} tone="warning" />
        <KpiCard label="Consumed (est.)" value={fmt.vol(k.fuelL)} change={pctChange(k.fuelL, k.fuelPrev)} invert sub="from trips" icon={Droplets} />
      </div>
      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <ChartCard title="Fuel expenditure trend" description="Weekly purchased fuel cost and estimated litres" actions={<Legend items={[{ color: C.navy, label: "Cost" }, { color: C.teal, label: "Litres (est.)" }]} />}>
          <ComposedChart data={weekly}>{grid}{xAxis("week")}{yAxis((x) => fmt.money(x), 56)}{tip((v, n) => (n === "Cost" ? fmt.money(v) : fmt.vol(v)))}<Bar dataKey="fuelCost" name="Cost" fill={C.navy} radius={[3, 3, 0, 0]} /><Line type="monotone" dataKey="fuelL" name="Litres (est.)" stroke={C.teal} strokeWidth={2} dot={false} /></ComposedChart>
        </ChartCard>
        <ChartCard title="Monthly expense trend" description="Fuel vs maintenance, last 6 months" actions={<Legend items={[{ color: C.teal, label: "Fuel" }, { color: C.navy, label: "Maintenance" }]} />}>
          <BarChart data={monthly}>{grid}{xAxis("month")}{yAxis((x) => fmt.money(x), 56)}{tip((v) => fmt.money(v))}<Bar dataKey="fuel" name="Fuel" stackId="a" fill={C.teal} /><Bar dataKey="maintenance" name="Maintenance" stackId="a" fill={C.navy} radius={[3, 3, 0, 0]} /></BarChart>
        </ChartCard>
      </div>
      <div className="mt-4 grid gap-4 lg:grid-cols-3">
        <ChartCard title="Operating cost by vehicle" description="Fuel + maintenance in period · click a bar to open the vehicle" className="lg:col-span-2" height={260}>
          <BarChart data={byVehicle} onClick={(e) => { const p = (e as { activePayload?: { payload: { id: string } }[] })?.activePayload?.[0]?.payload; if (p) nav(`/vehicles/${p.id}`); }}>{grid}{xAxis("name")}{yAxis((x) => fmt.money(x), 56)}{tip((v) => fmt.money(v))}<Bar dataKey="fuel" name="Fuel" stackId="a" fill={C.teal} /><Bar dataKey="maintenance" name="Maintenance" stackId="a" radius={[3, 3, 0, 0]}>{byVehicle.map((b, i) => <Cell key={i} fill={b.costPerKm > costPerKm * 1.3 ? C.red : C.navy} />)}</Bar></BarChart>
        </ChartCard>
        <Card><CardHeader className="pb-2"><CardTitle>Unusual fuel consumption</CardTitle><CardDescription>More than 20% above the fleet median of {fmt.economy(medEcon)}</CardDescription></CardHeader>
          <CardContent className="space-y-2 text-sm">{unusual.length === 0 && <div className="text-xs text-muted-foreground">No outliers in this period.</div>}{unusual.map((x) => <button key={x.vehicle.id} onClick={() => nav(`/vehicles/${x.vehicle.id}`)} className="flex w-full items-center justify-between rounded-md border p-2 text-left hover:bg-accent/40"><div><div className="font-medium">{x.vehicle.name}</div><div className="text-xs text-muted-foreground">{x.vehicle.year} {x.vehicle.make} {x.vehicle.model} · {fmt.duration(x.idleMin)} idle</div></div><Badge variant="warning">{fmt.economy(x.l100)}</Badge></button>)}</CardContent></Card>
      </div>
      <section className="mt-5"><h3 className="mb-2 text-sm font-semibold">Vehicle-level cost analysis</h3>
        <DataTable rows={[...stats].sort((a, b) => b.opCost - a.opCost)} rowKey={(x) => x.vehicle.id} onRowClick={(x) => nav(`/vehicles/${x.vehicle.id}`)} exportName="vehicle-costs" pageSize={15} dense
          columns={[
            { key: "v", header: "Vehicle", cell: (x) => <span className="font-medium">{x.vehicle.name}</span>, sortValue: (x) => x.vehicle.name },
            { key: "km", header: "Distance", cell: (x) => fmt.dist(x.distance), sortValue: (x) => x.distance, align: "right" },
            { key: "fuel", header: "Fuel cost", cell: (x) => fmt.money(x.fuelSpend), sortValue: (x) => x.fuelSpend, align: "right" },
            { key: "econ", header: "Economy", cell: (x) => fmt.economy(x.l100), sortValue: (x) => x.l100, align: "right" },
            { key: "maint", header: "Maintenance", cell: (x) => fmt.money(x.maintSpend), sortValue: (x) => x.maintSpend, align: "right" },
            { key: "op", header: "Operating cost", cell: (x) => <span className="font-medium">{fmt.money(x.opCost)}</span>, sortValue: (x) => x.opCost, align: "right" },
            { key: "cpk", header: `Cost / ${fmt.distUnit}`, cell: (x) => (x.distance ? fmt.perDist(x.costPerKm) : "—"), sortValue: (x) => x.costPerKm, align: "right" },
            { key: "idle", header: "Idle fuel", cell: (x) => <span className="text-muted-foreground">{fmt.vol(x.idleFuelL, 1)} · {fmt.money2(x.idleCost)}</span>, sortValue: (x) => x.idleCost, align: "right" },
          ]} />
      </section>
      <section className="mt-6"><h3 className="mb-2 text-sm font-semibold">Fuel transactions</h3><DataTable rows={tx} columns={cols} rowKey={(f) => f.id} exportName="fuel-transactions" pageSize={10} dense searchKeys={(f) => `${vn(f.vehicleId)} ${dn(f.driverId)} ${f.station}`} filters={[{ key: "v", label: "Vehicle", options: s.vehicles.filter((v) => !v.archived).map((v) => ({ value: v.id, label: v.name })), predicate: (f, v) => f.vehicleId === v }]} /></section>
      <Dialog open={importOpen} onOpenChange={setImportOpen}><DialogContent><DialogHeader><DialogTitle>Import fuel transactions</DialogTitle><DialogDescription>Upload a CSV from your fuel-card provider. Columns: date, vehicle (plate or ID), driver, station, litres, unit price, total, odometer.</DialogDescription></DialogHeader>
        <label className="flex cursor-pointer flex-col items-center justify-center rounded-lg border border-dashed p-8 text-sm text-muted-foreground hover:bg-accent/40"><Upload className="mb-2 h-5 w-5" />Choose a CSV file<input type="file" accept=".csv" className="hidden" onChange={(e) => { const f = e.target.files?.[0]; if (f) { toast({ title: "Import not connected", description: `${f.name} was read locally. CSV parsing into the ledger is a backend feature; the demo ledger is unchanged.`, tone: "info" }); setImportOpen(false); } }} /></label>
        <DialogFooter><Button variant="outline" onClick={() => setImportOpen(false)}>Close</Button></DialogFooter></DialogContent></Dialog>
    </>
  );
}
