import * as React from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { Bell, CalendarDays, HelpCircle, LogOut, Menu, Search, Settings, User, Truck, Users, Route, Hexagon, Building2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { Avatar } from "@/components/ui/misc";
import { Badge } from "@/components/ui/badge";
import { useFleet } from "@/store/FleetStore";
import { canSwitchMode, isDemo, switchMode } from "@/services/mode";
import { currentUser, logout } from "@/services/auth";
import { pageTitle } from "./Sidebar";
import type { DateRangePreset } from "@/types";
import { cn } from "@/lib/utils";

const PRESETS: { v: DateRangePreset; l: string }[] = [
  { v: "today", l: "Today" }, { v: "7d", l: "Last 7 days" }, { v: "30d", l: "Last 30 days" }, { v: "month", l: "This month" }, { v: "last_month", l: "Last month" }, { v: "90d", l: "Last 90 days" },
];

export function Topbar({ onMenu }: { onMenu: () => void }) {
  const { s, range, fleetFilter, actions, fmt } = useFleet();
  const loc = useLocation();
  const nav = useNavigate();
  const unread = s.notifications.filter((n) => !n.read).length;
  const [q, setQ] = React.useState("");
  const [open, setOpen] = React.useState(false);
  const boxRef = React.useRef<HTMLDivElement>(null);

  React.useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") { e.preventDefault(); boxRef.current?.querySelector("input")?.focus(); } };
    const onClick = (e: MouseEvent) => { if (!boxRef.current?.contains(e.target as Node)) setOpen(false); };
    window.addEventListener("keydown", onKey); window.addEventListener("mousedown", onClick);
    return () => { window.removeEventListener("keydown", onKey); window.removeEventListener("mousedown", onClick); };
  }, []);

  const results = React.useMemo(() => {
    const n = q.trim().toLowerCase();
    if (n.length < 2) return [];
    const out: { icon: React.ComponentType<{ className?: string }>; label: string; sub: string; to: string }[] = [];
    for (const v of s.vehicles) if (!v.archived && `${v.id} ${v.name} ${v.registration} ${v.make} ${v.model}`.toLowerCase().includes(n)) out.push({ icon: Truck, label: v.name, sub: `${v.registration} · ${v.make} ${v.model}`, to: `/vehicles/${v.id}` });
    for (const d of s.drivers) if (`${d.name} ${d.employeeId}`.toLowerCase().includes(n)) out.push({ icon: Users, label: d.name, sub: d.employeeId, to: `/drivers/${d.id}` });
    for (const g of s.geofences) if (`${g.name} ${g.address}`.toLowerCase().includes(n)) out.push({ icon: Hexagon, label: g.name, sub: g.address, to: `/geofences?focus=${g.id}` });
    for (const t of s.trips.slice(-400)) if (`${t.id} ${t.startLabel} ${t.endLabel}`.toLowerCase().includes(n)) out.push({ icon: Route, label: `${t.startLabel.split(" — ")[0]} → ${t.endLabel.split(" — ")[0]}`, sub: `${t.id} · ${fmt.shortDate(t.startTime)}`, to: `/trips/${t.id}` });
    return out.slice(0, 8);
  }, [q, s, fmt]);

  const fleets = [{ v: "all", l: "All vehicles" }, { v: "Cargo Van", l: "Cargo vans" }, { v: "Pickup Truck", l: "Pickup trucks" }, { v: "Service Truck", l: "Service trucks" }];

  return (
    <header className="sticky top-0 z-[900] flex h-14 items-center gap-3 border-b bg-card/95 px-4 backdrop-blur supports-[backdrop-filter]:bg-card/80">
      <Button variant="ghost" size="icon" className="lg:hidden" onClick={onMenu}><Menu className="h-5 w-5" /></Button>
      <h1 className="hidden text-sm font-semibold md:block">{pageTitle(loc.pathname)}</h1>
      <div ref={boxRef} className="relative ml-auto w-full max-w-xs md:ml-4 md:max-w-sm">
        <Search className="pointer-events-none absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
        <Input value={q} onChange={(e) => { setQ(e.target.value); setOpen(true); }} onFocus={() => setOpen(true)} placeholder="Search vehicles, drivers, trips…  (Ctrl K)" className="h-9 bg-muted/60 pl-8 focus-visible:bg-card" />
        {open && q.length >= 2 && (
          <div className="absolute left-0 right-0 top-10 overflow-hidden rounded-md border bg-popover shadow-pop animate-fade-in">
            {results.length === 0 ? <div className="px-3 py-3 text-xs text-muted-foreground">No matches for “{q}”.</div> : results.map((r, i) => (
              <button key={i} onClick={() => { nav(r.to); setOpen(false); setQ(""); }} className="flex w-full items-center gap-3 px-3 py-2 text-left hover:bg-accent">
                <r.icon className="h-4 w-4 text-muted-foreground" />
                <div className="min-w-0"><div className="truncate text-sm">{r.label}</div><div className="truncate text-xs text-muted-foreground">{r.sub}</div></div>
              </button>
            ))}
          </div>
        )}
      </div>
      <div className="hidden items-center gap-2 md:flex">
        <Select value={range.preset} onValueChange={(v) => actions.setRange(v as DateRangePreset)}>
          <SelectTrigger className="h-9 w-[150px] bg-card"><CalendarDays className="h-3.5 w-3.5 text-muted-foreground" /><SelectValue /></SelectTrigger>
          <SelectContent>{PRESETS.map((p) => <SelectItem key={p.v} value={p.v}>{p.l}</SelectItem>)}</SelectContent>
        </Select>
        <Select value={fleetFilter} onValueChange={actions.setFleetFilter}>
          <SelectTrigger className="h-9 w-[150px] bg-card"><Building2 className="h-3.5 w-3.5 text-muted-foreground" /><SelectValue /></SelectTrigger>
          <SelectContent>{fleets.map((f) => <SelectItem key={f.v} value={f.v}>{f.l}</SelectItem>)}</SelectContent>
        </Select>
      </div>
      <Button variant="ghost" size="icon" className="relative" onClick={() => nav("/notifications")} aria-label="Notifications">
        <Bell className="h-[18px] w-[18px]" />
        {unread > 0 && <span className="absolute right-1.5 top-1.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-red-500 px-1 text-[10px] font-semibold text-white">{unread}</span>}
      </Button>
      <DropdownMenu>
        <DropdownMenuTrigger asChild><Button variant="ghost" size="icon" aria-label="Help"><HelpCircle className="h-[18px] w-[18px]" /></Button></DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="w-64">
          <DropdownMenuLabel>{isDemo() ? "About demo mode" : "About your data"}</DropdownMenuLabel>
          {isDemo()
            ? <div className="px-2 pb-2 text-xs text-muted-foreground">All figures are <Badge variant="warning" className="mx-0.5">demo data</Badge> for NorthStar Mechanical Services. Vehicle positions are simulated, not live GPS.</div>
            : <div className="px-2 pb-2 text-xs text-muted-foreground">Everything shown comes from your own trackers. Figures your device cannot measure are marked “not available with this device”.</div>}
          {canSwitchMode() && <DropdownMenuItem onClick={() => switchMode(isDemo() ? "live" : "demo")}>{isDemo() ? "Back to my fleet" : "Explore demo data"}</DropdownMenuItem>}
          <DropdownMenuSeparator />
          <DropdownMenuItem onClick={() => nav("/settings")}><Settings />Settings</DropdownMenuItem>
          <DropdownMenuItem onClick={() => nav("/integrations")}>Connect real hardware</DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <button className={cn("flex items-center gap-2 rounded-md p-1 hover:bg-accent")}><Avatar name={s.users[0]?.name ?? currentUser()?.email ?? "User"} size="md" /></button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="w-56">
          <DropdownMenuLabel><div className="text-sm font-medium text-foreground">{isDemo() ? s.users[0]?.name : "Signed in"}</div><div className="text-xs font-normal">{isDemo() ? s.users[0]?.email : currentUser()?.email}</div></DropdownMenuLabel>
          <DropdownMenuSeparator />
          <DropdownMenuItem onClick={() => nav("/settings?tab=users")}><User />My account</DropdownMenuItem>
          <DropdownMenuItem onClick={() => nav("/settings?tab=billing")}>Billing & subscription</DropdownMenuItem>
          <DropdownMenuSeparator />
          <DropdownMenuItem onClick={() => (canSwitchMode() ? logout() : alert("Offline demo: there is no session to end."))}><LogOut />Sign out</DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    </header>
  );
}
