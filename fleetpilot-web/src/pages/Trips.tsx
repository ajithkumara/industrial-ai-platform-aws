import * as React from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { Route } from "lucide-react";
import { PageHeader, Stat } from "@/components/shared/PageHeader";
import { DataTable, type Column } from "@/components/shared/DataTable";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { BaseMap, FitBounds, TripPath } from "@/components/map/FleetMap";
import { useFleet } from "@/store/FleetStore";
import { tripsIn, sum } from "@/lib/metrics";
import type { Trip } from "@/types";

export default function TripsPage() {
  const { s, fmt, range, fleetFilter } = useFleet();
  const nav = useNavigate();
  const [params] = useSearchParams();
  const vehicleParam = params.get("vehicle") ?? undefined;
  const trips = React.useMemo(() => tripsIn(s, range).filter((t) => (!vehicleParam || t.vehicleId === vehicleParam) && (fleetFilter === "all" || s.vehicles.find((v) => v.id === t.vehicleId)?.type === fleetFilter)).sort((a, b) => b.startTime.localeCompare(a.startTime)), [s, range, vehicleParam, fleetFilter]);
  const [hover, setHover] = React.useState<Trip | null>(null);
  const vn = (id: string) => s.vehicles.find((v) => v.id === id)?.name ?? id;
  const dn = (id: string) => s.drivers.find((d) => d.id === id)?.name ?? id;
  const preview = hover ?? trips[0];

  const columns: Column<Trip>[] = [
    { key: "id", header: "Trip", cell: (t) => <span className="font-mono text-xs text-muted-foreground">{t.id}</span>, sortValue: (t) => t.id },
    { key: "vehicle", header: "Vehicle", cell: (t) => <div><div className="font-medium">{vn(t.vehicleId)}</div><div className="text-xs text-muted-foreground">{dn(t.driverId)}</div></div>, sortValue: (t) => vn(t.vehicleId), csv: (t) => `${vn(t.vehicleId)} / ${dn(t.driverId)}` },
    { key: "from", header: "Start → destination", cell: (t) => <div className="text-xs"><div>{t.startLabel}</div><div className="text-muted-foreground">→ {t.endLabel}</div></div>, csv: (t) => `${t.startLabel} -> ${t.endLabel}` },
    { key: "start", header: "Start", cell: (t) => <div className="text-xs"><div>{fmt.shortDate(t.startTime)}</div><div className="text-muted-foreground">{fmt.time(t.startTime)}</div></div>, sortValue: (t) => t.startTime, csv: (t) => t.startTime },
    { key: "end", header: "End", cell: (t) => <span className="text-xs">{t.status === "in_progress" ? "—" : fmt.time(t.endTime)}</span>, sortValue: (t) => t.endTime, csv: (t) => t.endTime },
    { key: "dist", header: "Distance", cell: (t) => fmt.dist(t.distanceKm, 1), sortValue: (t) => t.distanceKm, align: "right" },
    { key: "dur", header: "Duration", cell: (t) => fmt.duration(t.durationMin), sortValue: (t) => t.durationMin, align: "right" },
    { key: "max", header: "Max", cell: (t) => <span className={t.maxSpeedKmh > s.settings.speedLimitKmh ? "font-medium text-red-600" : ""}>{fmt.speed(t.maxSpeedKmh)}</span>, sortValue: (t) => t.maxSpeedKmh, align: "right" },
    { key: "status", header: "Status", cell: (t) => (t.status === "in_progress" ? <Badge variant="success">In progress</Badge> : <Badge variant="muted">Completed</Badge>), sortValue: (t) => t.status },
  ];

  return (
    <>
      <PageHeader title="Trips & Routes" description={`${trips.length} trips · ${fmt.dist(sum(trips.map((t) => t.distanceKm)))} · ${fmt.duration(sum(trips.map((t) => t.durationMin)))} driving${vehicleParam ? ` · filtered to ${vn(vehicleParam)}` : ""}`} />
      <div className="mb-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Stat label="Trips" value={trips.length} sub={`${trips.filter((t) => t.status === "in_progress").length} in progress`} />
        <Stat label="Average trip" value={fmt.dist(trips.length ? sum(trips.map((t) => t.distanceKm)) / trips.length : 0, 1)} sub={fmt.duration(trips.length ? sum(trips.map((t) => t.durationMin)) / trips.length : 0)} />
        <Stat label="Idle inside trips" value={fmt.duration(sum(trips.map((t) => t.idleMin)))} sub={`${trips.length ? Math.round(sum(trips.map((t) => t.idleMin)) / Math.max(1, sum(trips.map((t) => t.durationMin))) * 100) : 0}% of trip time`} />
        <Stat label="Over speed limit" value={trips.filter((t) => t.maxSpeedKmh > s.settings.speedLimitKmh).length} sub={`trips above ${fmt.speed(s.settings.speedLimitKmh)}`} />
      </div>
      <div className="grid gap-4 xl:grid-cols-3">
        <div className="xl:col-span-2">
          <DataTable rows={trips} columns={columns} rowKey={(t) => t.id} onRowClick={(t) => nav(`/trips/${t.id}`)} exportName="trips" pageSize={12} dense
            searchKeys={(t) => `${t.id} ${vn(t.vehicleId)} ${dn(t.driverId)} ${t.startLabel} ${t.endLabel}`}
            filters={[
              { key: "vehicle", label: "Vehicle", options: s.vehicles.filter((v) => !v.archived).map((v) => ({ value: v.id, label: v.name })), predicate: (t, v) => t.vehicleId === v },
              { key: "driver", label: "Driver", options: s.drivers.map((d) => ({ value: d.id, label: d.name })), predicate: (t, v) => t.driverId === v },
              { key: "status", label: "Status", options: [{ value: "completed", label: "Completed" }, { value: "in_progress", label: "In progress" }], predicate: (t, v) => t.status === v },
            ]} />
          <p className="mt-2 text-xs text-muted-foreground">Hover a row to preview its route. Change the date range in the top bar to see other days.</p>
        </div>
        <Card className="overflow-hidden xl:sticky xl:top-20 h-[460px]" onMouseLeave={() => setHover(null)}>
          {preview ? (
            <div className="relative h-full" onMouseMove={undefined}>
              <BaseMap zoom={11} scrollWheel={false}><FitBounds points={preview.path} />{<TripPath trip={preview} />}</BaseMap>
              <div className="absolute bottom-3 left-3 right-3 z-[500] rounded-md border bg-card/95 p-3 text-xs shadow-card">
                <div className="font-medium">{vn(preview.vehicleId)} · {dn(preview.driverId)}</div>
                <div className="text-muted-foreground">{preview.startLabel.split(" — ")[0]} → {preview.endLabel.split(" — ")[0]} · {fmt.dist(preview.distanceKm, 1)} · {fmt.duration(preview.durationMin)}</div>
                <button onClick={() => nav(`/trips/${preview.id}`)} className="mt-1 font-medium text-secondary hover:underline">Open trip & replay →</button>
              </div>
            </div>
          ) : <div className="flex h-full items-center justify-center text-sm text-muted-foreground"><Route className="mr-2 h-4 w-4" />No trips in this period</div>}
        </Card>
      </div>
      <RowHover onHover={setHover} trips={trips} />
    </>
  );
}

/** Attaches hover listeners to table rows (keeps DataTable generic). */
function RowHover({ onHover, trips }: { onHover: (t: Trip | null) => void; trips: Trip[] }) {
  React.useEffect(() => {
    const handler = (e: Event) => {
      const tr = (e.target as HTMLElement).closest("tr");
      const id = tr?.querySelector("td span.font-mono")?.textContent;
      onHover(id ? trips.find((t) => t.id === id) ?? null : null);
    };
    document.addEventListener("mouseover", handler);
    return () => document.removeEventListener("mouseover", handler);
  }, [onHover, trips]);
  return null;
}
