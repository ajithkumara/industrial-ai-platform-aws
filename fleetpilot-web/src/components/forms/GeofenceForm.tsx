import * as React from "react";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Field } from "@/components/shared/PageHeader";
import { useFleet } from "@/store/FleetStore";
import { useToast } from "@/components/ui/toast";
import { CUSTOMER_SITES, PLACES } from "@/data/geo";
import type { Geofence, GeofenceCategory, LatLng } from "@/types";

export function GeofenceDialog({ open, onOpenChange, geofence, initial }: { open: boolean; onOpenChange: (o: boolean) => void; geofence?: Geofence; initial?: { center: LatLng; name?: string } }) {
  const { s, actions } = useFleet();
  const { toast } = useToast();
  const blank = { name: "", category: "customer" as GeofenceCategory, shape: "circle" as "circle" | "polygon", lat: "43.4354", lng: "-79.7085", radiusM: "200", address: "", vehicleIds: [] as string[], alertOnEntry: true, alertOnExit: true, polygonText: "" };
  const [f, setF] = React.useState(blank);
  const [errors, setErrors] = React.useState<Record<string, string>>({});
  React.useEffect(() => {
    if (!open) return;
    if (geofence) setF({ name: geofence.name, category: geofence.category, shape: geofence.shape, lat: String(geofence.center.lat), lng: String(geofence.center.lng), radiusM: String(geofence.radiusM), address: geofence.address, vehicleIds: geofence.vehicleIds, alertOnEntry: geofence.alertOnEntry, alertOnExit: geofence.alertOnExit, polygonText: geofence.polygon?.map((p) => `${p.lat}, ${p.lng}`).join("\n") ?? "" });
    else setF({ ...blank, lat: String(initial?.center.lat ?? blank.lat), lng: String(initial?.center.lng ?? blank.lng), name: initial?.name ?? "" });
    setErrors({});
  }, [open, geofence, initial?.center.lat, initial?.center.lng]); // eslint-disable-line react-hooks/exhaustive-deps
  const set = <K extends keyof typeof f>(k: K) => (v: (typeof f)[K]) => setF((x) => ({ ...x, [k]: v }));

  const useKnown = (name: string) => {
    const p = CUSTOMER_SITES.find((c) => c.name === name) ?? PLACES.find((c) => c.name === name);
    if (!p) return;
    setF((x) => ({ ...x, name: x.name || p.name, lat: String(p.pos.lat), lng: String(p.pos.lng), address: "address" in p ? p.address : x.address }));
  };
  const submit = () => {
    const e: Record<string, string> = {};
    if (!f.name.trim()) e.name = "Required";
    const lat = Number(f.lat), lng = Number(f.lng);
    if (!(lat > 41 && lat < 57)) e.lat = "Latitude out of range for Canada/US";
    if (!(lng > -142 && lng < -52)) e.lng = "Longitude out of range";
    let polygon: LatLng[] | undefined;
    if (f.shape === "circle") { if (!(Number(f.radiusM) >= 50 && Number(f.radiusM) <= 20000)) e.radiusM = "Radius 50–20,000 m"; }
    else {
      polygon = f.polygonText.split(/\n/).map((l) => l.split(",").map((x) => Number(x.trim()))).filter((p) => p.length === 2 && p.every((n) => !isNaN(n))).map(([a, b]) => ({ lat: a!, lng: b! }));
      if (polygon.length < 3) e.polygonText = "Enter at least 3 points as “lat, lng” per line";
    }
    setErrors(e); if (Object.keys(e).length) return;
    const data = { name: f.name.trim(), category: f.category, shape: f.shape, center: { lat, lng }, radiusM: f.shape === "circle" ? Number(f.radiusM) : 0, polygon, address: f.address.trim() || `${lat.toFixed(4)}, ${lng.toFixed(4)}`, vehicleIds: f.vehicleIds, alertOnEntry: f.alertOnEntry, alertOnExit: f.alertOnExit };
    if (geofence) { actions.updateGeofence(geofence.id, data); toast({ title: "Geofence updated" }); }
    else { actions.addGeofence(data); toast({ title: "Geofence created", description: `${data.name}. Entry/exit alerts will appear in Notifications.` }); }
    onOpenChange(false);
  };
  const toggleVehicle = (id: string) => setF((x) => ({ ...x, vehicleIds: x.vehicleIds.includes(id) ? x.vehicleIds.filter((v) => v !== id) : [...x.vehicleIds, id] }));

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-xl">
        <DialogHeader><DialogTitle>{geofence ? "Edit geofence" : "Create geofence"}</DialogTitle><DialogDescription>Zones trigger entry/exit events and can be limited to specific vehicles.</DialogDescription></DialogHeader>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Name" error={errors.name} className="sm:col-span-2"><Input value={f.name} onChange={(e) => set("name")(e.target.value)} placeholder="Customer site, depot, supplier…" /></Field>
          <Field label="Category"><Select value={f.category} onValueChange={(v) => set("category")(v as GeofenceCategory)}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent><SelectItem value="customer">Customer location</SelectItem><SelectItem value="depot">Depot</SelectItem><SelectItem value="warehouse">Warehouse / supplier</SelectItem><SelectItem value="restricted">Restricted zone</SelectItem></SelectContent></Select></Field>
          <Field label="Shape"><Select value={f.shape} onValueChange={(v) => set("shape")(v as "circle" | "polygon")}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent><SelectItem value="circle">Circle</SelectItem><SelectItem value="polygon">Polygon</SelectItem></SelectContent></Select></Field>
          <Field label="Pick a known place" className="sm:col-span-2" hint="Fills coordinates and address">
            <Select onValueChange={useKnown}><SelectTrigger><SelectValue placeholder="Choose…" /></SelectTrigger><SelectContent>{[...CUSTOMER_SITES.map((c) => c.name), ...PLACES.map((p) => p.name)].map((n) => <SelectItem key={n} value={n}>{n}</SelectItem>)}</SelectContent></Select>
          </Field>
          <Field label="Centre latitude" error={errors.lat}><Input value={f.lat} onChange={(e) => set("lat")(e.target.value)} /></Field>
          <Field label="Centre longitude" error={errors.lng}><Input value={f.lng} onChange={(e) => set("lng")(e.target.value)} /></Field>
          {f.shape === "circle" ? (
            <Field label="Radius (metres)" error={errors.radiusM}><Input inputMode="numeric" value={f.radiusM} onChange={(e) => set("radiusM")(e.target.value)} /></Field>
          ) : (
            <Field label="Polygon points" error={errors.polygonText} className="sm:col-span-2" hint="One “lat, lng” per line, at least 3"><textarea className="min-h-[88px] w-full rounded-md border px-3 py-2 font-mono text-xs" value={f.polygonText} onChange={(e) => set("polygonText")(e.target.value)} placeholder={"43.665, -79.405\n43.665, -79.360\n43.640, -79.360"} /></Field>
          )}
          <Field label="Address" className={f.shape === "circle" ? "" : "sm:col-span-2"}><Input value={f.address} onChange={(e) => set("address")(e.target.value)} /></Field>
          <div className="sm:col-span-2 grid grid-cols-2 gap-3 rounded-md border p-3 text-sm">
            <label className="flex items-center justify-between">Alert on entry <Switch checked={f.alertOnEntry} onCheckedChange={set("alertOnEntry")} /></label>
            <label className="flex items-center justify-between">Alert on exit <Switch checked={f.alertOnExit} onCheckedChange={set("alertOnExit")} /></label>
          </div>
          <Field label="Applies to" className="sm:col-span-2" hint={f.vehicleIds.length ? `${f.vehicleIds.length} selected` : "All vehicles"}>
            <div className="flex max-h-28 flex-wrap gap-1.5 overflow-y-auto rounded-md border p-2">
              {s.vehicles.filter((v) => !v.archived).map((v) => <button key={v.id} type="button" onClick={() => toggleVehicle(v.id)} className={`rounded-full border px-2 py-0.5 text-xs ${f.vehicleIds.includes(v.id) ? "border-primary bg-primary text-primary-foreground" : "hover:bg-accent"}`}>{v.name}</button>)}
            </div>
          </Field>
        </div>
        <DialogFooter><Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button><Button onClick={submit}>{geofence ? "Save" : "Create geofence"}</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
