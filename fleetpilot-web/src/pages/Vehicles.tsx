import * as React from "react";
import { useNavigate } from "react-router-dom";
import { Plus, MoreHorizontal, Archive, Pencil, UserPlus, Wrench, Map } from "lucide-react";
import { PageHeader, ConfirmDialog } from "@/components/shared/PageHeader";
import { DataTable, type Column } from "@/components/shared/DataTable";
import { VehicleStatusBadge } from "@/components/shared/StatusBadge";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/misc";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { VehicleDialog } from "@/components/forms/VehicleForm";
import { isDemo } from "@/services/mode";
import { MaintenanceDialog } from "@/components/forms/MaintenanceForm";
import { useFleet } from "@/store/FleetStore";
import { useToast } from "@/components/ui/toast";
import { downloadCsv } from "@/lib/utils";
import { serviceStatus } from "@/lib/metrics";
import type { Vehicle } from "@/types";

export default function VehiclesPage() {
  const { s, fmt, actions, fleetFilter } = useFleet();
  const nav = useNavigate();
  const { toast } = useToast();
  const [add, setAdd] = React.useState(false);
  const [edit, setEdit] = React.useState<Vehicle | undefined>();
  const [archive, setArchive] = React.useState<Vehicle | undefined>();
  const [maint, setMaint] = React.useState<string | undefined>();
  const [assign, setAssign] = React.useState<Vehicle | undefined>();
  const [assignTo, setAssignTo] = React.useState("none");
  const [showArchived, setShowArchived] = React.useState(false);

  const rows = s.vehicles.filter((v) => (showArchived || !v.archived) && (fleetFilter === "all" || v.type === fleetFilter));
  const driverName = (id?: string) => s.drivers.find((d) => d.id === id)?.name ?? "—";

  const columns: Column<Vehicle>[] = [
    { key: "id", header: "ID", cell: (v) => <span className="font-mono text-xs text-muted-foreground">{v.id}</span>, sortValue: (v) => v.id, width: "w-20" },
    { key: "name", header: "Vehicle", cell: (v) => <div><div className="font-medium">{v.name}</div><div className="text-xs text-muted-foreground">{v.registration}</div></div>, sortValue: (v) => v.name, csv: (v) => `${v.name} (${v.registration})` },
    { key: "type", header: "Type", cell: (v) => <span className="text-muted-foreground">{v.type}</span>, sortValue: (v) => v.type },
    { key: "make", header: "Make / model", cell: (v) => `${v.make} ${v.model}`, sortValue: (v) => `${v.make} ${v.model}` },
    { key: "year", header: "Year", cell: (v) => v.year, sortValue: (v) => v.year },
    { key: "driver", header: "Driver", cell: (v) => (v.driverId ? <button className="hover:underline" onClick={(e) => { e.stopPropagation(); nav(`/drivers/${v.driverId}`); }}>{driverName(v.driverId)}</button> : <span className="text-muted-foreground">Unassigned</span>), sortValue: (v) => driverName(v.driverId) },
    { key: "status", header: "Status", cell: (v) => (v.archived ? <Badge variant="muted">Archived</Badge> : <VehicleStatusBadge status={v.status} freshness={v.freshness} />), sortValue: (v) => (v.archived ? "zz" : v.status) },
    { key: "odo", header: "Odometer", cell: (v) => (v.odometerSource === "none" ? <span className="text-xs text-muted-foreground">not reported</span> : v.device.source === "obd" ? <span title="Counted by the tracker since install">{fmt.dist(v.odometerKm)}*</span> : fmt.dist(v.odometerKm)), sortValue: (v) => v.odometerKm, align: "right" },
    { key: "fuel", header: "Fuel", cell: (v) => (v.fuelLevelPct === undefined ? <span className="text-xs text-muted-foreground">n/a</span> : <div className="flex items-center gap-2"><Progress value={v.fuelLevelPct} className="w-14" tone={v.fuelLevelPct < 20 ? "destructive" : "secondary"} /><span className="text-xs tabular">{v.fuelLevelPct}%</span></div>), sortValue: (v) => v.fuelLevelPct ?? -1 },
    { key: "service", header: "Last service", cell: (v) => { if (v.device.source === "obd") return <span className="text-xs text-muted-foreground">—</span>; const st = serviceStatus(v); return <div><div>{fmt.date(v.lastServiceDate)}</div>{st !== "ok" && <div className={st === "overdue" ? "text-xs font-medium text-red-600" : "text-xs text-amber-600"}>{st === "overdue" ? `Overdue ${fmt.dist(v.odometerKm - v.nextServiceKm)}` : `Due in ${fmt.dist(v.nextServiceKm - v.odometerKm)}`}</div>}</div>; }, sortValue: (v) => v.lastServiceDate, csv: (v) => v.lastServiceDate.slice(0, 10) },
    { key: "actions", header: "", cell: (v) => (
      <div onClick={(e) => e.stopPropagation()}>
        <DropdownMenu>
          <DropdownMenuTrigger asChild><Button variant="ghost" size="iconSm"><MoreHorizontal className="h-4 w-4" /></Button></DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuItem onClick={() => nav(`/vehicles/${v.id}`)}>View details</DropdownMenuItem>
            <DropdownMenuItem onClick={() => nav(`/map?vehicle=${v.id}`)}><Map />Show on map</DropdownMenuItem>
            <DropdownMenuItem onClick={() => setEdit(v)}><Pencil />Edit</DropdownMenuItem>
            <DropdownMenuItem onClick={() => { setAssign(v); setAssignTo(v.driverId ?? "none"); }}><UserPlus />Assign driver</DropdownMenuItem>
            <DropdownMenuItem onClick={() => setMaint(v.id)}><Wrench />Schedule maintenance</DropdownMenuItem>
            <DropdownMenuSeparator />
            {!v.archived && <DropdownMenuItem className="text-destructive" onClick={() => setArchive(v)}><Archive />Archive</DropdownMenuItem>}
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    ), width: "w-10" },
  ];

  return (
    <>
      <PageHeader title="Vehicles" description={`${rows.filter((v) => !v.archived).length} active vehicles · ${s.vehicles.filter((v) => v.archived).length} archived`}
        actions={<><Button variant="outline" size="sm" onClick={() => setShowArchived((x) => !x)}>{showArchived ? "Hide archived" : "Show archived"}</Button>{isDemo() ? <Button size="sm" onClick={() => setAdd(true)}><Plus className="h-4 w-4" />Add vehicle</Button> : <Button size="sm" variant="outline" title="Vehicles are added when FleetPilot registers your tracker" onClick={() => alert("To add a vehicle, send the tracker IMEI to FleetPilot support. Self-service vehicle setup is coming in a later release.")}><Plus className="h-4 w-4" />Add vehicle</Button>}</>} />
      <DataTable rows={rows} columns={columns} rowKey={(v) => v.id} onRowClick={(v) => nav(`/vehicles/${v.id}`)} exportName="vehicles" pageSize={15} selectable
        searchKeys={(v) => `${v.id} ${v.name} ${v.registration} ${v.make} ${v.model} ${driverName(v.driverId)}`}
        filters={[
          { key: "status", label: "Status", options: [{ value: "moving", label: "Moving" }, { value: "idle", label: "Idle" }, { value: "stopped", label: "Stopped" }, { value: "offline", label: "Offline" }], predicate: (v, x) => v.status === x },
          { key: "type", label: "Type", options: [{ value: "Cargo Van", label: "Cargo van" }, { value: "Pickup Truck", label: "Pickup truck" }, { value: "Service Truck", label: "Service truck" }], predicate: (v, x) => v.type === x },
          { key: "service", label: "Service", options: [{ value: "overdue", label: "Overdue" }, { value: "due_soon", label: "Due soon" }, { value: "ok", label: "Up to date" }], predicate: (v, x) => serviceStatus(v) === x },
        ]}
        bulkActions={(ids, clear) => (
          <>
            <Button size="sm" variant="outline" onClick={() => { ids.forEach((id) => actions.scheduleMaintenance({ vehicleId: id, type: "Safety Inspection", date: new Date(Date.now() + 7 * 864e5).toISOString(), odometerKm: s.vehicles.find((v) => v.id === id)?.odometerKm ?? 0, provider: "In-house (NorthStar shop)", cost: 0, notes: "Bulk-scheduled inspection" })); toast({ title: `Inspection scheduled for ${ids.length} vehicles` }); clear(); }}>Schedule inspection</Button>
            <Button size="sm" variant="outline" onClick={() => { const rowsCsv = s.vehicles.filter((v) => ids.includes(v.id)); downloadCsv("selected-vehicles.csv", rowsCsv.map((v) => ({ id: v.id, name: v.name, registration: v.registration, odometer_km: v.odometerKm }))); clear(); }}>Export selected</Button>
          </>
        )}
      />
      <VehicleDialog open={add} onOpenChange={setAdd} onSaved={(v) => nav(`/vehicles/${v.id}`)} />
      <VehicleDialog open={!!edit} onOpenChange={(o) => !o && setEdit(undefined)} vehicle={edit} />
      <MaintenanceDialog open={!!maint} onOpenChange={(o) => !o && setMaint(undefined)} vehicleId={maint} />
      <ConfirmDialog open={!!archive} onOpenChange={(o) => !o && setArchive(undefined)} title={`Archive ${archive?.name}?`} description="The vehicle is removed from the active fleet, dashboards and reports. Its history is kept and it can be restored by support." confirmLabel="Archive vehicle" destructive onConfirm={() => { if (archive) { actions.archiveVehicle(archive.id); toast({ title: `${archive.name} archived` }); } }} />
      <Dialog open={!!assign} onOpenChange={(o) => !o && setAssign(undefined)}>
        <DialogContent className="max-w-sm">
          <DialogHeader><DialogTitle>Assign driver to {assign?.name}</DialogTitle></DialogHeader>
          <Select value={assignTo} onValueChange={setAssignTo}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent><SelectItem value="none">Unassigned</SelectItem>{s.drivers.map((d) => <SelectItem key={d.id} value={d.id}>{d.name}{d.vehicleId && d.vehicleId !== assign?.id ? ` · currently ${s.vehicles.find((v) => v.id === d.vehicleId)?.name}` : ""}</SelectItem>)}</SelectContent></Select>
          <DialogFooter><Button variant="outline" onClick={() => setAssign(undefined)}>Cancel</Button><Button onClick={() => { if (assign) { actions.assignDriver(assign.id, assignTo === "none" ? undefined : assignTo); toast({ title: "Driver assignment updated" }); } setAssign(undefined); }}>Save</Button></DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
