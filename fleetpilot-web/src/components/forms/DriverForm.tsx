import * as React from "react";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Field } from "@/components/shared/PageHeader";
import { useFleet } from "@/store/FleetStore";
import { useToast } from "@/components/ui/toast";
import type { Driver } from "@/types";

export function DriverDialog({ open, onOpenChange, driver }: { open: boolean; onOpenChange: (o: boolean) => void; driver?: Driver }) {
  const { s, actions } = useFleet();
  const { toast } = useToast();
  const blank = { name: "", employeeId: "", email: "", phone: "", licenseClass: "G", licenseExpiry: "", vehicleId: "" };
  const [f, setF] = React.useState(blank);
  const [errors, setErrors] = React.useState<Partial<Record<keyof typeof blank, string>>>({});
  React.useEffect(() => { if (open) setF(driver ? { name: driver.name, employeeId: driver.employeeId, email: driver.email, phone: driver.phone, licenseClass: driver.licenseClass, licenseExpiry: driver.licenseExpiry.slice(0, 10), vehicleId: driver.vehicleId ?? "" } : blank); setErrors({}); }, [open, driver]); // eslint-disable-line react-hooks/exhaustive-deps
  const set = (k: keyof typeof blank) => (v: string) => setF((x) => ({ ...x, [k]: v }));
  const submit = () => {
    const e: typeof errors = {};
    if (f.name.trim().split(" ").length < 2) e.name = "Enter first and last name";
    if (!f.employeeId.trim()) e.employeeId = "Required";
    if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(f.email)) e.email = "Enter a valid email";
    if (!/^[\d() +-]{10,}$/.test(f.phone)) e.phone = "Enter a valid phone number";
    if (!f.licenseExpiry) e.licenseExpiry = "Required";
    else if (new Date(f.licenseExpiry) < new Date()) e.licenseExpiry = "Licence has expired";
    setErrors(e); if (Object.keys(e).length) return;
    const data = { name: f.name.trim(), employeeId: f.employeeId.trim(), email: f.email.trim(), phone: f.phone.trim(), licenseClass: f.licenseClass, licenseExpiry: new Date(f.licenseExpiry).toISOString() };
    if (driver) {
      actions.updateDriver(driver.id, data);
      if ((f.vehicleId || undefined) !== driver.vehicleId) actions.assignDriver(f.vehicleId || driver.vehicleId || "", f.vehicleId ? driver.id : undefined);
      toast({ title: "Driver updated" });
    } else {
      const d = actions.addDriver({ ...data, hireDate: new Date().toISOString(), vehicleId: undefined });
      if (f.vehicleId) actions.assignDriver(f.vehicleId, d.id);
      toast({ title: "Driver added", description: `${d.name} can now be assigned to vehicles.` });
    }
    onOpenChange(false);
  };
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader><DialogTitle>{driver ? `Edit ${driver.name}` : "Add driver"}</DialogTitle><DialogDescription>Driver records are used for trip attribution, safety scoring and coaching.</DialogDescription></DialogHeader>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Full name" error={errors.name}><Input value={f.name} onChange={(e) => set("name")(e.target.value)} /></Field>
          <Field label="Employee ID" error={errors.employeeId}><Input value={f.employeeId} onChange={(e) => set("employeeId")(e.target.value)} placeholder="NS-1200" /></Field>
          <Field label="Email" error={errors.email}><Input type="email" value={f.email} onChange={(e) => set("email")(e.target.value)} /></Field>
          <Field label="Phone" error={errors.phone}><Input value={f.phone} onChange={(e) => set("phone")(e.target.value)} placeholder="(905) 555-0100" /></Field>
          <Field label="Licence class"><Select value={f.licenseClass} onValueChange={set("licenseClass")}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent>{["G", "G2", "DZ", "AZ", "CDL-A", "CDL-B"].map((c) => <SelectItem key={c} value={c}>{c}</SelectItem>)}</SelectContent></Select></Field>
          <Field label="Licence expiry" error={errors.licenseExpiry}><Input type="date" value={f.licenseExpiry} onChange={(e) => set("licenseExpiry")(e.target.value)} /></Field>
          <Field label="Assigned vehicle" className="sm:col-span-2">
            <Select value={f.vehicleId || "none"} onValueChange={(v) => set("vehicleId")(v === "none" ? "" : v)}><SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent><SelectItem value="none">Unassigned</SelectItem>{s.vehicles.filter((v) => !v.archived).map((v) => <SelectItem key={v.id} value={v.id}>{v.name} · {v.registration}</SelectItem>)}</SelectContent></Select>
          </Field>
        </div>
        <DialogFooter><Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button><Button onClick={submit}>{driver ? "Save changes" : "Add driver"}</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
