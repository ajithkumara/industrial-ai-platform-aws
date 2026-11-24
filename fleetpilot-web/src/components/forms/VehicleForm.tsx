import * as React from "react";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Field } from "@/components/shared/PageHeader";
import { useFleet } from "@/store/FleetStore";
import { useToast } from "@/components/ui/toast";
import type { FuelType, Vehicle, VehicleType } from "@/types";

type Form = { name: string; registration: string; type: VehicleType; make: string; model: string; year: string; vin: string; fuelType: FuelType; tankL: string; odometerKm: string; purchasePrice: string; driverId: string; nextServiceKm: string };

const MAKES: Record<string, string[]> = { Ford: ["Transit 250", "Transit 350", "F-150 XL", "F-150 XLT", "E-Transit"], "Mercedes-Benz": ["Sprinter 2500", "Sprinter 3500", "Metris"], Chevrolet: ["Express 2500", "Express 3500", "Silverado 1500"], RAM: ["ProMaster 2500", "ProMaster 3500", "1500"], GMC: ["Savana 2500", "Sierra 1500"] };

export function VehicleDialog({ open, onOpenChange, vehicle, onSaved }: { open: boolean; onOpenChange: (o: boolean) => void; vehicle?: Vehicle; onSaved?: (v: Vehicle) => void }) {
  const { s, actions, fmt } = useFleet();
  const { toast } = useToast();
  const blank: Form = { name: "", registration: "", type: "Cargo Van", make: "Ford", model: "Transit 250", year: String(new Date().getFullYear()), vin: "", fuelType: "Gasoline", tankL: "95", odometerKm: "0", purchasePrice: "", driverId: "", nextServiceKm: "8000" };
  const [f, setF] = React.useState<Form>(blank);
  const [errors, setErrors] = React.useState<Partial<Record<keyof Form, string>>>({});
  React.useEffect(() => {
    if (open) setF(vehicle ? { name: vehicle.name, registration: vehicle.registration, type: vehicle.type, make: vehicle.make, model: vehicle.model, year: String(vehicle.year), vin: vehicle.vin, fuelType: vehicle.fuelType, tankL: String(vehicle.tankL), odometerKm: String(vehicle.odometerKm), purchasePrice: String(vehicle.purchasePrice), driverId: vehicle.driverId ?? "", nextServiceKm: String(vehicle.nextServiceKm) } : blank);
    setErrors({});
  }, [open, vehicle]); // eslint-disable-line react-hooks/exhaustive-deps
  const set = (k: keyof Form) => (v: string) => setF((x) => ({ ...x, [k]: v }));

  const validate = () => {
    const e: typeof errors = {};
    if (!f.name.trim()) e.name = "Required";
    if (!/^[A-Z0-9 -]{4,10}$/i.test(f.registration.trim())) e.registration = "Enter a valid plate (4–10 characters)";
    else if (s.vehicles.some((v) => v.registration.replace(/\s/g, "").toUpperCase() === f.registration.replace(/\s/g, "").toUpperCase() && v.id !== vehicle?.id)) e.registration = "Another vehicle already uses this plate";
    const yr = Number(f.year); if (!yr || yr < 1995 || yr > new Date().getFullYear() + 1) e.year = "Year 1995 to next model year";
    if (f.vin && !/^[A-HJ-NPR-Z0-9]{17}$/i.test(f.vin.trim())) e.vin = "VIN must be 17 characters (no I, O, Q)";
    if (!(Number(f.odometerKm) >= 0)) e.odometerKm = "Enter a number";
    if (!(Number(f.tankL) > 0)) e.tankL = "Enter tank capacity";
    if (f.purchasePrice && !(Number(f.purchasePrice) >= 0)) e.purchasePrice = "Enter a number";
    if (!(Number(f.nextServiceKm) > 0)) e.nextServiceKm = "Enter the next service odometer";
    setErrors(e); return Object.keys(e).length === 0;
  };

  const submit = () => {
    if (!validate()) return;
    const base = { name: f.name.trim(), registration: f.registration.trim().toUpperCase(), type: f.type, make: f.make, model: f.model, year: Number(f.year), vin: f.vin.trim().toUpperCase() || "UNKNOWN", fuelType: f.fuelType, tankL: Number(f.tankL), odometerKm: Number(f.odometerKm), purchasePrice: Number(f.purchasePrice || 0), nextServiceKm: Number(f.nextServiceKm) };
    if (vehicle) {
      actions.updateVehicle(vehicle.id, base);
      if ((f.driverId || undefined) !== vehicle.driverId) actions.assignDriver(vehicle.id, f.driverId || undefined);
      toast({ title: "Vehicle updated", description: `${base.name} saved.` });
      onSaved?.({ ...vehicle, ...base });
    } else {
      const v = actions.addVehicle({ ...base, lastServiceDate: new Date().toISOString(), nextServiceDate: new Date(Date.now() + 180 * 864e5).toISOString() });
      if (f.driverId) actions.assignDriver(v.id, f.driverId);
      toast({ title: "Vehicle added", description: `${v.name} (${v.registration}) is now in the fleet. Assign a GPS device under Integrations to receive telemetry.` });
      onSaved?.(v);
    }
    onOpenChange(false);
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogHeader><DialogTitle>{vehicle ? `Edit ${vehicle.name}` : "Add vehicle"}</DialogTitle><DialogDescription>{vehicle ? "Changes apply immediately across the fleet." : "New vehicles appear in the list, dashboard counts and reports right away."}</DialogDescription></DialogHeader>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Vehicle name" error={errors.name}><Input value={f.name} onChange={(e) => set("name")(e.target.value)} placeholder="Van 116" /></Field>
          <Field label="Registration (plate)" error={errors.registration}><Input value={f.registration} onChange={(e) => set("registration")(e.target.value)} placeholder="CXYZ 123" /></Field>
          <Field label="Vehicle type"><Select value={f.type} onValueChange={(v) => set("type")(v)}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent>{(["Cargo Van", "Pickup Truck", "Service Truck"] as VehicleType[]).map((t) => <SelectItem key={t} value={t}>{t}</SelectItem>)}</SelectContent></Select></Field>
          <Field label="Fuel type"><Select value={f.fuelType} onValueChange={(v) => set("fuelType")(v)}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent><SelectItem value="Gasoline">Gasoline</SelectItem><SelectItem value="Diesel">Diesel</SelectItem></SelectContent></Select></Field>
          <Field label="Make"><Select value={f.make} onValueChange={(v) => { set("make")(v); set("model")(MAKES[v]?.[0] ?? ""); }}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent>{Object.keys(MAKES).map((m) => <SelectItem key={m} value={m}>{m}</SelectItem>)}</SelectContent></Select></Field>
          <Field label="Model"><Select value={f.model} onValueChange={set("model")}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent>{(MAKES[f.make] ?? [f.model]).map((m) => <SelectItem key={m} value={m}>{m}</SelectItem>)}</SelectContent></Select></Field>
          <Field label="Model year" error={errors.year}><Input inputMode="numeric" value={f.year} onChange={(e) => set("year")(e.target.value)} /></Field>
          <Field label="VIN" error={errors.vin} hint="17 characters; optional for the demo"><Input value={f.vin} onChange={(e) => set("vin")(e.target.value)} placeholder="1FTBR1C86NKA10231" className="font-mono uppercase" /></Field>
          <Field label={`Odometer (${fmt.distUnit})`} error={errors.odometerKm}><Input inputMode="numeric" value={f.odometerKm} onChange={(e) => set("odometerKm")(e.target.value)} /></Field>
          <Field label={`Tank capacity (${fmt.volUnit})`} error={errors.tankL}><Input inputMode="numeric" value={f.tankL} onChange={(e) => set("tankL")(e.target.value)} /></Field>
          <Field label={`Next service at (${fmt.distUnit})`} error={errors.nextServiceKm}><Input inputMode="numeric" value={f.nextServiceKm} onChange={(e) => set("nextServiceKm")(e.target.value)} /></Field>
          <Field label="Purchase price" error={errors.purchasePrice} hint="Used for total cost of ownership"><Input inputMode="numeric" value={f.purchasePrice} onChange={(e) => set("purchasePrice")(e.target.value)} placeholder="58900" /></Field>
          <Field label="Assigned driver" className="sm:col-span-2">
            <Select value={f.driverId || "none"} onValueChange={(v) => set("driverId")(v === "none" ? "" : v)}><SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent><SelectItem value="none">Unassigned</SelectItem>{s.drivers.map((d) => <SelectItem key={d.id} value={d.id}>{d.name}{d.vehicleId && d.vehicleId !== vehicle?.id ? ` (currently ${s.vehicles.find((v) => v.id === d.vehicleId)?.name})` : ""}</SelectItem>)}</SelectContent></Select>
          </Field>
        </div>
        <DialogFooter><Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button><Button onClick={submit}>{vehicle ? "Save changes" : "Add vehicle"}</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
