import * as React from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { Plus, Pencil, Trash2, LogIn, LogOut, Hexagon } from "lucide-react";
import { PageHeader, ConfirmDialog, EmptyState } from "@/components/shared/PageHeader";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { BaseMap, GeofenceLayer, FlyTo, geofenceColor, Marker, vehicleIcon } from "@/components/map/FleetMap";
import { GeofenceDialog } from "@/components/forms/GeofenceForm";
import { DataTable, type Column } from "@/components/shared/DataTable";
import { useFleet } from "@/store/FleetStore";
import { useToast } from "@/components/ui/toast";
import { inRange } from "@/lib/metrics";
import { cn } from "@/lib/utils";
import type { Geofence, GeofenceEvent } from "@/types";

const CAT: Record<Geofence["category"], string> = { customer: "Customer", depot: "Depot", warehouse: "Warehouse", restricted: "Restricted" };

export default function GeofencesPage() {
  const { s, fmt, range, actions } = useFleet();
  const nav = useNavigate();
  const { toast } = useToast();
  const [params, setParams] = useSearchParams();
  const focus = params.get("focus");
  const sel = s.geofences.find((g) => g.id === focus) ?? null;
  const [q, setQ] = React.useState("");
  const [create, setCreate] = React.useState(false);
  const [edit, setEdit] = React.useState<Geofence | undefined>();
  const [del, setDel] = React.useState<Geofence | undefined>();
  const list = s.geofences.filter((g) => !q || `${g.name} ${g.address} ${CAT[g.category]}`.toLowerCase().includes(q.toLowerCase()));
  const events = React.useMemo(() => s.geofenceEvents.filter((e) => inRange(e.time, range) && (!sel || e.geofenceId === sel.id)).sort((a, b) => b.time.localeCompare(a.time)), [s.geofenceEvents, range, sel]);
  const counts = (g: Geofence) => { const ev = s.geofenceEvents.filter((e) => e.geofenceId === g.id && inRange(e.time, range)); return { enter: ev.filter((e) => e.type === "enter").length, exit: ev.filter((e) => e.type === "exit").length }; };
  const inside = (g: Geofence) => s.vehicles.filter((v) => !v.archived && g.shape === "circle" && Math.hypot((v.position.lat - g.center.lat) * 111000, (v.position.lng - g.center.lng) * 81000) <= g.radiusM);

  const evCols: Column<GeofenceEvent>[] = [
    { key: "time", header: "Time", cell: (e) => fmt.dateTime(e.time), sortValue: (e) => e.time },
    { key: "type", header: "Event", cell: (e) => <span className="inline-flex items-center gap-1">{e.type === "enter" ? <LogIn className="h-3.5 w-3.5 text-emerald-600" /> : <LogOut className="h-3.5 w-3.5 text-slate-500" />}{e.type === "enter" ? "Entered" : "Exited"}</span>, sortValue: (e) => e.type },
    { key: "geo", header: "Geofence", cell: (e) => s.geofences.find((g) => g.id === e.geofenceId)?.name ?? "—", sortValue: (e) => s.geofences.find((g) => g.id === e.geofenceId)?.name ?? "" },
    { key: "veh", header: "Vehicle", cell: (e) => <button className="hover:underline" onClick={() => nav(`/vehicles/${e.vehicleId}`)}>{s.vehicles.find((v) => v.id === e.vehicleId)?.name}</button>, sortValue: (e) => e.vehicleId },
  ];

  return (
    <>
      <PageHeader title="Geofences" description={`${s.geofences.length} zones · ${events.length} entry/exit events in period`} actions={<Button size="sm" onClick={() => setCreate(true)}><Plus className="h-4 w-4" />Create geofence</Button>} />
      <div className="grid gap-4 xl:grid-cols-3">
        <div className="space-y-3">
          <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search zones…" />
          <div className="max-h-[560px] space-y-2 overflow-y-auto pr-1">
            {list.map((g) => { const c = counts(g); const vin = inside(g); return (
              <button key={g.id} onClick={() => setParams({ focus: g.id })} className={cn("w-full rounded-lg border bg-card p-3 text-left hover:bg-accent/40", sel?.id === g.id && "ring-2 ring-secondary")}>
                <div className="flex items-start justify-between gap-2"><div className="flex items-center gap-2"><span className="h-2.5 w-2.5 rounded-sm" style={{ background: geofenceColor(g.category) }} /><span className="font-medium">{g.name}</span></div><Badge variant="muted">{CAT[g.category]}</Badge></div>
                <div className="mt-1 truncate text-xs text-muted-foreground">{g.address}</div>
                <div className="mt-1.5 flex items-center gap-3 text-xs text-muted-foreground"><span>{g.shape === "circle" ? `${g.radiusM} m radius` : `${g.polygon?.length ?? 0}-point polygon`}</span><span>{c.enter} in / {c.exit} out</span>{vin.length > 0 && <Badge variant="success">{vin.length} inside now</Badge>}</div>
              </button>); })}
            {list.length === 0 && <EmptyState icon={Hexagon} title="No geofences match" />}
          </div>
        </div>
        <div className="space-y-4 xl:col-span-2">
          <Card className="overflow-hidden"><div className="h-[380px]"><BaseMap zoom={11}><FlyTo target={sel?.center} zoom={13} /><GeofenceLayer geofences={s.geofences} selectedId={sel?.id} onClick={(g) => setParams({ focus: g.id })} />{s.vehicles.filter((v) => !v.archived).map((v) => <Marker key={v.id} position={[v.position.lat, v.position.lng]} icon={vehicleIcon(v)} eventHandlers={{ click: () => nav(`/map?vehicle=${v.id}`) }} />)}</BaseMap></div></Card>
          {sel ? (
            <Card>
              <CardHeader className="flex-row items-start justify-between space-y-0"><div><CardTitle>{sel.name}</CardTitle><div className="text-xs text-muted-foreground">{sel.address}</div></div>
                <div className="flex gap-2"><Button size="sm" variant="outline" onClick={() => setEdit(sel)}><Pencil className="h-3.5 w-3.5" />Edit</Button><Button size="sm" variant="ghost" className="text-destructive" onClick={() => setDel(sel)}><Trash2 className="h-3.5 w-3.5" /></Button></div></CardHeader>
              <CardContent className="grid gap-3 text-sm sm:grid-cols-4">
                <div><div className="text-xs text-muted-foreground">Category</div><div>{CAT[sel.category]}</div></div>
                <div><div className="text-xs text-muted-foreground">Boundary</div><div>{sel.shape === "circle" ? `Circle · ${sel.radiusM} m` : `Polygon · ${sel.polygon?.length} points`}</div></div>
                <div><div className="text-xs text-muted-foreground">Alerts</div><div>{[sel.alertOnEntry && "entry", sel.alertOnExit && "exit"].filter(Boolean).join(" + ") || "none"}</div></div>
                <div><div className="text-xs text-muted-foreground">Applies to</div><div>{sel.vehicleIds.length ? sel.vehicleIds.map((id) => s.vehicles.find((v) => v.id === id)?.name).join(", ") : "All vehicles"}</div></div>
                <div className="sm:col-span-4 text-xs text-muted-foreground">Vehicles inside now: {inside(sel).map((v) => v.name).join(", ") || "none"}. Entry and exit events appear in Notifications when alerts are enabled.</div>
              </CardContent>
            </Card>
          ) : <p className="text-xs text-muted-foreground">Select a zone to see its details and events. Click a zone on the map or in the list.</p>}
          <section><h3 className="mb-2 text-sm font-semibold">Entry / exit events {sel && <span className="font-normal text-muted-foreground">· {sel.name}</span>}</h3><DataTable rows={events} columns={evCols} rowKey={(e) => e.id} exportName="geofence-events" pageSize={8} dense initialSort={{ key: "time", dir: "desc" }} filters={[{ key: "type", label: "Event", options: [{ value: "enter", label: "Entered" }, { value: "exit", label: "Exited" }], predicate: (e, v) => e.type === v }]} /></section>
        </div>
      </div>
      <GeofenceDialog open={create} onOpenChange={setCreate} />
      <GeofenceDialog open={!!edit} onOpenChange={(o) => !o && setEdit(undefined)} geofence={edit} />
      <ConfirmDialog open={!!del} onOpenChange={(o) => !o && setDel(undefined)} title={`Delete ${del?.name}?`} description="Past entry/exit events are kept for reporting; no new events will be generated." confirmLabel="Delete" destructive onConfirm={() => { if (del) { actions.deleteGeofence(del.id); toast({ title: "Geofence deleted" }); setParams({}); } }} />
    </>
  );
}
