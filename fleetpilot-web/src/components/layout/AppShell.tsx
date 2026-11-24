import * as React from "react";
import { Outlet, useLocation } from "react-router-dom";
import { ErrorBoundary } from "@/components/shared/ErrorBoundary";
import { Sidebar } from "./Sidebar";
import { Topbar } from "./Topbar";
import { useFleetRaw } from "@/store/FleetStore";
import { Skeleton } from "@/components/ui/misc";
import { CalendarDays } from "lucide-react";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import type { DateRangePreset } from "@/types";
import { canSwitchMode, isDemo, switchMode } from "@/services/mode";
import { Button } from "@/components/ui/button";

export function AppShell() {
  const { snapshot, loading, range, actions } = useFleetRaw();
  const loc = useLocation();
  const [collapsed, setCollapsed] = React.useState(() => { try { return localStorage.getItem("fp.sidebar") === "1"; } catch { return false; } });
  const [mobileOpen, setMobileOpen] = React.useState(false);
  const toggle = () => setCollapsed((c) => { try { localStorage.setItem("fp.sidebar", c ? "0" : "1"); } catch { /* ignore */ } return !c; });

  if (loading || !snapshot) {
    return (
      <div className="flex h-screen">
        <div className="hidden w-60 bg-sidebar lg:block" />
        <div className="flex-1 p-6"><Skeleton className="mb-4 h-8 w-64" /><div className="grid grid-cols-4 gap-4">{Array.from({ length: 8 }).map((_, i) => <Skeleton key={i} className="h-24" />)}</div><Skeleton className="mt-4 h-72" /></div>
      </div>
    );
  }
  return (
    <div className="flex h-screen overflow-hidden">
      <Sidebar collapsed={collapsed} onToggle={toggle} mobileOpen={mobileOpen} onMobileClose={() => setMobileOpen(false)} />
      <div className="flex min-w-0 flex-1 flex-col">
        <Topbar onMenu={() => setMobileOpen(true)} />
        {isDemo() && (
          <div className="flex flex-wrap items-center gap-2 border-b border-amber-300 bg-amber-50 px-4 py-1.5 text-xs text-amber-900">
            <strong>Demo mode.</strong> You are viewing a sample fleet (NorthStar Mechanical). None of these vehicles, trips or costs are real.
            {canSwitchMode() && <Button size="sm" variant="outline" className="ml-auto h-7" onClick={() => switchMode("live")}>Back to my fleet</Button>}
          </div>
        )}
        <div className="flex items-center gap-2 border-b bg-card px-4 py-2 md:hidden">
          <CalendarDays className="h-3.5 w-3.5 text-muted-foreground" />
          <Select value={range.preset} onValueChange={(v) => actions.setRange(v as DateRangePreset)}>
            <SelectTrigger className="h-8 w-40"><SelectValue /></SelectTrigger>
            <SelectContent>
              {(["today", "7d", "30d", "month", "last_month", "90d"] as DateRangePreset[]).map((p) => <SelectItem key={p} value={p}>{{ today: "Today", "7d": "Last 7 days", "30d": "Last 30 days", month: "This month", last_month: "Last month", "90d": "Last 90 days" }[p]}</SelectItem>)}
            </SelectContent>
          </Select>
        </div>
        <main className="min-h-0 flex-1 overflow-y-auto">
          <div className="mx-auto w-full max-w-[1500px] px-4 py-5 sm:px-6 animate-fade-in">
            <ErrorBoundary resetKey={loc.pathname}><Outlet /></ErrorBoundary>
          </div>
        </main>
      </div>
    </div>
  );
}
