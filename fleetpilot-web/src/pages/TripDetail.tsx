import * as React from "react";
import { useNavigate, useParams } from "react-router-dom";
import { ArrowLeft, Play, Pause, Square, Route, Flag, MapPin, AlertTriangle, Clock } from "lucide-react";
import { Area, AreaChart, ReferenceLine } from "recharts";
import { PageHeader, Stat, EmptyState } from "@/components/shared/PageHeader";
import { SeverityBadge } from "@/components/shared/StatusBadge";
import { ChartCard, C, grid, tip, xAxis, yAxis } from "@/components/shared/Charts";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { BaseMap, FitBounds, TripPath, GeofenceLayer } from "@/components/map/FleetMap";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useFleet } from "@/store/FleetStore";
import { cn } from "@/lib/utils";

/** Deterministic speed profile along the path (simulated: accelerates, cruises near max, slows at stops/end). */
function speedProfile(n: number, max: number, avg: number, seed: string) {
  let h = 0; for (const ch of seed) h = (h * 31 + ch.charCodeAt(0)) | 0;
  return Array.from({ length: n }, (_, i) => {
    const t = i / (n - 1);
    const env = Math.sin(Math.PI * t) ** 0.6;
    const wob = Math.sin(i * 1.7 + h) * 0.08 + Math.cos(i * 0.9 + h * 0.3) * 0.06;
    return Math.max(0, Math.round(Math.min(max, (avg * 1.25 + (max - avg * 1.25) * env) * (1 + wob) * (t < 0.04 || t > 0.96 ? 0.35 : 1))));
  });
}

export default function TripDetailPage() {
  const { id } = useParams();
  const { s, fmt } = useFleet();
  const nav = useNavigate();
  const t = s.trips.find((x) => x.id === id);
  const [progress, setProgress] = React.useState(0);
  const [playing, setPlaying] = React.useState(false);
  const [rate, setRate] = React.useState("10");
  React.useEffect(() => {
    if (!playing) return;
    const h = setInterval(() => setProgress((p) => { if (p >= 1) { setPlaying(false); return 1; } return Math.min(1, p + 0.004 * Number(rate)); }), 60);
    return () => clearInterval(h);
  }, [playing, rate]);
  // hook must run before the early return so hook order is stable when live trips arrive after first render
  const speeds = React.useMemo(() => (t ? t.speeds ?? speedProfile(t.path.length, t.maxSpeedKmh, t.avgSpeedKmh, t.id) : []), [t]);
  if (!t) return <EmptyState icon={Route} title="Trip not found" action={<Button onClick={() => nav("/trips")}>Back to trips</Button>} />;

  const v = s.vehicles.find((x) => x.id === t.vehicleId)!;
  const d = s.drivers.find((x) => x.id === t.driverId); // live-tracker trips have no driver
  const events = s.safety.filter((e) => e.tripId === t.id).sort((a, b) => a.time.localeCompare(b.time));
  const idx = Math.round(progress * (t.path.length - 1));
  const recorded = !!t.speeds;
  const curTime = t.times?.[idx] ?? new Date(new Date(t.startTime).getTime() + progress * t.durationMin * 60000).toISOString();
  const timeline = [
    { time: t.startTime, icon: Flag, label: `Departed ${t.startLabel}`, tone: "success" },
    ...t.stops.map((st) => ({ time: st.arrival, icon: MapPin, label: `Stop at ${st.label} · ${st.durationMin} min`, tone: "warning" })),
    ...events.map((e) => ({ time: e.time, icon: AlertTriangle, label: `${e.type.replace("_", " ")}${e.type === "speeding" ? ` +${e.value} km/h` : ""} · ${e.locationLabel}`, tone: e.severity === "high" || e.severity === "critical" ? "destructive" : "warning" })),
    { time: t.endTime, icon: Flag, label: t.status === "in_progress" ? "Trip in progress" : `Arrived ${t.endLabel}`, tone: t.status === "in_progress" ? "info" : "destructive" },
  ].sort((a, b) => a.time.localeCompare(b.time));

  return (
    <>
      <Button variant="ghost" size="sm" className="-ml-2 mb-2" onClick={() => nav(-1)}><ArrowLeft className="h-4 w-4" />Back</Button>
      <PageHeader title={`${t.startLabel.split(" — ")[0]} → ${t.endLabel.split(" — ")[0]}`} description={`${t.id} · ${fmt.date(t.startTime)} · ${v.name} (${v.registration}) · ${d?.name ?? "No driver assigned"}`}
        actions={<>{t.status === "in_progress" && <Badge variant="success">In progress</Badge>}<Button variant="outline" size="sm" onClick={() => nav(`/vehicles/${v.id}`)}>Vehicle</Button>{d && <Button variant="outline" size="sm" onClick={() => nav(`/drivers/${d.id}`)}>Driver</Button>}</>} />

      <div className="grid gap-3 sm:grid-cols-3 lg:grid-cols-6">
        <Stat label="Distance" value={fmt.dist(t.distanceKm, 1)} />
        <Stat label="Duration" value={fmt.duration(t.durationMin)} sub={`${fmt.time(t.startTime)} – ${t.status === "in_progress" ? "now" : fmt.time(t.endTime)}`} />
        <Stat label="Average speed" value={fmt.speed(t.avgSpeedKmh)} />
        <Stat label="Max speed" value={<span className={t.maxSpeedKmh > s.settings.speedLimitKmh ? "text-red-600" : ""}>{fmt.speed(t.maxSpeedKmh)}</span>} sub={t.maxSpeedKmh > s.settings.speedLimitKmh ? `above ${fmt.speed(s.settings.speedLimitKmh)} limit` : "within limit"} />
        {recorded ? <>
          <Stat label="Points recorded" value={String(t.path.length)} sub="GPS fixes from the tracker" />
          <Stat label="Fuel" value="n/a" sub="not available with this device" />
        </> : <>
        <Stat label="Idle" value={`${t.idleMin} min`} sub={`≈ ${fmt.money2((t.idleMin / 60) * s.settings.idleFuelLPerHour * s.settings.fuelPricePerL)} fuel`} />
        <Stat label="Fuel (est.)" value={fmt.vol(t.fuelL, 1)} sub={fmt.money2(t.fuelL * s.settings.fuelPricePerL)} /></>}
      </div>

      <div className="mt-4 grid gap-4 xl:grid-cols-3">
        <Card className="overflow-hidden xl:col-span-2">
          <div className="h-[440px]"><BaseMap zoom={12}><FitBounds points={t.path} /><GeofenceLayer geofences={s.geofences} labels={false} /><TripPath trip={t} progress={progress} /></BaseMap></div>
          <div className="flex flex-wrap items-center gap-3 border-t p-3">
            <div className="flex items-center gap-1">
              <Button size="iconSm" variant={playing ? "outline" : "default"} onClick={() => { if (progress >= 1) setProgress(0); setPlaying((p) => !p); }} aria-label={playing ? "Pause" : "Play"}>{playing ? <Pause className="h-4 w-4" /> : <Play className="h-4 w-4" />}</Button>
              <Button size="iconSm" variant="outline" onClick={() => { setPlaying(false); setProgress(0); }} aria-label="Stop"><Square className="h-3.5 w-3.5" /></Button>
            </div>
            <input type="range" min={0} max={1000} value={Math.round(progress * 1000)} onChange={(e) => setProgress(Number(e.target.value) / 1000)} className="h-1.5 flex-1 cursor-pointer accent-blue-600" aria-label="Replay position" />
            <Select value={rate} onValueChange={setRate}><SelectTrigger className="h-8 w-20"><SelectValue /></SelectTrigger><SelectContent>{["1", "5", "10", "30"].map((r) => <SelectItem key={r} value={r}>{r}×</SelectItem>)}</SelectContent></Select>
            <div className="w-40 text-right text-xs tabular text-muted-foreground"><Clock className="mr-1 inline h-3 w-3" />{fmt.time(curTime)} · {fmt.speed(speeds[idx] ?? 0)}</div>
          </div>
        </Card>
        <Card>
          <CardHeader className="pb-2"><CardTitle>Timeline</CardTitle></CardHeader>
          <CardContent>
            <ol className="relative ml-2 border-l pl-5 text-sm">
              {timeline.map((e, i) => (
                <li key={i} className="mb-4 last:mb-0">
                  <span className={cn("absolute -left-[9px] mt-0.5 flex h-4 w-4 items-center justify-center rounded-full border-2 border-card", { success: "bg-emerald-500", warning: "bg-amber-500", destructive: "bg-red-500", info: "bg-blue-500" }[e.tone])} />
                  <div className="text-xs tabular text-muted-foreground">{fmt.time(e.time)}</div>
                  <div className="flex items-start gap-1.5"><e.icon className="mt-0.5 h-3.5 w-3.5 shrink-0 text-muted-foreground" /><span>{e.label}</span></div>
                </li>
              ))}
            </ol>
          </CardContent>
        </Card>
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-3">
        <ChartCard title="Speed along the route" description={recorded ? "Speed reported by the tracker at each GPS fix · red line = configured speed limit" : "Simulated profile between recorded points · red line = configured speed limit"} className="lg:col-span-2" height={200}>
          <AreaChart data={speeds.map((sp, i) => ({ i, pct: Math.round((i / (speeds.length - 1)) * 100), speed: sp }))}>
            <defs><linearGradient id="spd" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor={C.blue} stopOpacity={0.3} /><stop offset="100%" stopColor={C.blue} stopOpacity={0} /></linearGradient></defs>
            {grid}{xAxis("pct")}{yAxis((x) => `${x}`, 32)}{tip((val) => fmt.speed(val))}
            <ReferenceLine y={s.settings.speedLimitKmh} stroke={C.red} strokeDasharray="4 3" />
            <ReferenceLine x={Math.round(progress * 100)} stroke={C.navy} />
            <Area type="monotone" dataKey="speed" name="Speed" stroke={C.blue} strokeWidth={2} fill="url(#spd)" />
          </AreaChart>
        </ChartCard>
        <Card>
          <CardHeader className="pb-2"><CardTitle>Safety events on this trip</CardTitle></CardHeader>
          <CardContent className="space-y-2 text-sm">
            {events.length === 0 && <div className="text-xs text-muted-foreground">No events recorded.</div>}
            {events.map((e) => <div key={e.id} className="flex items-center justify-between rounded-md border p-2"><div><div className="capitalize">{e.type.replace("_", " ")}</div><div className="text-xs text-muted-foreground">{fmt.time(e.time)} · {e.locationLabel}</div></div><SeverityBadge severity={e.severity} /></div>)}
            <Button variant="link" size="sm" className="h-auto p-0" onClick={() => nav("/safety")}>Open safety centre →</Button>
          </CardContent>
        </Card>
      </div>
      <p className="mt-3 text-xs text-muted-foreground">{recorded ? "Route lines connect the recorded GPS fixes in straight lines and are not road-matched." : "Route lines are simulated between recorded points and are not road-matched. Demo data."}</p>
    </>
  );
}
