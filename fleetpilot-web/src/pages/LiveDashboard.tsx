import * as React from "react";
import { useNavigate } from "react-router-dom";
import { Bar, BarChart } from "recharts";
import { Truck, Activity, ParkingCircle, WifiOff, Route, Timer, AlertTriangle, Clock, Power, MapPin, Info } from "lucide-react";
import { KpiCard } from "@/components/shared/KpiCard";
import { PageHeader } from "@/components/shared/PageHeader";
import { ChartCard, C, grid, tip, xAxis, yAxis } from "@/components/shared/Charts";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { VehicleStatusBadge, FRESHNESS_META } from "@/components/shared/StatusBadge";
import { useFleet } from "@/store/FleetStore";
import { dailySeries, sum, tripsIn } from "@/lib/metrics";
import { alarmLabel } from "@/lib/alarms";
import type { Freshness } from "@/types";

/**
 * Dashboard for a real account. Every number here is computed from the account's own tracker data
 * (vehicles, positions, trips). Figures the current hardware cannot measure (fuel, engine faults,
 * harsh driving) are not estimated; the "What your devices report" card says so explicitly.
 */
export default function LiveDashboard() {
  const { s, range, fmt, liveStatus } = useFleet();
  const nav = useNavigate();
  const vehicles = s.vehicles.filter((v) => !v.archived);
  const trips = React.useMemo(() => tripsIn(s, range), [s, range]);
  const daily = React.useMemo(() => dailySeries(s, range), [s, range]);
  const by = (f: Freshness) => vehicles.filter((v) => v.freshness === f).length;
  const current = vehicles.filter((v) => v.freshness === "live" || v.freshness === "delayed");
  const moving = current.filter((v) => v.status === "moving").length;
  const parked = current.filter((v) => v.status === "stopped" || v.status === "idle").length;
  const notReporting = by("stale") + by("offline") + by("error");
  const withAlarms = vehicles.filter((v) => (v.alarms ?? []).length > 0);
  const km = sum(trips.map((t) => t.distanceKm));
  const driveMin = sum(trips.map((t) => t.durationMin));
  const recent = [...s.trips].sort((a, b) => b.startTime.localeCompare(a.startTime)).slice(0, 8);
  const vn = (id: string) => s.vehicles.find((v) => v.id === id)?.name ?? id;

  if (vehicles.length === 0) {
    return (
      <>
        <PageHeader title="Dashboard" />
        <Card><CardContent className="p-8 text-center text-sm text-muted-foreground">
          {liveStatus === "error" ? "Could not reach the FleetPilot service. Retrying every 15 seconds." : "No vehicles are linked to your account yet. Once a tracker is registered, it appears here within a minute of its first report."}
        </CardContent></Card>
      </>
    );
  }

  return (
    <>
      <PageHeader title="Dashboard" description={`${fmt.shortDate(range.from)} – ${fmt.shortDate(range.to)} · your own tracker data`} />

      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
        <KpiCard label="Vehicles" value={String(vehicles.length)} sub={`${current.length} reporting now`} icon={Truck} onClick={() => nav("/vehicles")} />
        <KpiCard label="Moving" value={String(moving)} sub="right now" icon={Activity} tone="success" onClick={() => nav("/map")} />
        <KpiCard label="Parked" value={String(parked)} sub="reporting, not moving" icon={ParkingCircle} onClick={() => nav("/map")} />
        <KpiCard label="Not reporting" value={String(notReporting)} sub={notReporting ? "stale, offline or device error" : "all devices reporting"} icon={WifiOff} tone={notReporting ? "destructive" : "default"} onClick={() => nav("/vehicles")} />
        <KpiCard label="Distance" value={fmt.dist(km)} sub={`${trips.length} trip${trips.length === 1 ? "" : "s"} in period`} icon={Route} tone="info" spark={daily.map((d) => d.distance)} onClick={() => nav("/trips")} />
        <KpiCard label="Driving time" value={fmt.duration(driveMin)} sub="ignition-on time" icon={Timer} onClick={() => nav("/trips")} />
      </div>

      <div className="mt-4 grid gap-4 xl:grid-cols-3">
        <Card className="xl:col-span-2">
          <CardHeader className="pb-2"><CardTitle>Vehicles now</CardTitle><CardDescription>Status and the time of each device’s last message</CardDescription></CardHeader>
          <CardContent className="divide-y p-0">
            {vehicles.map((v) => (
              <button key={v.id} onClick={() => nav(`/vehicles/${v.id}`)} className="flex w-full items-center gap-3 px-6 py-2.5 text-left text-sm hover:bg-accent/40">
                <span className="w-40 truncate font-medium">{v.name}</span>
                <VehicleStatusBadge status={v.status} freshness={v.freshness} />
                <span className="flex-1 truncate text-xs text-muted-foreground">{v.speedKmh > 3 && v.freshness === "live" ? fmt.speed(v.speedKmh) : ""}{(v.alarms ?? []).length > 0 && <span className="ml-2 text-red-600">{v.alarms!.map(alarmLabel).join(", ")}</span>}</span>
                <span className="text-xs text-muted-foreground"><Clock className="mr-1 inline h-3 w-3" />{v.lastContact ? fmt.relative(v.lastContact) : "never"}</span>
              </button>
            ))}
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="pb-2"><CardTitle>Data freshness</CardTitle><CardDescription>Is each tracker reporting on schedule?</CardDescription></CardHeader>
          <CardContent className="space-y-2 text-sm">
            {(Object.keys(FRESHNESS_META) as Freshness[]).map((f) => (
              <div key={f} className="flex items-center justify-between" title={FRESHNESS_META[f].hint}>
                <span>{FRESHNESS_META[f].label}</span><span className="tabular font-medium">{by(f)}</span>
              </div>
            ))}
            {withAlarms.length > 0 && <div className="mt-2 flex items-start gap-2 rounded-md border border-red-200 bg-red-50 p-2 text-xs text-red-700"><AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />{withAlarms.length} vehicle{withAlarms.length === 1 ? "" : "s"} reporting device alarms.</div>}
            <Button variant="outline" size="sm" className="mt-2 w-full" onClick={() => nav("/map")}>Open live map</Button>
          </CardContent>
        </Card>
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <ChartCard title="Distance per day" description="From recorded trips">
          <BarChart data={daily}>{grid}{xAxis("date")}{yAxis(undefined, 36)}{tip((v) => fmt.dist(v))}<Bar dataKey="distance" name="Distance" fill={C.blue} radius={[3, 3, 0, 0]} /></BarChart>
        </ChartCard>
        <Card>
          <CardHeader className="pb-2"><CardTitle>Recent trips</CardTitle></CardHeader>
          <CardContent className="divide-y p-0">
            {recent.length === 0 && <div className="px-6 py-4 text-sm text-muted-foreground">No trips recorded yet.</div>}
            {recent.map((t) => (
              <button key={t.id} onClick={() => nav(`/trips/${t.id}`)} className="flex w-full items-center gap-3 px-6 py-2 text-left text-sm hover:bg-accent/40">
                <Power className="h-4 w-4 text-muted-foreground" />
                <span className="w-20 shrink-0 text-xs tabular text-muted-foreground">{fmt.shortDate(t.startTime)} {fmt.time(t.startTime)}</span>
                <span className="w-32 truncate font-medium">{vn(t.vehicleId)}</span>
                <span className="flex-1 truncate text-xs text-muted-foreground"><MapPin className="mr-1 inline h-3 w-3" />{fmt.dist(t.distanceKm, 1)} · {fmt.duration(t.durationMin)}</span>
              </button>
            ))}
          </CardContent>
        </Card>
      </div>

      <Card className="mt-4">
        <CardHeader className="pb-2"><CardTitle className="flex items-center gap-2"><Info className="h-4 w-4" />What your devices report</CardTitle></CardHeader>
        <CardContent className="text-sm text-muted-foreground">
          Your trackers (Mictrack MP91) report position, speed, ignition, distance travelled since install, tracker battery and device alarms. They do not report fuel level, engine fault codes, engine temperature or harsh braking, so the Fuel, Vehicle Health and Driver Safety pages show those as not available instead of estimating them.
        </CardContent>
      </Card>
    </>
  );
}
