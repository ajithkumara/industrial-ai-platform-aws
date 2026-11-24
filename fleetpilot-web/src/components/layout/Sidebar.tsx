import * as React from "react";
import { NavLink, useLocation } from "react-router-dom";
import {
  LayoutDashboard, Map, Truck, Users, Route, Hexagon, HeartPulse, Wrench, Fuel, ShieldCheck, BarChart3, Sparkles, FileText,
  Plug, Bell, Settings, ChevronsLeft, ChevronsRight, X, type LucideIcon,
} from "lucide-react";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { Avatar } from "@/components/ui/misc";
import { cn } from "@/lib/utils";
import { useFleet } from "@/store/FleetStore";

export const NAV: { section: string; items: { to: string; label: string; icon: LucideIcon; badge?: "alerts" }[] }[] = [
  { section: "Overview", items: [{ to: "/", label: "Dashboard", icon: LayoutDashboard }, { to: "/map", label: "Live Fleet Map", icon: Map }] },
  { section: "Fleet operations", items: [{ to: "/vehicles", label: "Vehicles", icon: Truck }, { to: "/drivers", label: "Drivers", icon: Users }, { to: "/trips", label: "Trips & Routes", icon: Route }, { to: "/geofences", label: "Geofences", icon: Hexagon }] },
  { section: "Fleet intelligence", items: [{ to: "/health", label: "Vehicle Health", icon: HeartPulse }, { to: "/maintenance", label: "Maintenance", icon: Wrench }, { to: "/fuel", label: "Fuel & Expenses", icon: Fuel }, { to: "/safety", label: "Driver Safety", icon: ShieldCheck }, { to: "/analytics", label: "Fleet Analytics", icon: BarChart3 }] },
  { section: "AI & reporting", items: [{ to: "/assistant", label: "AI Fleet Assistant", icon: Sparkles }, { to: "/reports", label: "Reports", icon: FileText }] },
  { section: "Administration", items: [{ to: "/integrations", label: "Integrations", icon: Plug }, { to: "/notifications", label: "Notifications", icon: Bell, badge: "alerts" }, { to: "/settings", label: "Settings", icon: Settings }] },
];

export function pageTitle(pathname: string) {
  for (const g of NAV) for (const i of g.items) if (i.to === "/" ? pathname === "/" : pathname.startsWith(i.to)) return i.label;
  return "FleetPilot";
}

export function Logo({ compact }: { compact?: boolean }) {
  return (
    <div className="flex items-center gap-2.5">
      <svg viewBox="0 0 64 64" className="h-8 w-8 shrink-0" aria-hidden><rect width="64" height="64" rx="14" fill="#14b8a6" /><path d="M18 40 L32 16 L46 40 L32 33 Z" fill="#0f2a4a" /><circle cx="32" cy="46" r="4" fill="#fff" /></svg>
      {!compact && <div className="leading-tight"><div className="text-[15px] font-semibold tracking-tight text-white">FleetPilot</div><div className="text-[10px] uppercase tracking-wider text-sidebar-muted">Fleet operations</div></div>}
    </div>
  );
}

export function Sidebar({ collapsed, onToggle, mobileOpen, onMobileClose }: { collapsed: boolean; onToggle: () => void; mobileOpen: boolean; onMobileClose: () => void }) {
  const { s } = useFleet();
  const unread = s.notifications.filter((n) => !n.read).length;
  const loc = useLocation();
  React.useEffect(() => { onMobileClose(); /* close drawer on navigation */ }, [loc.pathname]); // eslint-disable-line react-hooks/exhaustive-deps
  const owner = s.users[0];

  const content = (compact: boolean) => (
    <div className="flex h-full flex-col">
      <div className={cn("flex h-14 items-center border-b border-sidebar-border px-4", compact && "justify-center px-0")}>
        <Logo compact={compact} />
        {mobileOpen && <button onClick={onMobileClose} className="ml-auto text-sidebar-muted lg:hidden"><X className="h-5 w-5" /></button>}
      </div>
      <nav className="flex-1 overflow-y-auto px-2 py-3 scrollbar-none">
        {NAV.map((g) => (
          <div key={g.section} className="mb-4">
            {!compact && <div className="px-2 pb-1.5 text-[10px] font-semibold uppercase tracking-wider text-sidebar-muted">{g.section}</div>}
            {compact && <div className="mx-auto mb-2 h-px w-6 bg-sidebar-border" />}
            {g.items.map((it) => {
              const link = (
                <NavLink key={it.to} to={it.to} end={it.to === "/"}
                  className={({ isActive }) => cn("group relative mb-0.5 flex items-center gap-2.5 rounded-md px-2 py-[7px] text-[13px] font-medium text-sidebar-foreground/90 transition-colors hover:bg-white/5 hover:text-white", isActive && "bg-sidebar-active text-white shadow-[inset_2px_0_0_0_#14b8a6]", compact && "justify-center px-0")}>
                  <it.icon className="h-4 w-4 shrink-0 opacity-90" />
                  {!compact && <span className="truncate">{it.label}</span>}
                  {it.badge === "alerts" && unread > 0 && (
                    <span className={cn("ml-auto rounded-full bg-red-500 px-1.5 text-[10px] font-semibold leading-4 text-white", compact && "absolute -right-0.5 -top-0.5 ml-0")}>{unread}</span>
                  )}
                </NavLink>
              );
              return compact ? (
                <Tooltip key={it.to}><TooltipTrigger asChild>{link}</TooltipTrigger><TooltipContent side="right">{it.label}</TooltipContent></Tooltip>
              ) : link;
            })}
          </div>
        ))}
      </nav>
      <div className={cn("border-t border-sidebar-border p-3", compact && "flex justify-center p-2")}>
        {compact ? <Avatar name={owner?.name ?? "User"} size="sm" /> : (
          <div className="flex items-center gap-2.5">
            <Avatar name={owner?.name ?? "User"} />
            <div className="min-w-0 flex-1 leading-tight">
              <div className="truncate text-[13px] font-medium text-white">{owner?.name}</div>
              <div className="truncate text-[11px] text-sidebar-muted">{owner?.role} · {s.settings.companyName}</div>
            </div>
          </div>
        )}
      </div>
      <button onClick={onToggle} className="hidden h-9 items-center justify-center border-t border-sidebar-border text-sidebar-muted hover:text-white lg:flex" aria-label="Toggle sidebar">
        {collapsed ? <ChevronsRight className="h-4 w-4" /> : <ChevronsLeft className="h-4 w-4" />}
      </button>
    </div>
  );

  return (
    <>
      <aside className={cn("hidden shrink-0 bg-sidebar text-sidebar-foreground transition-[width] duration-200 lg:block", collapsed ? "w-[60px]" : "w-60")}>{content(collapsed)}</aside>
      {mobileOpen && (
        <div className="fixed inset-0 z-[1000] lg:hidden">
          <div className="absolute inset-0 bg-slate-900/50" onClick={onMobileClose} />
          <aside className="absolute inset-y-0 left-0 w-64 bg-sidebar text-sidebar-foreground shadow-pop animate-in slide-in-from-left duration-200">{content(false)}</aside>
        </div>
      )}
    </>
  );
}
