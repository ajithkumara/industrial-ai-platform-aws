import * as React from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { Search, Gauge, Fuel, BatteryMedium, Route, Wrench, MapPin, User, X, Hexagon, Navigation, Clock, PanelLeftClose, PanelLeftOpen } from "lucide-react";
import { BaseMap, BasemapToggle, FlyTo, GeofenceLayer, Marker, Popup, TripPath, vehicleIcon, type Basemap } from "@/components/map/FleetMap";
import { VehicleStatusBadge, STATUS_META, DemoTag, FRESHNESS_META } from "@/components/shared/StatusBadge";
import { isDemo } from "@/services/mode";
import { alarmLabel } from "@/lib/alarms";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Avatar, Progress } from "@/components/ui/misc";
import { Switch } from "@/components/ui/switch";
import { useFleet } from "@/store/FleetStore";
import { useLivePolling } from "@/hooks/useLivePolling";
import { currentTrip, todayDistanceFor } from "@/lib/metrics";
import { PLACES } from "@/data/geo";
import { cn } from "@/lib/utils";
import type { LatLng, Vehicle, VehicleStatus } from "@/types";
import { GeofenceDialog } from "@/components/forms/GeofenceForm";

export default function LiveMapPage() {
  const { s, fmt, fleetFilter } = useFleet();
  const nav = useNavigate();
  const [params, setParams] = useSearchParams();
  const [q, setQ] = React.useState("");
  const [statusF, setStatusF] = React.useState<VehicleStatus | "all">("all");
  const [basemap, setBasemap] = React.useState<Basemap>("street");
  const [showGeo, setShowGeo] = React.useState(true);
  const [panel, setPanel] = React.useState(true);
  const [flyTarget, setFlyTarget] = React.useState<LatLng | null>(null);
  const [locQ, setLocQ] = React.useState("");
  const [geoOpen, setGeoOpen] = React.useState(false);
  const selectedId = params.get("vehicle");
  const liveNow = useLivePolling(true);

  const vehicles = React.useMemo(() => s.vehicles.filter((v) => !v.archived && (fleetFilter === "all" || v.type === fleetFilter)), [s.vehicles, fleetFilter]);
  const list = React.useMemo(() => {
    const n = q.toLowerCase();
    return vehicles.filter((v) => (statusF === "all" || v.status === statusF) && (!n || `${v.name} ${v.registration} ${s.drivers.find((d) => d.id === v.driverId)?.name ?? ""}`.toLowerCase().includes(n)))
      .sort((a, b) => ["moving", "idle", "stopped", "offline"].indexOf(a.status) - ["moving", "idle", "stopped", "offline"].indexOf(b.status) || a.name.localeCompare(b.name));
  }, [vehicles, q, statusF, s.drivers]);
  const selected = vehicles.find((v) => v.id === selectedId);
  const counts = vehicles.reduce((acc, v) => ((acc[v.status] = (acc[v.status] ?? 0) + 1), acc), {} as Record<string, number>);

  const select = (v: Vehicle | null) => {
    if (v) { setParams({ vehicle: v.id }); setFlyTarget({ ...v.position }); } else setParams({});
  };
  React.useEffect(() => { if (selected && !flyTarget) setFlyTarget({ ...selected.position }); }, []); // eslint-disable-line react-hooks/exhaustive-deps
  // follow a live (real tracker) vehicle that is moving
  React.useEffect(() => {
    if (selected && selected.id.startsWith("LV-") && selected.speedKmh > 3) setFlyTarget({ ...selected.position });
  }, [selected?.position.lat, selected?.position.lng]); // eslint-disable-line react-hooks/exhaustive-deps

  const locResults = locQ.length >= 2 ? PLACES.filter((p) => p.name.toLowerCase().includes(locQ.toLowerCase())).slice(0, 5) : [];
  const driver = selected ? s.drivers.find((d) => d.id === selected.driverId) : undefined;
  const trip = selected ? currentTrip(s, selected.id) : undefined;
  const lastMaint = selected ? s.maintenance.filter((m) => m.vehicleId === selected.id && m.status === "completed").sort((a, b) => b.date.localeCompare(a.date))[0] : undefined;

  return (
    <div className="-mx-4 -my-5 flex h-[calc(100vh-3.5rem)] sm:-mx-6 md:h-[calc(100vh-3.5rem)]">
      {/* Vehicle list panel */}
      <aside className={cn("flex w-80 shrink-0 flex-col border-r bg-card transition-all", !panel && "w-0 overflow-hidden border-0", "max-md:absolute max-md:inset-y-0 max-md:left-0 max-md:z-[600] max-md:shadow-pop")}>
        <div className="border-b p-3">
          <div className="mb-2 flex items-center justify-between"><div className="flex items-center gap-2 text-sm font-semibold">Vehicles <Badge variant="muted">{list.length}</Badge>{liveNow && <Badge variant="success">Live · 2 s</Badge>}</div><DemoTag /></div>
          <div className="relative"><Search className="pointer-events-none absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" /><Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Vehicle, plate or driver" className="pl-8" /></div>
          <div className="mt-2 flex flex-wrap gap-1">
            {(["all", "moving", "idle", "stopped", "offline"] as const).map((st) => (
              <button key={st} onClick={() => setStatusF(st)} className={cn("flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-medium", statusF === st ? "border-primary bg-primary text-primary-foreground" : "hover:bg-accent")}>
                {st !== "all" && <span className="h-1.5 w-1.5 rounded-full" style={{ background: STATUS_META[st].color }} />}
                {st === "all" ? "All" : STATUS_META[st].label} <span className="opacity-60">{st === "all" ? vehicles.length : counts[st] ?? 0}</span>
              </button>
            ))}
          </div>
        </div>
        <div className="flex-1 overflow-y-auto">
          {list.map((v) => {
            const d = s.drivers.find((x) => x.id === v.driverId);
            return (
              <button key={v.id} onClick={() => select(v)} className={cn("flex w-full items-start gap-3 border-b px-3 py-2.5 text-left hover:bg-accent/50", selectedId === v.id && "bg-accent")}>
                <span className="mt-1.5 h-2.5 w-2.5 shrink-0 rounded-full" style={{ background: STATUS_META[v.status].color }} />
                <div className="min-w-0 flex-1">
                  <div className="flex items-center justify-between gap-2"><span className="truncate text-sm font-medium">{v.name}</span><span className="text-xs tabular text-muted-foreground">{v.status === "moving" ? fmt.speed(v.speedKmh) : STATUS_META[v.status].label}</span></div>
                  <div className="truncate text-xs text-muted-foreground">{v.registration} · {d?.name ?? "Unassigned"}</div>
                  <div className="text-[11px] text-muted-foreground">Updated {fmt.relative(v.lastUpdate)}</div>
                </div>
              </button>
            );
          })}
          {list.length === 0 && <div className="p-6 text-center text-xs text-muted-foreground">No vehicles match.</div>}
        </div>
        <div className="flex items-center justify-between border-t px-3 py-2 text-xs"><span className="flex items-center gap-2"><Switch checked={showGeo} onCheckedChange={setShowGeo} /> Show geofences</span><span className="text-muted-foreground">{s.geofences.length} zones</span></div>
      </aside>

      {/* Map */}
      <div className="relative min-w-0 flex-1">
        <BaseMap basemap={basemap}>
          <FlyTo target={flyTarget} />
          {showGeo && <GeofenceLayer geofences={s.geofences} onClick={(g) => nav(`/geofences?focus=${g.id}`)} />}
          {trip && <TripPath trip={trip} showEnds={false} />}
          {vehicles.map((v) => (
            <Marker key={v.id} position={[v.position.lat, v.position.lng]} icon={vehicleIcon(v, v.id === selectedId)} eventHandlers={{ click: () => select(v) }} zIndexOffset={v.id === selectedId ? 1000 : 0}>
              <Popup>
                <div className="min-w-[180px]">
                  <div className="flex items-center justify-between gap-2"><strong>{v.name}</strong><VehicleStatusBadge status={v.status} freshness={v.freshness} /></div>
                  <div className="mt-1 text-muted-foreground">{v.registration} · {s.drivers.find((d) => d.id === v.driverId)?.name ?? "Unassigned"}</div>
                  <div className="mt-1">{fmt.speed(v.speedKmh)} · updated {fmt.relative(v.lastContact ?? v.lastUpdate)}</div>
                </div>
              </Popup>
            </Marker>
          ))}
        </BaseMap>
        <BasemapToggle value={basemap} onChange={setBasemap} />
        <button onClick={() => setPanel((p) => !p)} className="absolute left-3 top-3 z-[500] rounded-md border bg-card p-2 shadow-card hover:bg-accent" aria-label="Toggle vehicle list">{panel ? <PanelLeftClose className="h-4 w-4" /> : <PanelLeftOpen className="h-4 w-4" />}</button>
        <div className="absolute left-14 top-3 z-[500] w-64">
          <div className="relative"><MapPin className="pointer-events-none absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" /><Input value={locQ} onChange={(e) => setLocQ(e.target.value)} placeholder="Search a location…" className="bg-card pl-8 shadow-card" /></div>
          {locResults.length > 0 && (
            <div className="mt-1 overflow-hidden rounded-md border bg-card shadow-pop">
              {locResults.map((p) => <button key={p.name} onClick={() => { setFlyTarget({ ...p.pos }); setLocQ(""); }} className="block w-full px-3 py-2 text-left text-xs hover:bg-accent">{p.name}</button>)}
            </div>
          )}
        </div>
        <div className="absolute bottom-6 left-3 z-[500] rounded-md border bg-card/95 px-3 py-2 text-[11px] shadow-card">
          <div className="mb-1 font-semibold">Vehicle status</div>
          <div className="flex gap-3">{(Object.keys(STATUS_META) as VehicleStatus[]).map((k) => <span key={k} className="flex items-center gap-1"><span className="h-2 w-2 rounded-full" style={{ background: STATUS_META[k].color }} />{STATUS_META[k].label}</span>)}</div>
          {isDemo() && <div className="mt-1 text-amber-700">Simulated positions · demo data</div>}
        </div>

        {/* Detail panel */}
        {selected && (
          <div className="absolute inset-y-3 right-3 z-[600] flex w-[340px] max-w-[calc(100%-1.5rem)] flex-col overflow-hidden rounded-lg border bg-card shadow-pop animate-in slide-in-from-right-4 fade-in-0">
            <div className="flex items-start justify-between border-b p-4">
              <div>
                <div className="flex items-center gap-2"><h3 className="text-base font-semibold">{selected.name}</h3><VehicleStatusBadge status={selected.status} freshness={selected.freshness} /></div>
                <div className="text-xs text-muted-foreground">{selected.registration} · {selected.year} {selected.make} {selected.model}</div>
              </div>
              <button onClick={() => select(null)} className="rounded p-1 text-muted-foreground hover:bg-accent"><X className="h-4 w-4" /></button>
            </div>
            <div className="flex-1 space-y-4 overflow-y-auto p-4 text-sm">
              <div className="flex items-center gap-3 rounded-md border p-2.5">
                <Avatar name={driver?.name ?? "Unassigned"} />
                <div className="min-w-0 flex-1"><div className="truncate font-medium">{driver?.name ?? "No driver assigned"}</div><div className="text-xs text-muted-foreground">{driver ? `${driver.employeeId} · ${driver.phone}` : "Assign from the vehicle page"}</div></div>
                {driver && <Button variant="ghost" size="iconSm" onClick={() => nav(`/drivers/${driver.id}`)}><User className="h-4 w-4" /></Button>}
              </div>
              <div className="grid grid-cols-2 gap-2">
                <Tile icon={Gauge} label="Speed" value={fmt.speed(selected.speedKmh)} />
                <Tile icon={Route} label="Today" value={fmt.dist(todayDistanceFor(s, selected.id), 1)} />
                <Tile icon={Fuel} label="Fuel level" value={selected.fuelLevelPct !== undefined ? `${selected.fuelLevelPct}%` : "n/a"} sub={selected.fuelLevelPct === undefined ? (selected.device.source === "obd" ? "not available with this device" : "not reported by vehicle") : undefined}>{selected.fuelLevelPct !== undefined && <Progress value={selected.fuelLevelPct} tone={selected.fuelLevelPct < 20 ? "destructive" : "secondary"} className="mt-1.5" />}</Tile>
                {selected.device.source === "obd"
                  ? <Tile icon={BatteryMedium} label="Tracker battery" value={selected.batteryPct != null ? `${selected.batteryPct}%` : "n/a"} sub={selected.batteryPct == null ? "not reported yet" : selected.alarms?.includes("vehicle_battery_low") ? "vehicle battery low" : "device backup battery"} />
                  : <Tile icon={BatteryMedium} label="Battery" value={selected.batteryV ? `${selected.batteryV.toFixed(1)} V` : "n/a"} sub={selected.batteryV && selected.batteryV < 12.2 ? "low" : undefined} />}
              </div>
              <div>
                <div className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">Current location</div>
                <div className="flex items-start gap-2"><Navigation className="mt-0.5 h-4 w-4 text-muted-foreground" /><div><div>{nearestPlace(selected.position)}</div><div className="text-xs tabular text-muted-foreground">{selected.position.lat.toFixed(5)}, {selected.position.lng.toFixed(5)} · heading {selected.heading}°</div><div className="text-xs text-muted-foreground">Position from {fmt.relative(selected.lastUpdate)} · {fmt.time(selected.lastUpdate)}</div>{selected.lastContact && selected.lastContact !== selected.lastUpdate && <div className="text-xs text-muted-foreground">Last message from device {fmt.relative(selected.lastContact)}</div>}{selected.freshness && selected.freshness !== "live" && <div className="mt-1 text-xs font-medium text-amber-700">{FRESHNESS_META[selected.freshness].hint}. The position shown may not be where the vehicle is now.</div>}{selected.alarms && selected.alarms.length > 0 && <div className="mt-1 text-xs font-medium text-red-600">Device alarms: {selected.alarms.map(alarmLabel).join(", ")}</div>}</div></div>
              </div>
              <div>
                <div className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">Current trip</div>
                {trip ? (
                  <button onClick={() => nav(`/trips/${trip.id}`)} className="w-full rounded-md border p-2.5 text-left hover:bg-accent/40">
                    <div className="font-medium">{trip.startLabel.split(" — ")[0]} → {trip.endLabel.split(" — ")[0]}</div>
                    <div className="text-xs text-muted-foreground"><Clock className="mr-1 inline h-3 w-3" />Started {fmt.time(trip.startTime)} · {fmt.duration(trip.durationMin)} so far</div>
                  </button>
                ) : <div className="text-xs text-muted-foreground">No trip in progress.</div>}
              </div>
              {selected.device.source !== "obd" && <div className="flex items-start gap-2 text-xs"><Wrench className="mt-0.5 h-4 w-4 text-muted-foreground" /><div>Last maintenance: <span className="font-medium">{lastMaint ? `${lastMaint.type} · ${fmt.date(lastMaint.date)}` : "—"}</span><div className="text-muted-foreground">Next service at {fmt.dist(selected.nextServiceKm)} ({fmt.dist(selected.nextServiceKm - selected.odometerKm)} {selected.nextServiceKm < selected.odometerKm ? "overdue" : "remaining"})</div></div></div>}
              {selected.device.source === "obd" && <div className="flex items-start gap-2 text-xs"><Wrench className="mt-0.5 h-4 w-4 text-muted-foreground" /><div>Tracker distance: <span className="font-medium">{selected.odometerSource === "device" ? fmt.dist(selected.odometerKm) : "not reported by this device"}</span><div className="text-muted-foreground">Counted since the tracker was installed (not the vehicle odometer).</div></div></div>}
            </div>
            <div className="grid grid-cols-2 gap-2 border-t p-3">
              <Button size="sm" onClick={() => nav(`/vehicles/${selected.id}`)}>View vehicle</Button>
              <Button size="sm" variant="outline" onClick={() => nav(`/trips?vehicle=${selected.id}`)}>Trip history</Button>
              <Button size="sm" variant="outline" disabled={!driver} onClick={() => driver && nav(`/drivers/${driver.id}`)}>View driver</Button>
              <Button size="sm" variant="outline" onClick={() => setGeoOpen(true)}><Hexagon className="h-3.5 w-3.5" />Geofence here</Button>
            </div>
          </div>
        )}
      </div>
      {selected && <GeofenceDialog open={geoOpen} onOpenChange={setGeoOpen} initial={{ center: selected.position, name: `${nearestPlace(selected.position)} site` }} />}
    </div>
  );
}

function Tile({ icon: Icon, label, value, sub, children }: { icon: React.ComponentType<{ className?: string }>; label: string; value: string; sub?: string; children?: React.ReactNode }) {
  return (
    <div className="rounded-md border p-2.5">
      <div className="flex items-center gap-1.5 text-[11px] text-muted-foreground"><Icon className="h-3.5 w-3.5" />{label}</div>
      <div className="mt-0.5 font-semibold tabular">{value}</div>
      {sub && <div className="text-[11px] text-muted-foreground">{sub}</div>}
      {children}
    </div>
  );
}

export function nearestPlace(p: LatLng) {
  let best = PLACES[0]!, bd = Infinity;
  for (const pl of PLACES) { const d = (pl.pos.lat - p.lat) ** 2 + (pl.pos.lng - p.lng) ** 2; if (d < bd) { bd = d; best = pl; } }
  return `Near ${best.name}`;
}
