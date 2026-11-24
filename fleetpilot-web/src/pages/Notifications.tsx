import * as React from "react";
import { useNavigate } from "react-router-dom";
import { Bell, CheckCheck, WifiOff, ShieldAlert, Hexagon, Wrench, AlertTriangle, Timer, Gauge, BatteryWarning, Settings as SettingsIcon, Info } from "lucide-react";
import { PageHeader, EmptyState } from "@/components/shared/PageHeader";
import { SeverityBadge } from "@/components/shared/StatusBadge";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useFleet } from "@/store/FleetStore";
import { cn } from "@/lib/utils";
import type { Notification, NotificationCategory, Severity } from "@/types";
import { AlertRulesCard } from "@/components/shared/AlertRulesCard";

export const CATEGORY_META: Record<NotificationCategory, { label: string; icon: React.ComponentType<{ className?: string }> }> = {
  vehicle_offline: { label: "Vehicle offline", icon: WifiOff }, unauthorized_movement: { label: "Unauthorized movement", icon: ShieldAlert }, geofence: { label: "Geofence entry/exit", icon: Hexagon },
  maintenance_due: { label: "Maintenance due", icon: Wrench }, diagnostic: { label: "Engine diagnostic", icon: AlertTriangle }, excessive_idling: { label: "Excessive idling", icon: Timer },
  speeding: { label: "Speeding", icon: Gauge }, safety_incident: { label: "Safety incident", icon: ShieldAlert }, low_battery: { label: "Low battery", icon: BatteryWarning }, system: { label: "System", icon: Info },
};

export default function NotificationsPage() {
  const { s, fmt, actions, mode } = useFleet();
  const nav = useNavigate();
  const [tab, setTab] = React.useState<"unread" | "all">("unread");
  const [sev, setSev] = React.useState<Severity | "all">("all");
  const [cat, setCat] = React.useState<NotificationCategory | "all">("all");
  const list = s.notifications.filter((n) => (tab === "all" || !n.read) && (sev === "all" || n.severity === sev) && (cat === "all" || n.category === cat));
  const unread = s.notifications.filter((n) => !n.read).length;
  const groups = groupByDay(list, fmt);
  const target = (n: Notification) => (n.category === "geofence" ? "/geofences" : n.category === "maintenance_due" ? "/maintenance" : n.category === "diagnostic" || n.category === "low_battery" ? "/health" : n.category === "vehicle_offline" ? `/vehicles/${n.vehicleId}` : n.vehicleId ? `/vehicles/${n.vehicleId}` : "/safety");

  return (
    <>
      <PageHeader title="Notifications" description={`${unread} unread · ${s.notifications.length} in the last 7 days`} actions={<><Button variant="outline" size="sm" onClick={() => nav("/settings?tab=notifications")}><SettingsIcon className="h-4 w-4" />Preferences</Button><Button size="sm" variant="outline" disabled={!unread} onClick={actions.markAllRead}><CheckCheck className="h-4 w-4" />Mark all read</Button></>} />
      {mode === "live" && <AlertRulesCard />}
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <Tabs value={tab} onValueChange={(v) => setTab(v as typeof tab)}><TabsList><TabsTrigger value="unread">Unread {unread > 0 && <Badge variant="destructive" className="ml-1.5">{unread}</Badge>}</TabsTrigger><TabsTrigger value="all">All history</TabsTrigger></TabsList></Tabs>
        <Select value={sev} onValueChange={(v) => setSev(v as typeof sev)}><SelectTrigger className="h-9 w-40 bg-card"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="all">All severities</SelectItem>{(["critical", "high", "medium", "low", "info"] as Severity[]).map((x) => <SelectItem key={x} value={x}>{x[0]!.toUpperCase() + x.slice(1)}</SelectItem>)}</SelectContent></Select>
        <Select value={cat} onValueChange={(v) => setCat(v as typeof cat)}><SelectTrigger className="h-9 w-52 bg-card"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="all">All categories</SelectItem>{(Object.keys(CATEGORY_META) as NotificationCategory[]).map((c) => <SelectItem key={c} value={c}>{CATEGORY_META[c].label}</SelectItem>)}</SelectContent></Select>
      </div>
      {list.length === 0 ? <EmptyState icon={Bell} title={tab === "unread" ? "You're all caught up" : "No notifications match"} description={tab === "unread" ? "New alerts will appear here as the fleet reports." : "Try a different severity or category."} /> : (
        <div className="space-y-5">
          {groups.map((g) => (
            <section key={g.label}>
              <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">{g.label}</div>
              <Card className="divide-y">
                {g.items.map((n) => { const M = CATEGORY_META[n.category]; return (
                  <div key={n.id} className={cn("flex items-start gap-3 p-3", !n.read && "bg-blue-50/40")}>
                    <div className={cn("mt-0.5 rounded-md p-2", n.severity === "critical" || n.severity === "high" ? "bg-red-50 text-red-600" : n.severity === "medium" ? "bg-amber-50 text-amber-600" : "bg-slate-100 text-slate-600")}><M.icon className="h-4 w-4" /></div>
                    <button className="min-w-0 flex-1 text-left" onClick={() => { actions.markNotification(n.id, true); nav(target(n)); }}>
                      <div className="flex flex-wrap items-center gap-2"><span className={cn("text-sm", !n.read && "font-semibold")}>{n.title}</span><SeverityBadge severity={n.severity} /><Badge variant="muted">{M.label}</Badge></div>
                      <div className="text-xs text-muted-foreground">{n.message}</div>
                      <div className="mt-0.5 text-[11px] text-muted-foreground">{fmt.time(n.time)} · {fmt.relative(n.time)}</div>
                    </button>
                    <Button size="sm" variant="ghost" className="text-xs" onClick={() => actions.markNotification(n.id, !n.read)}>{n.read ? "Mark unread" : "Mark read"}</Button>
                  </div>); })}
              </Card>
            </section>
          ))}
        </div>
      )}
    </>
  );
}

function groupByDay(items: Notification[], fmt: ReturnType<typeof useFleet>["fmt"]) {
  const today = new Date().toDateString(), y = new Date(Date.now() - 864e5).toDateString();
  const map = new Map<string, Notification[]>();
  for (const n of items) { const d = new Date(n.time).toDateString(); const label = d === today ? "Today" : d === y ? "Yesterday" : fmt.date(n.time); if (!map.has(label)) map.set(label, []); map.get(label)!.push(n); }
  return [...map.entries()].map(([label, items]) => ({ label, items }));
}
