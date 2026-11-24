import * as React from "react";
import { useNavigate, useParams } from "react-router-dom";
import { ArrowLeft, Pencil, MessageSquarePlus, Users } from "lucide-react";
import { Line, LineChart, Bar, BarChart, Cell } from "recharts";
import { PageHeader, Stat, EmptyState, Field } from "@/components/shared/PageHeader";
import { DriverStatusBadge, SeverityBadge } from "@/components/shared/StatusBadge";
import { DataTable, type Column } from "@/components/shared/DataTable";
import { ChartCard, C, grid, tip, xAxis, yAxis } from "@/components/shared/Charts";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Avatar } from "@/components/ui/misc";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input, Textarea } from "@/components/ui/input";
import { DriverDialog } from "@/components/forms/DriverForm";
import { useFleet } from "@/store/FleetStore";
import { useToast } from "@/components/ui/toast";
import { driverSafety, driverWeeklyScores, inRange, scoreTone, sum } from "@/lib/metrics";
import type { SafetyEvent, Trip } from "@/types";

const TYPE_LABEL: Record<SafetyEvent["type"], string> = { speeding: "Speeding", harsh_braking: "Harsh braking", harsh_acceleration: "Harsh acceleration", excessive_idling: "Excessive idling", distracted: "Distracted driving" };

export default function DriverDetailPage() {
  const { id } = useParams();
  const { s, fmt, range, actions } = useFleet();
  const nav = useNavigate();
  const { toast } = useToast();
  const d = s.drivers.find((x) => x.id === id);
  const [edit, setEdit] = React.useState(false);
  const [coach, setCoach] = React.useState(false);
  const [topic, setTopic] = React.useState(""); const [notes, setNotes] = React.useState("");
  if (!d) return <EmptyState icon={Users} title="Driver not found" action={<Button onClick={() => nav("/drivers")}>Back to drivers</Button>} />;

  const st = driverSafety(s, d.id, range);
  const weekly = driverWeeklyScores(s, d.id, 8);
  const vehicle = s.vehicles.find((v) => v.id === d.vehicleId);
  const trips = s.trips.filter((t) => t.driverId === d.id && inRange(t.startTime, range)).sort((a, b) => b.startTime.localeCompare(a.startTime));
  const events = s.safety.filter((e) => e.driverId === d.id && inRange(e.time, range)).sort((a, b) => b.time.localeCompare(a.time));
  const idleMin = sum(trips.map((t) => t.idleMin));
  const rank = s.drivers.map((x) => ({ id: x.id, score: driverSafety(s, x.id, range).score, km: driverSafety(s, x.id, range).km })).filter((x) => x.km > 0).sort((a, b) => b.score - a.score);
  const pos = rank.findIndex((x) => x.id === d.id) + 1;
  const w = s.settings.safetyWeights;

  const tripCols: Column<Trip>[] = [
    { key: "start", header: "Date", cell: (t) => <div><div>{fmt.shortDate(t.startTime)} {fmt.time(t.startTime)}</div><div className="text-xs text-muted-foreground">{s.vehicles.find((v) => v.id === t.vehicleId)?.name}</div></div>, sortValue: (t) => t.startTime },
    { key: "route", header: "Route", cell: (t) => <span className="text-xs">{t.startLabel.split(" — ")[0]} → {t.endLabel.split(" — ")[0]}</span> },
    { key: "dist", header: "Distance", cell: (t) => fmt.dist(t.distanceKm, 1), sortValue: (t) => t.distanceKm, align: "right" },
    { key: "dur", header: "Duration", cell: (t) => fmt.duration(t.durationMin), sortValue: (t) => t.durationMin, align: "right" },
    { key: "max", header: "Max speed", cell: (t) => fmt.speed(t.maxSpeedKmh), sortValue: (t) => t.maxSpeedKmh, align: "right" },
    { key: "ev", header: "Events", cell: (t) => { const n = s.safety.filter((e) => e.tripId === t.id).length; return n ? <Badge variant="warning">{n}</Badge> : <span className="text-xs text-muted-foreground">0</span>; }, sortValue: (t) => s.safety.filter((e) => e.tripId === t.id).length, align: "right" },
  ];
  const evCols: Column<SafetyEvent>[] = [
    { key: "time", header: "Time", cell: (e) => fmt.dateTime(e.time), sortValue: (e) => e.time },
    { key: "type", header: "Type", cell: (e) => TYPE_LABEL[e.type], sortValue: (e) => e.type },
    { key: "val", header: "Detail", cell: (e) => <span className="text-xs text-muted-foreground">{e.type === "speeding" ? `+${e.value} km/h over limit` : e.type === "excessive_idling" ? `${e.value} min` : `${e.value} g`} · {e.locationLabel}</span> },
    { key: "sev", header: "Severity", cell: (e) => <SeverityBadge severity={e.severity} />, sortValue: (e) => e.severity },
    { key: "ack", header: "Review", cell: (e) => (e.acknowledged ? <Badge variant="muted">Reviewed</Badge> : <Button size="sm" variant="outline" onClick={(ev) => { ev.stopPropagation(); actions.acknowledgeSafety(e.id); }}>Acknowledge</Button>) },
  ];

  return (
    <>
      <Button variant="ghost" size="sm" className="-ml-2 mb-2" onClick={() => nav("/drivers")}><ArrowLeft className="h-4 w-4" />Drivers</Button>
      <PageHeader title={d.name} description={`${d.employeeId} · Licence ${d.licenseClass} (expires ${fmt.date(d.licenseExpiry)}) · hired ${fmt.date(d.hireDate)}`}
        actions={<><Button variant="outline" size="sm" onClick={() => setEdit(true)}><Pencil className="h-4 w-4" />Edit</Button><Button size="sm" onClick={() => setCoach(true)}><MessageSquarePlus className="h-4 w-4" />Log coaching</Button></>} />

      <div className="grid gap-4 lg:grid-cols-3">
        <Card>
          <CardContent className="flex items-center gap-4 p-5">
            <Avatar name={d.name} size="lg" />
            <div className="flex-1"><div className="flex items-center gap-2"><span className="font-semibold">{d.name}</span><DriverStatusBadge status={d.status} /></div><div className="text-xs text-muted-foreground">{d.phone} · {d.email}</div>
              <div className="mt-1 text-xs">Vehicle: {vehicle ? <button className="font-medium hover:underline" onClick={() => nav(`/vehicles/${vehicle.id}`)}>{vehicle.name} · {vehicle.registration}</button> : <span className="text-muted-foreground">unassigned</span>}</div></div>
          </CardContent>
        </Card>
        <Card className="lg:col-span-2">
          <CardContent className="grid grid-cols-2 gap-3 p-4 sm:grid-cols-4">
            <div className="col-span-2 flex items-center gap-4 rounded-md border p-3 sm:col-span-1 sm:flex-col sm:items-start">
              <div><div className="text-[11px] uppercase tracking-wide text-muted-foreground">Safety score</div><div className="text-3xl font-semibold tabular">{st.km ? st.score : "—"}</div></div>
              <Badge variant={scoreTone(st.score)}>{pos ? `#${pos} of ${rank.length}` : "no trips"}</Badge>
            </div>
            <Stat label="Distance" value={fmt.dist(st.km)} sub={`${st.trips} trips`} className="border-0 bg-muted/40" />
            <Stat label="Events / 100 km" value={st.km ? (st.events / st.km * 100).toFixed(1) : "—"} sub={`${st.events} total`} className="border-0 bg-muted/40" />
            <Stat label="Idle time" value={fmt.duration(idleMin)} sub={`≈ ${fmt.money2((idleMin / 60) * s.settings.idleFuelLPerHour * s.settings.fuelPricePerL)} fuel`} className="border-0 bg-muted/40" />
          </CardContent>
        </Card>
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-3">
        <ChartCard title="Weekly score trend" description="Last 8 weeks" height={200}>
          <LineChart data={weekly}>{grid}{xAxis("week")}{yAxis(undefined, 28)}{tip()}<Line type="monotone" dataKey="score" name="Score" stroke={C.blue} strokeWidth={2} dot={{ r: 3 }} /></LineChart>
        </ChartCard>
        <ChartCard title="Driving behaviour" description={`Weights: speeding ×${w.speeding}, braking ×${w.harsh_braking}, acceleration ×${w.harsh_acceleration}, idling ×${w.excessive_idling}`} height={200}>
          <BarChart data={[{ n: "Speeding", v: st.counts.speeding }, { n: "Braking", v: st.counts.harsh_braking }, { n: "Acceleration", v: st.counts.harsh_acceleration }, { n: "Idling", v: st.counts.excessive_idling }]}>{grid}{xAxis("n")}{yAxis(undefined, 28)}{tip()}
            <Bar dataKey="v" name="Events" radius={[3, 3, 0, 0]}>{[C.red, C.amber, C.blue, C.slate].map((c, i) => <Cell key={i} fill={c} />)}</Bar></BarChart>
        </ChartCard>
        <Card>
          <CardHeader className="pb-2"><CardTitle>Coaching history</CardTitle><CardDescription>{d.coaching.length} sessions</CardDescription></CardHeader>
          <CardContent className="space-y-2 text-sm">
            {d.coaching.length === 0 && <div className="text-xs text-muted-foreground">No coaching recorded. Use “Log coaching” after a conversation.</div>}
            {d.coaching.map((c) => <div key={c.id} className="rounded-md border p-2.5"><div className="flex items-center justify-between"><span className="font-medium">{c.topic}</span><span className="text-xs text-muted-foreground">{fmt.date(c.date)}</span></div><div className="text-xs text-muted-foreground">{c.notes}</div><div className="mt-1 text-[11px] text-muted-foreground">Coach: {c.coach}</div></div>)}
          </CardContent>
        </Card>
      </div>

      <p className="mt-4 text-xs text-muted-foreground">Scores are calculated from available telemetry (GPS speed and accelerometer-derived events) using the configurable rules in Settings → Fleet configuration. They are a coaching aid, not a legal record.</p>

      <section className="mt-4"><h3 className="mb-2 text-sm font-semibold">Safety events</h3><DataTable rows={events} columns={evCols} rowKey={(e) => e.id} exportName={`${d.id}-events`} pageSize={8} dense initialSort={{ key: "time", dir: "desc" }} filters={[{ key: "type", label: "Type", options: Object.entries(TYPE_LABEL).map(([value, label]) => ({ value, label })), predicate: (e, v) => e.type === v }]} /></section>
      <section className="mt-6"><h3 className="mb-2 text-sm font-semibold">Trip history</h3><DataTable rows={trips} columns={tripCols} rowKey={(t) => t.id} onRowClick={(t) => nav(`/trips/${t.id}`)} exportName={`${d.id}-trips`} pageSize={8} dense initialSort={{ key: "start", dir: "desc" }} /></section>

      <DriverDialog open={edit} onOpenChange={setEdit} driver={d} />
      <Dialog open={coach} onOpenChange={setCoach}><DialogContent><DialogHeader><DialogTitle>Log coaching session</DialogTitle></DialogHeader>
        <Field label="Topic"><Input value={topic} onChange={(e) => setTopic(e.target.value)} placeholder="Following distance, idling, speed on QEW…" /></Field>
        <Field label="Notes"><Textarea value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="What was discussed and agreed" /></Field>
        <DialogFooter><Button variant="outline" onClick={() => setCoach(false)}>Cancel</Button><Button disabled={!topic.trim()} onClick={() => { actions.addCoaching(d.id, topic.trim(), notes.trim()); toast({ title: "Coaching logged" }); setTopic(""); setNotes(""); setCoach(false); }}>Save</Button></DialogFooter></DialogContent></Dialog>
    </>
  );
}
