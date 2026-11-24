import * as React from "react";
import { useSearchParams } from "react-router-dom";
import { Building2, SlidersHorizontal, Users, Shield, CreditCard, Bell, Globe, Database, KeyRound, ScrollText, Plus, Trash2, RotateCcw, Copy } from "lucide-react";
import { PageHeader, Field, ConfirmDialog } from "@/components/shared/PageHeader";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Avatar } from "@/components/ui/misc";
import { useFleet } from "@/store/FleetStore";
import { useToast } from "@/components/ui/toast";
import { CATEGORY_META } from "./Notifications";
import { cn } from "@/lib/utils";
import { canSwitchMode, isDemo, switchMode } from "@/services/mode";
import type { NotificationCategory, Role, Settings } from "@/types";

const TABS = [
  { id: "company", label: "Company profile", icon: Building2 }, { id: "fleet", label: "Fleet configuration", icon: SlidersHorizontal }, { id: "users", label: "Users & permissions", icon: Users },
  { id: "roles", label: "Roles", icon: Shield }, { id: "billing", label: "Billing & subscription", icon: CreditCard }, { id: "notifications", label: "Notification preferences", icon: Bell },
  { id: "regional", label: "Units & regional", icon: Globe }, { id: "data", label: "Data retention", icon: Database }, { id: "api", label: "API keys", icon: KeyRound }, { id: "audit", label: "Audit log", icon: ScrollText },
] as const;
type TabId = (typeof TABS)[number]["id"];

const ROLES: { role: Role; description: string; perms: string[] }[] = [
  { role: "Super Admin", description: "FleetPilot staff. Cross-tenant support access, audit-logged.", perms: ["Everything", "Impersonate (logged)"] },
  { role: "Company Owner", description: "Full control of the company account.", perms: ["All data", "Billing", "Users & roles", "API keys", "Settings"] },
  { role: "Fleet Manager", description: "Runs day-to-day operations.", perms: ["Vehicles, drivers, trips", "Maintenance", "Safety review", "Reports", "Geofences"] },
  { role: "Dispatcher", description: "Live operations only.", perms: ["Live map", "Trips", "Geofences", "Notifications"] },
  { role: "Maintenance Manager", description: "Vehicle health and service.", perms: ["Vehicle health", "Maintenance", "Vehicle cost reports"] },
  { role: "Driver", description: "Own trips and safety score only.", perms: ["Own trips", "Own safety score", "Own coaching notes"] },
];
const TIMEZONES = ["America/Toronto", "America/Vancouver", "America/Edmonton", "America/Winnipeg", "America/Halifax", "America/New_York", "America/Chicago", "America/Denver", "America/Los_Angeles", "America/Phoenix"];
const SCOPES = ["vehicles:read", "trips:read", "drivers:read", "reports:read", "maintenance:write", "geofences:write"];

export default function SettingsPage() {
  const { s, fmt, actions } = useFleet();
  const { toast } = useToast();
  const [params, setParams] = useSearchParams();
  const tab = (TABS.find((t) => t.id === params.get("tab"))?.id ?? "company") as TabId;
  const set = (id: TabId) => setParams({ tab: id });
  const st = s.settings;
  const [draft, setDraft] = React.useState<Settings>(st);
  React.useEffect(() => setDraft(st), [st]);
  const dirty = JSON.stringify(draft) !== JSON.stringify(st);
  const save = () => { actions.updateSettings(draft); toast({ title: "Settings saved" }); };
  const d = <K extends keyof Settings>(k: K, v: Settings[K]) => setDraft((x) => ({ ...x, [k]: v }));

  return (
    <>
      <PageHeader title="Settings" description={s.settings.companyName} demo={false} actions={dirty ? <><Button variant="outline" size="sm" onClick={() => setDraft(st)}>Discard</Button><Button size="sm" onClick={save}>Save changes</Button></> : undefined} />
      <div className="grid gap-4 lg:grid-cols-5">
        <nav className="flex gap-1 overflow-x-auto lg:flex-col lg:overflow-visible scrollbar-none">
          {TABS.map((t) => <button key={t.id} onClick={() => set(t.id)} className={cn("flex shrink-0 items-center gap-2 rounded-md px-3 py-2 text-left text-sm hover:bg-accent", tab === t.id && "bg-card font-medium shadow-card")}><t.icon className="h-4 w-4 text-muted-foreground" />{t.label}</button>)}
        </nav>
        <div className="space-y-4 lg:col-span-4">
          {tab === "company" && <Card><CardHeader><CardTitle>Company profile</CardTitle><CardDescription>Shown on reports and invoices.</CardDescription></CardHeader>
            <CardContent className="grid gap-4 sm:grid-cols-2">
              <Field label="Company name"><Input value={draft.companyName} onChange={(e) => d("companyName", e.target.value)} /></Field>
              <Field label="Legal name"><Input value={draft.legalName} onChange={(e) => d("legalName", e.target.value)} /></Field>
              <Field label="Country"><Select value={draft.country} onValueChange={(v) => { const c = v as "CA" | "US"; setDraft((x) => ({ ...x, country: c, currency: c === "US" ? "USD" : "CAD", distanceUnit: c === "US" ? "mi" : "km", volumeUnit: c === "US" ? "gal" : "L", tempUnit: c === "US" ? "F" : "C", dateFormat: c === "US" ? "MM/DD/YYYY" : "YYYY-MM-DD", timezone: c === "US" ? "America/New_York" : "America/Toronto" })); }}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent><SelectItem value="CA">Canada</SelectItem><SelectItem value="US">United States</SelectItem></SelectContent></Select></Field>
              <Field label="Address" className="sm:col-span-2"><Input value={draft.address} onChange={(e) => d("address", e.target.value)} /></Field>
              <div className="sm:col-span-2 text-xs text-muted-foreground">Changing country switches currency, units, date format and time zone to that market’s defaults. Adjust individually under Units & regional.</div>
            </CardContent></Card>}

          {tab === "fleet" && <Card><CardHeader><CardTitle>Fleet configuration</CardTitle><CardDescription>Thresholds that drive alerts, idle cost and safety scores across every screen.</CardDescription></CardHeader>
            <CardContent className="grid gap-4 sm:grid-cols-2">
              <Field label={`Speeding threshold (${fmt.distUnit === "mi" ? "mph" : "km/h"})`} hint="Events above this speed count as speeding"><Input inputMode="numeric" value={Math.round(fmt.distValue(draft.speedLimitKmh))} onChange={(e) => d("speedLimitKmh", Math.round(Number(e.target.value) / (fmt.distUnit === "mi" ? 0.621371 : 1)))} /></Field>
              <Field label="Idle threshold (minutes)" hint="Idling longer than this creates an event"><Input inputMode="numeric" value={draft.idleThresholdMin} onChange={(e) => d("idleThresholdMin", Number(e.target.value))} /></Field>
              <Field label={`Fuel price (${s.settings.currency} per ${fmt.volUnit})`} hint="Used for idle-cost and consumption estimates"><Input inputMode="decimal" value={draft.fuelPricePerL} onChange={(e) => d("fuelPricePerL", Number(e.target.value))} /></Field>
              <Field label="Idle fuel burn (L per hour)" hint="Typical van 0.6–1.0 L/h"><Input inputMode="decimal" value={draft.idleFuelLPerHour} onChange={(e) => d("idleFuelLPerHour", Number(e.target.value))} /></Field>
              <Field label="Business hours start"><Input type="time" value={draft.businessHours.start} onChange={(e) => d("businessHours", { ...draft.businessHours, start: e.target.value })} /></Field>
              <Field label="Business hours end" hint="Ignition outside these hours triggers unauthorized-movement alerts"><Input type="time" value={draft.businessHours.end} onChange={(e) => d("businessHours", { ...draft.businessHours, end: e.target.value })} /></Field>
              <Field label="Working days" className="sm:col-span-2"><div className="flex gap-1">{["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"].map((n, i) => <button key={n} onClick={() => d("businessHours", { ...draft.businessHours, days: draft.businessHours.days.includes(i) ? draft.businessHours.days.filter((x) => x !== i) : [...draft.businessHours.days, i] })} className={cn("rounded-md border px-3 py-1 text-xs", draft.businessHours.days.includes(i) ? "border-primary bg-primary text-primary-foreground" : "bg-card")}>{n}</button>)}</div></Field>
              <div className="sm:col-span-2"><div className="mb-2 text-sm font-medium">Safety score weights</div><div className="grid grid-cols-2 gap-3 sm:grid-cols-5">{(Object.keys(draft.safetyWeights) as (keyof Settings["safetyWeights"])[]).map((k) => <Field key={k} label={k.replace("_", " ")}><Input inputMode="numeric" value={draft.safetyWeights[k]} onChange={(e) => d("safetyWeights", { ...draft.safetyWeights, [k]: Number(e.target.value) })} /></Field>)}</div><p className="mt-2 text-xs text-muted-foreground">Score = 100 − 1.8 × (Σ weight × events) ÷ km × 100, clamped to 0–100. Higher weight = larger penalty.</p></div>
            </CardContent></Card>}

          {tab === "users" && <UsersTab />}

          {tab === "roles" && <Card><CardHeader><CardTitle>Roles</CardTitle><CardDescription>Role-based access. Permissions are enforced by the API; the prototype shows the matrix.</CardDescription></CardHeader>
            <CardContent className="grid gap-3 sm:grid-cols-2">{ROLES.map((r) => <div key={r.role} className="rounded-md border p-3"><div className="flex items-center justify-between"><span className="text-sm font-semibold">{r.role}</span><Badge variant="muted">{s.users.filter((u) => u.role === r.role).length} users</Badge></div><div className="text-xs text-muted-foreground">{r.description}</div><ul className="mt-2 flex flex-wrap gap-1">{r.perms.map((p) => <li key={p} className="rounded bg-muted px-1.5 py-0.5 text-[11px]">{p}</li>)}</ul></div>)}</CardContent></Card>}

          {tab === "billing" && <BillingTab />}

          {tab === "notifications" && <Card><CardHeader><CardTitle>Notification preferences</CardTitle><CardDescription>Choose channels per alert category. SMS requires a verified phone number.</CardDescription></CardHeader>
            <CardContent className="p-0"><Table><TableHeader><TableRow><TableHead>Alert</TableHead><TableHead className="text-center">Email</TableHead><TableHead className="text-center">Push</TableHead><TableHead className="text-center">SMS</TableHead></TableRow></TableHeader>
              <TableBody>{(Object.keys(CATEGORY_META) as NotificationCategory[]).map((c) => <TableRow key={c}><TableCell className="text-sm">{CATEGORY_META[c].label}</TableCell>{(["email", "push", "sms"] as const).map((ch) => <TableCell key={ch} className="text-center"><Switch checked={draft.notificationPrefs[c][ch]} onCheckedChange={(v) => d("notificationPrefs", { ...draft.notificationPrefs, [c]: { ...draft.notificationPrefs[c], [ch]: v } })} /></TableCell>)}</TableRow>)}</TableBody></Table></CardContent></Card>}

          {tab === "regional" && <Card><CardHeader><CardTitle>Units & regional settings</CardTitle><CardDescription>Applied instantly to every number in the app after saving.</CardDescription></CardHeader>
            <CardContent className="grid gap-4 sm:grid-cols-2">
              <Field label="Currency"><Select value={draft.currency} onValueChange={(v) => d("currency", v as "CAD" | "USD")}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent><SelectItem value="CAD">CAD · Canadian dollar</SelectItem><SelectItem value="USD">USD · US dollar</SelectItem></SelectContent></Select></Field>
              <Field label="Distance"><Select value={draft.distanceUnit} onValueChange={(v) => d("distanceUnit", v as "km" | "mi")}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent><SelectItem value="km">Kilometres</SelectItem><SelectItem value="mi">Miles</SelectItem></SelectContent></Select></Field>
              <Field label="Volume"><Select value={draft.volumeUnit} onValueChange={(v) => d("volumeUnit", v as "L" | "gal")}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent><SelectItem value="L">Litres</SelectItem><SelectItem value="gal">US gallons</SelectItem></SelectContent></Select></Field>
              <Field label="Temperature"><Select value={draft.tempUnit} onValueChange={(v) => d("tempUnit", v as "C" | "F")}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent><SelectItem value="C">Celsius</SelectItem><SelectItem value="F">Fahrenheit</SelectItem></SelectContent></Select></Field>
              <Field label="Date format"><Select value={draft.dateFormat} onValueChange={(v) => d("dateFormat", v as Settings["dateFormat"])}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent><SelectItem value="YYYY-MM-DD">2026-11-09 (ISO / Canada)</SelectItem><SelectItem value="MM/DD/YYYY">11/09/2026 (US)</SelectItem><SelectItem value="DD/MM/YYYY">09/11/2026</SelectItem></SelectContent></Select></Field>
              <Field label="Time zone"><Select value={draft.timezone} onValueChange={(v) => d("timezone", v)}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent>{TIMEZONES.map((t) => <SelectItem key={t} value={t}>{t}</SelectItem>)}</SelectContent></Select></Field>
              <div className="sm:col-span-2 rounded-md border bg-muted/40 p-3 text-xs">Preview: {fmt.dist(1234.5, 1)} · {fmt.vol(85.2, 1)} · {fmt.temp(92)} · {fmt.money2(1.58)} · {fmt.dateTime(new Date().toISOString())}</div>
            </CardContent></Card>}

          {tab === "data" && <DataTab draft={draft} d={d} />}
          {tab === "api" && <ApiTab />}
          {tab === "audit" && <Card><CardHeader><CardTitle>Audit log</CardTitle><CardDescription>Every change made in FleetPilot, newest first. Retained for {s.settings.dataRetentionMonths} months.</CardDescription></CardHeader>
            <CardContent className="p-0"><Table><TableHeader><TableRow><TableHead>Time</TableHead><TableHead>User</TableHead><TableHead>Action</TableHead><TableHead>Target</TableHead></TableRow></TableHeader><TableBody>{s.audit.map((a) => <TableRow key={a.id}><TableCell className="whitespace-nowrap text-xs tabular">{fmt.dateTime(a.time)}</TableCell><TableCell className="text-sm">{a.actor}</TableCell><TableCell className="text-sm">{a.action}</TableCell><TableCell className="text-xs text-muted-foreground">{a.target}</TableCell></TableRow>)}</TableBody></Table></CardContent></Card>}
        </div>
      </div>
    </>
  );
}

function UsersTab() {
  const { s, fmt, actions } = useFleet();
  const { toast } = useToast();
  const [invite, setInvite] = React.useState(false);
  const [f, setF] = React.useState({ name: "", email: "", role: "Dispatcher" as Role });
  const [err, setErr] = React.useState("");
  return (
    <Card><CardHeader className="flex-row items-start justify-between space-y-0"><div><CardTitle>Users & permissions</CardTitle><CardDescription>{s.users.length} users</CardDescription></div><Button size="sm" onClick={() => setInvite(true)}><Plus className="h-4 w-4" />Invite user</Button></CardHeader>
      <CardContent className="p-0"><Table><TableHeader><TableRow><TableHead>User</TableHead><TableHead>Role</TableHead><TableHead>Last active</TableHead><TableHead>Status</TableHead><TableHead /></TableRow></TableHeader>
        <TableBody>{s.users.map((u) => <TableRow key={u.id}><TableCell><div className="flex items-center gap-2"><Avatar name={u.name} size="sm" /><div><div className="text-sm font-medium">{u.name}</div><div className="text-xs text-muted-foreground">{u.email}</div></div></div></TableCell>
          <TableCell><Select value={u.role} onValueChange={(v) => actions.updateUser(u.id, { role: v as Role })} disabled={u.id === "U-1"}><SelectTrigger className="h-8 w-44"><SelectValue /></SelectTrigger><SelectContent>{ROLES.filter((r) => r.role !== "Super Admin").map((r) => <SelectItem key={r.role} value={r.role}>{r.role}</SelectItem>)}</SelectContent></Select></TableCell>
          <TableCell className="text-xs text-muted-foreground">{fmt.relative(u.lastActive)}</TableCell><TableCell>{u.active ? <Badge variant="success">Active</Badge> : <Badge variant="muted">Deactivated</Badge>}</TableCell>
          <TableCell className="text-right">{u.id !== "U-1" && <Button size="sm" variant="ghost" onClick={() => actions.updateUser(u.id, { active: !u.active })}>{u.active ? "Deactivate" : "Reactivate"}</Button>}</TableCell></TableRow>)}</TableBody></Table></CardContent>
      <Dialog open={invite} onOpenChange={setInvite}><DialogContent className="max-w-sm"><DialogHeader><DialogTitle>Invite user</DialogTitle><DialogDescription>They receive an email to set a password (demo: user is added directly).</DialogDescription></DialogHeader>
        <Field label="Full name"><Input value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></Field>
        <Field label="Email" error={err}><Input value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} /></Field>
        <Field label="Role"><Select value={f.role} onValueChange={(v) => setF({ ...f, role: v as Role })}><SelectTrigger><SelectValue /></SelectTrigger><SelectContent>{ROLES.filter((r) => r.role !== "Super Admin").map((r) => <SelectItem key={r.role} value={r.role}>{r.role}</SelectItem>)}</SelectContent></Select></Field>
        <DialogFooter><Button variant="outline" onClick={() => setInvite(false)}>Cancel</Button><Button onClick={() => { if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(f.email)) { setErr("Enter a valid email"); return; } if (s.users.some((u) => u.email === f.email)) { setErr("Already a user"); return; } actions.addUser(f); toast({ title: "Invitation sent (demo)", description: f.email }); setInvite(false); setF({ name: "", email: "", role: "Dispatcher" }); setErr(""); }} disabled={!f.name.trim()}>Send invite</Button></DialogFooter></DialogContent></Dialog>
    </Card>
  );
}

function BillingTab() {
  const { s, fmt } = useFleet();
  const { toast } = useToast();
  const vehicles = s.vehicles.filter((v) => !v.archived).length;
  const price = s.settings.currency === "USD" ? 35 : 47;
  return (
    <div className="space-y-4">
      <Card><CardHeader><CardTitle>Subscription</CardTitle><CardDescription>Professional plan · billed monthly per active vehicle</CardDescription></CardHeader>
        <CardContent className="grid gap-4 sm:grid-cols-3">
          <div className="rounded-md border p-3"><div className="text-xs text-muted-foreground">Active vehicles</div><div className="text-2xl font-semibold tabular">{vehicles}</div></div>
          <div className="rounded-md border p-3"><div className="text-xs text-muted-foreground">Price per vehicle</div><div className="text-2xl font-semibold tabular">{fmt.money(price)}<span className="text-sm font-normal text-muted-foreground">/mo</span></div></div>
          <div className="rounded-md border p-3"><div className="text-xs text-muted-foreground">Next invoice (est.)</div><div className="text-2xl font-semibold tabular">{fmt.money(vehicles * price)}</div><div className="text-xs text-muted-foreground">+ tax · {fmt.date(new Date(new Date().getFullYear(), new Date().getMonth() + 1, 1).toISOString())}</div></div>
          <div className="sm:col-span-3 flex flex-wrap gap-2"><Button size="sm" variant="outline" onClick={() => toast({ title: "Billing portal not connected", description: "Stripe customer portal opens here in the hosted build.", tone: "info" })}>Manage payment method</Button><Button size="sm" variant="outline" onClick={() => toast({ title: "Plan change", description: "Starter ($19) · Professional ($35) · Business Intelligence ($49) per vehicle/month in USD.", tone: "info" })}>Change plan</Button></div>
        </CardContent></Card>
      <Card><CardHeader><CardTitle>Invoices</CardTitle></CardHeader><CardContent className="p-0"><Table><TableHeader><TableRow><TableHead>Date</TableHead><TableHead>Description</TableHead><TableHead className="text-right">Amount</TableHead><TableHead>Status</TableHead></TableRow></TableHeader><TableBody>{[1, 2, 3].map((i) => { const dt = new Date(new Date().getFullYear(), new Date().getMonth() - i, 1); return <TableRow key={i}><TableCell className="text-sm">{fmt.date(dt.toISOString())}</TableCell><TableCell className="text-sm">Professional · {vehicles} vehicles</TableCell><TableCell className="text-right tabular">{fmt.money(vehicles * price)}</TableCell><TableCell><Badge variant="success">Paid</Badge></TableCell></TableRow>; })}</TableBody></Table></CardContent></Card>
    </div>
  );
}

function DataTab({ draft, d }: { draft: Settings; d: <K extends keyof Settings>(k: K, v: Settings[K]) => void }) {
  const { actions } = useFleet();
  const { toast } = useToast();
  const [reset, setReset] = React.useState(false);
  return (
    <Card><CardHeader><CardTitle>Data retention</CardTitle><CardDescription>Location data is personal information under PIPEDA. Keep only what you need.</CardDescription></CardHeader>
      <CardContent className="space-y-4">
        <Field label="Retain trip and location history (months)" hint="Older data is purged automatically. Aggregated reports are kept."><Select value={String(draft.dataRetentionMonths)} onValueChange={(v) => d("dataRetentionMonths", Number(v))}><SelectTrigger className="w-48"><SelectValue /></SelectTrigger><SelectContent>{[3, 6, 13, 24, 36].map((m) => <SelectItem key={m} value={String(m)}>{m} months</SelectItem>)}</SelectContent></Select></Field>
        <div className="rounded-md border p-3 text-sm"><div className="font-medium">Data residency</div><div className="text-xs text-muted-foreground">All data is stored in AWS Canada (Central), ca-central-1. Video, when a camera provider is connected, stays with that provider.</div></div>
        <div className="rounded-md border p-3 text-sm"><div className="font-medium">Export or delete company data</div><div className="text-xs text-muted-foreground">Request a full export (CSV + JSON) or deletion. Requests are fulfilled within 30 days.</div><div className="mt-2 flex gap-2"><Button size="sm" variant="outline" onClick={() => toast({ title: "Export requested (demo)", description: "You'll receive a download link by email in the hosted build.", tone: "info" })}>Request export</Button></div></div>
        {isDemo() ? (<div className="rounded-md border border-amber-200 bg-amber-50/40 p-3 text-sm"><div className="font-medium">Reset demo data</div><div className="text-xs text-muted-foreground">Regenerates the NorthStar sample fleet and discards your local changes.</div><Button size="sm" variant="outline" className="mt-2" onClick={() => setReset(true)}><RotateCcw className="h-3.5 w-3.5" />Reset demo</Button></div>) : canSwitchMode() && <div className="rounded-md border p-3 text-sm"><div className="font-medium">Demo fleet</div><div className="text-xs text-muted-foreground">Explore every feature with a sample fleet. Your own data is not changed.</div><Button size="sm" variant="outline" className="mt-2" onClick={() => switchMode("demo")}>Explore demo data</Button></div>}
      </CardContent>
      <ConfirmDialog open={reset} onOpenChange={setReset} title="Reset demo data?" description="Vehicles, drivers, settings and every change you made in this browser will be replaced with the original sample fleet." confirmLabel="Reset" destructive onConfirm={() => { void actions.resetDemo().then(() => toast({ title: "Demo data reset" })); }} />
    </Card>
  );
}

function ApiTab() {
  const { s, fmt, actions } = useFleet();
  const { toast } = useToast();
  const [open, setOpen] = React.useState(false);
  const [name, setName] = React.useState(""); const [scopes, setScopes] = React.useState<string[]>(["vehicles:read"]);
  const [shown, setShown] = React.useState<string | null>(null);
  return (
    <Card><CardHeader className="flex-row items-start justify-between space-y-0"><div><CardTitle>API keys</CardTitle><CardDescription>Read fleet data from BI tools or your own systems. Keys are shown once.</CardDescription></div><Button size="sm" onClick={() => setOpen(true)}><Plus className="h-4 w-4" />Create key</Button></CardHeader>
      <CardContent className="p-0"><Table><TableHeader><TableRow><TableHead>Name</TableHead><TableHead>Key</TableHead><TableHead>Scopes</TableHead><TableHead>Created</TableHead><TableHead>Last used</TableHead><TableHead /></TableRow></TableHeader>
        <TableBody>{s.apiKeys.map((k) => <TableRow key={k.id}><TableCell className="text-sm font-medium">{k.name}</TableCell><TableCell className="font-mono text-xs">{k.prefix}••••••••</TableCell><TableCell><div className="flex flex-wrap gap-1">{k.scopes.map((sc) => <Badge key={sc} variant="muted">{sc}</Badge>)}</div></TableCell><TableCell className="text-xs">{fmt.date(k.created)}</TableCell><TableCell className="text-xs text-muted-foreground">{k.lastUsed ? fmt.relative(k.lastUsed) : "never"}</TableCell><TableCell className="text-right"><Button size="iconSm" variant="ghost" onClick={() => { actions.revokeApiKey(k.id); toast({ title: "Key revoked" }); }}><Trash2 className="h-4 w-4" /></Button></TableCell></TableRow>)}{s.apiKeys.length === 0 && <TableRow><TableCell colSpan={6} className="py-8 text-center text-sm text-muted-foreground">No API keys.</TableCell></TableRow>}</TableBody></Table></CardContent>
      <Dialog open={open} onOpenChange={(o) => { setOpen(o); if (!o) setShown(null); }}><DialogContent className="max-w-md">
        {shown ? (<><DialogHeader><DialogTitle>Copy your key now</DialogTitle><DialogDescription>It will not be shown again.</DialogDescription></DialogHeader><div className="flex items-center gap-2 rounded-md border bg-muted/40 p-2 font-mono text-xs">{shown}<Button size="iconSm" variant="ghost" className="ml-auto" onClick={() => { void navigator.clipboard?.writeText(shown); toast({ title: "Copied" }); }}><Copy className="h-4 w-4" /></Button></div><DialogFooter><Button onClick={() => { setOpen(false); setShown(null); }}>Done</Button></DialogFooter></>) : (<>
          <DialogHeader><DialogTitle>Create API key</DialogTitle></DialogHeader>
          <Field label="Name"><Input value={name} onChange={(e) => setName(e.target.value)} placeholder="Power BI reporting" /></Field>
          <Field label="Scopes"><div className="flex flex-wrap gap-1.5">{SCOPES.map((sc) => <button key={sc} onClick={() => setScopes((x) => (x.includes(sc) ? x.filter((y) => y !== sc) : [...x, sc]))} className={cn("rounded-full border px-2.5 py-1 text-xs", scopes.includes(sc) ? "border-primary bg-primary text-primary-foreground" : "bg-card")}>{sc}</button>)}</div></Field>
          <DialogFooter><Button variant="outline" onClick={() => setOpen(false)}>Cancel</Button><Button disabled={!name.trim() || !scopes.length} onClick={() => { const k = actions.addApiKey(name.trim(), scopes); setShown(`${k.prefix}_${Math.random().toString(36).slice(2)}${Math.random().toString(36).slice(2)}`); setName(""); }}>Create</Button></DialogFooter></>)}
      </DialogContent></Dialog>
    </Card>
  );
}
