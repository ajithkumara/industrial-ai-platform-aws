import * as React from "react";
import { Upload } from "lucide-react";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input, Textarea } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Field } from "@/components/shared/PageHeader";
import { useFleet } from "@/store/FleetStore";
import { useToast } from "@/components/ui/toast";
import type { MaintenanceType } from "@/types";

const TYPES: MaintenanceType[] = ["Oil Change", "Brake Service", "Tire Rotation", "Tire Replacement", "Safety Inspection", "Battery Replacement", "Transmission Service", "Coolant Flush", "Other"];
const PROVIDERS = ["Oakville Ford Service", "Mercedes-Benz Oakville", "Mister Transmission — Burlington", "Kal Tire — Speers Rd", "Midas — Dundas St", "In-house (NorthStar shop)"];

export function MaintenanceDialog({ open, onOpenChange, vehicleId, mode = "schedule" }: { open: boolean; onOpenChange: (o: boolean) => void; vehicleId?: string; mode?: "schedule" | "record" }) {
  const { s, actions, fmt } = useFleet();
  const { toast } = useToast();
  const [f, setF] = React.useState({ vehicleId: vehicleId ?? "", type: "Oil Change" as MaintenanceType, date: new Date().toISOString().slice(0, 10), odometerKm: "", provider: PROVIDERS[0]!, cost: "", nextKm: "", nextDate: "", notes: "", invoice: "" });
  const [errors, setErrors] = React.useState<Record<string, string>>({});
  React.useEffect(() => {
    if (!open) return;
    const v = s.vehicles.find((x) => x.id === (vehicleId ?? ""));
    setF((x) => ({ ...x, vehicleId: vehicleId ?? x.vehicleId, odometerKm: v ? String(v.odometerKm) : "", nextKm: v ? String(v.odometerKm + 8000) : "", invoice: "", notes: "", cost: "" }));
    setErrors({});
  }, [open, vehicleId, s.vehicles]);
  const set = (k: keyof typeof f) => (v: string) => setF((x) => ({ ...x, [k]: v }));
  const submit = () => {
    const e: Record<string, string> = {};
    if (!f.vehicleId) e.vehicleId = "Choose a vehicle";
    if (!f.date) e.date = "Required";
    if (!(Number(f.odometerKm) >= 0)) e.odometerKm = "Enter a number";
    if (mode === "record" && !(Number(f.cost) >= 0)) e.cost = "Enter the invoice total";
    if (f.nextKm && !(Number(f.nextKm) > 0)) e.nextKm = "Enter a number";
    setErrors(e); if (Object.keys(e).length) return;
    actions.scheduleMaintenance({ vehicleId: f.vehicleId, type: f.type, date: new Date(f.date).toISOString(), odometerKm: Number(f.odometerKm), provider: f.provider, cost: Number(f.cost || 0), nextKm: f.nextKm ? Number(f.nextKm) : undefined, nextDate: f.nextDate ? new Date(f.nextDate).toISOString() : undefined, notes: f.notes || undefined, invoiceName: f.invoice || undefined }, mode === "record" ? "completed" : "scheduled");
    toast({ title: mode === "record" ? "Service recorded" : "Maintenance scheduled", description: `${s.vehicles.find((v) => v.id === f.vehicleId)?.name} · ${f.type}` });
    onOpenChange(false);
  };
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-xl">
        <DialogHeader><DialogTitle>{mode === "record" ? "Record completed service" : "Schedule maintenance"}</DialogTitle><DialogDescription>{mode === "record" ? "Manually entered; shown separately from OBD diagnostics." : "Set a date and/or an odometer reminder. Reminders create notifications when due."}</DialogDescription></DialogHeader>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Vehicle" error={errors.vehicleId}><Select value={f.vehicleId} onValueChange={set("vehicleId")}><SelectTrigger><SelectValue placeholder="Select vehicle" /></SelectTrigger><SelectContent>{s.vehicles.filter((v) => !v.archived).map((v) => <SelectItem key={v.id} value={v.id}>{v.name} · {v.registration}</SelectItem>)}</SelectContent></Select></Field>
          <Field label="Service type"><Select value={f.type} onValueChange={(v) => set("type")(v)}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent>{TYPES.map((t) => <SelectItem key={t} value={t}>{t}</SelectItem>)}</SelectContent></Select></Field>
          <Field label={mode === "record" ? "Service date" : "Scheduled date"} error={errors.date}><Input type="date" value={f.date} onChange={(e) => set("date")(e.target.value)} /></Field>
          <Field label={`Odometer (${fmt.distUnit})`} error={errors.odometerKm}><Input inputMode="numeric" value={f.odometerKm} onChange={(e) => set("odometerKm")(e.target.value)} /></Field>
          <Field label="Service provider"><Select value={f.provider} onValueChange={set("provider")}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent>{PROVIDERS.map((p) => <SelectItem key={p} value={p}>{p}</SelectItem>)}</SelectContent></Select></Field>
          <Field label={mode === "record" ? "Cost" : "Estimated cost"} error={errors.cost}><Input inputMode="decimal" value={f.cost} onChange={(e) => set("cost")(e.target.value)} placeholder="0.00" /></Field>
          <Field label={`Next service at (${fmt.distUnit})`} error={errors.nextKm} hint="Mileage-based reminder"><Input inputMode="numeric" value={f.nextKm} onChange={(e) => set("nextKm")(e.target.value)} /></Field>
          <Field label="Next service date" hint="Time-based reminder"><Input type="date" value={f.nextDate} onChange={(e) => set("nextDate")(e.target.value)} /></Field>
          <Field label="Invoice / work order" className="sm:col-span-2" hint="Stored with the record in this prototype; files are not uploaded anywhere.">
            <label className="flex cursor-pointer items-center gap-2 rounded-md border border-dashed px-3 py-2 text-sm text-muted-foreground hover:bg-accent/40">
              <Upload className="h-4 w-4" />{f.invoice || "Choose a PDF or image"}<input type="file" className="hidden" accept=".pdf,image/*" onChange={(e) => set("invoice")(e.target.files?.[0]?.name ?? "")} />
            </label>
          </Field>
          <Field label="Notes" className="sm:col-span-2"><Textarea value={f.notes} onChange={(e) => set("notes")(e.target.value)} placeholder="Parts replaced, technician comments…" /></Field>
        </div>
        <DialogFooter><Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button><Button onClick={submit}>{mode === "record" ? "Save record" : "Schedule"}</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
