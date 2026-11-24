import * as React from "react";
import { useNavigate } from "react-router-dom";
import { ShieldCheck, Gauge, OctagonAlert, Zap, Timer, Video, Lock, CheckCircle2 } from "lucide-react";
import { Bar, BarChart, Line, LineChart, Cell } from "recharts";
import { PageHeader, Field } from "@/components/shared/PageHeader";
import { KpiCard } from "@/components/shared/KpiCard";
import { DataTable, type Column } from "@/components/shared/DataTable";
import { SeverityBadge } from "@/components/shared/StatusBadge";
import { ChartCard, C, grid, tip, xAxis, yAxis } from "@/components/shared/Charts";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription } from "@/components/ui/sheet";
import { Textarea } from "@/components/ui/input";
import { Avatar } from "@/components/ui/misc";
import { useFleet } from "@/store/FleetStore";
import { useToast } from "@/components/ui/toast";
import { dailySeries, driverSafety, fleetKpis, pctChange, safetyIn, scoreTone } from "@/lib/metrics";
import { DeviceLimitNotice } from "@/components/shared/DeviceLimitNotice";
import type { SafetyEvent } from "@/types";

const LABEL: Record<SafetyEvent["type"], string> = { speeding: "Speeding", harsh_braking: "Harsh braking", harsh_acceleration: "Harsh acceleration", excessive_idling: "Excessive idling", distracted: "Distracted driving" };

export default function SafetyPage() {
  const { s, fmt, range, actions } = useFleet();
  const nav = useNavigate();
  const { toast } = useToast();
  const [review, setReview] = React.useState<SafetyEvent | undefined>();
  const [note, setNote] = React.useState("");
  const k = fleetKpis(s, range);
  const events = safetyIn(s, range).sort((a, b) => b.time.localeCompare(a.time));
  const count = (t: SafetyEvent["type"]) => events.filter((e) => e.type === t).length;
  const drivers = s.drivers.map((d) => ({ d, ...driverSafety(s, d.id, range) })).filter((x) => x.km > 0).sort((a, b) => a.score - b.score);
  const avg = drivers.length ? Math.round(drivers.reduce((a, x) => a + x.score, 0) / drivers.length) : 0;
  const daily = dailySeries(s, range);
  const vn = (id: string) => s.vehicles.find((v) => v.id === id)?.name ?? id;
  const dn = (id: string) => s.drivers.find((d) => d.id === id)?.name ?? id;
  const pending = events.filter((e) => !e.acknowledged && (e.severity === "high" || e.severity === "critical"));
  const cameras = s.integrations.find((i) => i.category === "AI Dashcams");

  const cols: Column<SafetyEvent>[] = [
    { key: "time", header: "Time", cell: (e) => fmt.dateTime(e.time), sortValue: (e) => e.time, csv: (e) => e.time },
    { key: "type", header: "Type", cell: (e) => LABEL[e.type], sortValue: (e) => e.type },
    { key: "d", header: "Driver", cell: (e) => <button className="hover:underline" onClick={(ev) => { ev.stopPropagation(); nav(`/drivers/${e.driverId}`); }}>{dn(e.driverId)}</button>, sortValue: (e) => dn(e.driverId) },
    { key: "v", header: "Vehicle", cell: (e) => vn(e.vehicleId), sortValue: (e) => vn(e.vehicleId) },
    { key: "det", header: "Detail", cell: (e) => <span className="text-xs text-muted-foreground">{e.type === "speeding" ? `+${e.value} km/h over limit` : e.type === "excessive_idling" ? `${e.value} min idling` : `${e.value} g`} · {e.locationLabel}</span>, csv: (e) => `${e.value ?? ""} ${e.locationLabel}` },
    { key: "sev", header: "Severity", cell: (e) => <SeverityBadge severity={e.severity} />, sortValue: (e) => ["info", "low", "medium", "high", "critical"].indexOf(e.severity) },
    { key: "ack", header: "Review", cell: (e) => (e.acknowledged ? <span className="inline-flex items-center gap-1 text-xs text-emerald-700"><CheckCircle2 className="h-3.5 w-3.5" />Reviewed{e.reviewedBy ? ` · ${e.reviewedBy.split(" ")[0]}` : ""}</span> : <Button size="sm" variant="outline" onClick={(ev) => { ev.stopPropagation(); setReview(e); setNote(""); }}>Review</Button>), sortValue: (e) => (e.acknowledged ? 1 : 0) },
  ];

  return (
    <>
      <PageHeader title="Driver Safety" description="Events are derived from GPS speed and accelerometer thresholds on the tracker. No camera is connected, so there is no video evidence or AI distraction detection in this demo." />
      <DeviceLimitNotice>Harsh braking, harsh acceleration and cornering need an accelerometer feed your tracker does not send, and speeding against posted limits needs road speed-limit data. Speed alerts against a threshold you set arrive with the alert engine (next release).</DeviceLimitNotice>
      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
        <KpiCard label="Fleet safety score" value={String(avg)} sub={`${drivers.length} scored drivers`} icon={ShieldCheck} tone={avg >= 85 ? "success" : avg >= 70 ? "warning" : "destructive"} />
        <KpiCard label="Incidents" value={String(k.safety)} change={pctChange(k.safety, k.safetyPrev)} invert sub="vs prev." icon={OctagonAlert} tone={k.safety > k.safetyPrev ? "destructive" : "success"} />
        <KpiCard label="Speeding" value={String(count("speeding"))} sub={`above ${fmt.speed(s.settings.speedLimitKmh)}`} icon={Gauge} tone="warning" />
        <KpiCard label="Harsh braking" value={String(count("harsh_braking"))} icon={OctagonAlert} tone="warning" />
        <KpiCard label="Harsh acceleration" value={String(count("harsh_acceleration"))} icon={Zap} />
        <KpiCard label="Excessive idling" value={String(count("excessive_idling"))} sub={`> ${s.settings.idleThresholdMin} min`} icon={Timer} />
      </div>
      {pending.length > 0 && <Card className="mt-4 border-red-200 bg-red-50/40"><CardContent className="flex flex-wrap items-center justify-between gap-2 p-4 text-sm"><span><strong>{pending.length}</strong> high-severity incident{pending.length > 1 ? "s" : ""} awaiting review.</span><Button size="sm" onClick={() => { setReview(pending[0]); setNote(""); }}>Start review</Button></CardContent></Card>}
      <div className="mt-4 grid gap-4 lg:grid-cols-3">
        <ChartCard title="Incident timeline" description="Events per day in period" className="lg:col-span-2" height={200}>
          <BarChart data={daily}>{grid}{xAxis("date")}{yAxis(undefined, 28)}{tip()}<Bar dataKey="safety" name="Events" radius={[3, 3, 0, 0]}>{daily.map((d, i) => <Cell key={i} fill={d.safety >= 6 ? C.red : d.safety >= 3 ? C.amber : C.blue} />)}</Bar></BarChart>
        </ChartCard>
        <ChartCard title="Risk trend" description="Fleet average score by week (last 8 weeks)" height={200}>
          <LineChart data={Array.from({ length: 8 }, (_, i) => { const to = new Date(); to.setDate(to.getDate() - (7 - i) * 7); const from = new Date(to); from.setDate(from.getDate() - 6); const r = { preset: "7d" as const, from: from.toISOString(), to: to.toISOString() }; const sc = s.drivers.map((d) => driverSafety(s, d.id, r)).filter((x) => x.km > 0); return { week: from.toLocaleDateString("en-CA", { month: "short", day: "numeric" }), score: sc.length ? Math.round(sc.reduce((a, x) => a + x.score, 0) / sc.length) : 0 }; })}>{grid}{xAxis("week")}{yAxis(undefined, 28)}{tip()}<Line type="monotone" dataKey="score" name="Fleet score" stroke={C.blue} strokeWidth={2} dot={{ r: 3 }} /></LineChart>
        </ChartCard>
      </div>
      <div className="mt-4 grid gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2"><CardHeader className="pb-2"><CardTitle>Driver comparison</CardTitle><CardDescription>Lowest scores first · click to open the driver</CardDescription></CardHeader>
          <CardContent className="grid gap-2 sm:grid-cols-2">{drivers.slice(0, 8).map((x) => <button key={x.d.id} onClick={() => nav(`/drivers/${x.d.id}`)} className="flex items-center gap-3 rounded-md border p-2.5 text-left text-sm hover:bg-accent/40"><Avatar name={x.d.name} size="sm" /><div className="min-w-0 flex-1"><div className="truncate font-medium">{x.d.name}</div><div className="text-xs text-muted-foreground">{x.counts.speeding} spd · {x.counts.harsh_braking} brk · {x.counts.harsh_acceleration} acc · {fmt.dist(x.km)}</div></div><Badge variant={scoreTone(x.score)}>{x.score}</Badge></button>)}</CardContent></Card>
        <Card><CardHeader className="pb-2"><CardTitle className="flex items-center gap-2"><Video className="h-4 w-4 text-muted-foreground" />Video telematics</CardTitle><CardDescription>{cameras?.status === "connected" ? "Connected" : "Not connected"}</CardDescription></CardHeader>
          <CardContent className="space-y-3 text-sm">
            <div className="flex aspect-video items-center justify-center rounded-md border border-dashed bg-muted/40 text-xs text-muted-foreground">Event video appears here once an AI dashcam provider is connected</div>
            <ul className="space-y-1 text-xs text-muted-foreground"><li className="flex gap-2"><Lock className="mt-0.5 h-3.5 w-3.5" />Video stays with the camera provider; FleetPilot stores only event metadata and links.</li><li className="flex gap-2"><Lock className="mt-0.5 h-3.5 w-3.5" />Default retention 30 days; access limited to Fleet Manager and Company Owner roles; every view is audit-logged.</li></ul>
            <Button size="sm" variant="outline" className="w-full" onClick={() => nav("/integrations")}>Browse dashcam integrations</Button>
          </CardContent></Card>
      </div>
      <section className="mt-5"><h3 className="mb-2 text-sm font-semibold">Incidents</h3><DataTable rows={events} columns={cols} rowKey={(e) => e.id} exportName="safety-events" pageSize={12} dense initialSort={{ key: "time", dir: "desc" }} searchKeys={(e) => `${dn(e.driverId)} ${vn(e.vehicleId)} ${e.locationLabel} ${LABEL[e.type]}`}
        filters={[{ key: "type", label: "Type", options: Object.entries(LABEL).map(([value, label]) => ({ value, label })), predicate: (e, v) => e.type === v },
          { key: "sev", label: "Severity", options: ["critical", "high", "medium", "low"].map((v) => ({ value: v, label: v[0]!.toUpperCase() + v.slice(1) })), predicate: (e, v) => e.severity === v },
          { key: "rev", label: "Review", options: [{ value: "open", label: "Needs review" }, { value: "done", label: "Reviewed" }], predicate: (e, v) => (v === "open" ? !e.acknowledged : e.acknowledged) },
          { key: "driver", label: "Driver", options: s.drivers.map((d) => ({ value: d.id, label: d.name })), predicate: (e, v) => e.driverId === v }]} /></section>

      <Sheet open={!!review} onOpenChange={(o) => !o && setReview(undefined)}>
        <SheetContent>
          {review && (<>
            <SheetHeader><SheetTitle>Review incident</SheetTitle><SheetDescription>{LABEL[review.type]} · {fmt.dateTime(review.time)}</SheetDescription></SheetHeader>
            <div className="flex-1 space-y-4 overflow-y-auto p-5 text-sm">
              <div className="grid grid-cols-2 gap-3">
                <div><div className="text-xs text-muted-foreground">Driver</div><div className="font-medium">{dn(review.driverId)}</div></div>
                <div><div className="text-xs text-muted-foreground">Vehicle</div><div className="font-medium">{vn(review.vehicleId)}</div></div>
                <div><div className="text-xs text-muted-foreground">Severity</div><SeverityBadge severity={review.severity} /></div>
                <div><div className="text-xs text-muted-foreground">Measured</div><div>{review.type === "speeding" ? `+${review.value} km/h over ${fmt.speed(s.settings.speedLimitKmh)}` : review.type === "excessive_idling" ? `${review.value} min idling` : `${review.value} g`}</div></div>
                <div className="col-span-2"><div className="text-xs text-muted-foreground">Location</div><div>{review.locationLabel} · {review.position.lat.toFixed(4)}, {review.position.lng.toFixed(4)}</div></div>
              </div>
              <div className="flex aspect-video items-center justify-center rounded-md border border-dashed bg-muted/40 text-xs text-muted-foreground">No video — camera integration not connected</div>
              {review.tripId && <Button variant="outline" size="sm" onClick={() => nav(`/trips/${review.tripId}`)}>Open trip replay</Button>}
              <Field label="Review note (optional)"><Textarea value={note} onChange={(e) => setNote(e.target.value)} placeholder="Context, driver explanation, coaching agreed…" /></Field>
            </div>
            <div className="flex gap-2 border-t p-4">
              <Button className="flex-1" onClick={() => { actions.acknowledgeSafety(review.id, note || undefined); toast({ title: "Incident acknowledged" }); setReview(undefined); }}>Acknowledge</Button>
              <Button variant="outline" onClick={() => { actions.acknowledgeSafety(review.id, note || undefined); actions.addCoaching(review.driverId, `${LABEL[review.type]} on ${fmt.date(review.time)}`, note || "Discussed incident and expectations."); toast({ title: "Acknowledged and coaching logged" }); setReview(undefined); }}>Acknowledge + coach</Button>
            </div>
          </>)}
        </SheetContent>
      </Sheet>
    </>
  );
}
