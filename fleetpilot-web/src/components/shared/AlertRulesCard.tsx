import * as React from "react";
import { useNavigate } from "react-router-dom";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { useToast } from "@/components/ui/toast";
import { useFleet } from "@/store/FleetStore";
import type { AlertSettings } from "@/services/alerts";

const DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

/** Live accounts: the rules the server evaluates on every data pass. */
export function AlertRulesCard() {
  const { alertSettings, actions } = useFleet();
  const { toast } = useToast();
  const nav = useNavigate();
  const [d, setD] = React.useState<AlertSettings | null>(alertSettings);
  const [saving, setSaving] = React.useState(false);
  const [emails, setEmails] = React.useState((alertSettings?.email.to ?? []).join(", "));
  React.useEffect(() => { setD(alertSettings); setEmails((alertSettings?.email.to ?? []).join(", ")); }, [alertSettings]);
  if (!d) return <Card className="mb-4"><CardContent className="p-4 text-sm text-muted-foreground">Loading alert rules…</CardContent></Card>;
  const dirty = JSON.stringify(d) !== JSON.stringify(alertSettings);
  const ah = d.after_hours;
  const set = (p: Partial<AlertSettings>) => setD({ ...d, ...p });
  const save = async () => {
    setSaving(true);
    try { await actions.saveAlertSettings(d); toast({ title: "Alert rules saved", description: "They apply from the next data the trackers send." }); }
    catch (e) { toast({ title: "Could not save", description: String((e as Error).message), tone: "warning" }); }
    finally { setSaving(false); }
  };

  return (
    <Card className="mb-4">
      <CardHeader className="flex-row items-start justify-between space-y-0 pb-3">
        <div><CardTitle>Alert rules</CardTitle><CardDescription>Checked by FleetPilot every time your trackers report. Each alert fires once per event, not repeatedly.</CardDescription></div>
        <div className="flex items-center gap-2 text-sm">Alerts on<Switch checked={d.enabled} onCheckedChange={(v) => set({ enabled: v })} /></div>
      </CardHeader>
      <CardContent className="grid gap-4 text-sm md:grid-cols-2 xl:grid-cols-4">
        <label className="space-y-1"><div className="font-medium">Speed limit</div>
          <div className="flex items-center gap-2"><Input type="number" min={0} max={250} value={d.speed_limit_kmh} onChange={(e) => set({ speed_limit_kmh: Number(e.target.value) })} className="w-24" />km/h</div>
          <div className="text-xs text-muted-foreground">One alert per trip above this. 0 turns it off.</div></label>
        <label className="space-y-1"><div className="font-medium">Not reporting after</div>
          <div className="flex items-center gap-2"><Input type="number" min={30} max={2880} value={d.offline_minutes} onChange={(e) => set({ offline_minutes: Number(e.target.value) })} className="w-24" />minutes</div>
          <div className="text-xs text-muted-foreground">A parked MP91 reports about every 20 min; keep this above 60.</div></label>
        <div className="space-y-1"><div className="flex items-center gap-2 font-medium">After-hours use<Switch checked={ah.enabled} onCheckedChange={(v) => set({ after_hours: { ...ah, enabled: v } })} /></div>
          <div className="flex items-center gap-2"><Input type="time" value={ah.start} onChange={(e) => set({ after_hours: { ...ah, start: e.target.value } })} className="w-28" />to<Input type="time" value={ah.end} onChange={(e) => set({ after_hours: { ...ah, end: e.target.value } })} className="w-28" /></div>
          <div className="flex flex-wrap gap-1">{DAYS.map((name, i) => { const on = ah.days.includes(i); return <button key={name} type="button" onClick={() => set({ after_hours: { ...ah, days: on ? ah.days.filter((x) => x !== i) : [...ah.days, i].sort() } })} className={`rounded border px-1.5 py-0.5 text-xs ${on ? "border-primary bg-primary text-primary-foreground" : "text-muted-foreground"}`}>{name}</button>; })}</div>
          <div className="text-xs text-muted-foreground">Business hours (Toronto time). Ignition outside them raises an alert.</div></div>
        <div className="space-y-1"><div className="font-medium">Always on</div>
          <div className="text-xs text-muted-foreground">Tracker unplugged · low battery · geofence arrivals and departures ({d.geofences.length} geofence{d.geofences.length === 1 ? "" : "s"}).</div>
          <Button variant="link" size="sm" className="h-auto p-0" onClick={() => nav("/geofences")}>Manage geofences →</Button></div>
        <div className="space-y-1 md:col-span-2 xl:col-span-4"><div className="flex items-center gap-2 font-medium">Email alerts<Switch checked={d.email.enabled} onCheckedChange={(v) => set({ email: { ...d.email, enabled: v } })} /></div>
          <Input placeholder="you@company.com, manager@company.com" value={emails} onChange={(e) => { setEmails(e.target.value); set({ email: { ...d.email, to: e.target.value.split(/[,;\s]+/).map((x) => x.trim()).filter(Boolean).slice(0, 5) } }); }} className="max-w-xl" />
          <div className="text-xs text-muted-foreground">Up to 5 addresses. One email per batch of new alerts, at most 10 an hour. During testing, each address must first be verified with AWS (it receives a one-time confirmation email).</div></div>
      </CardContent>
      {dirty && <div className="flex justify-end gap-2 border-t p-3"><Button variant="outline" size="sm" onClick={() => { setD(alertSettings); setEmails((alertSettings?.email.to ?? []).join(", ")); }}>Discard</Button><Button size="sm" disabled={saving} onClick={save}>{saving ? "Saving…" : "Save rules"}</Button></div>}
    </Card>
  );
}
