import type { LucideIcon } from "lucide-react";
import { ArrowDownRight, ArrowUpRight, Minus } from "lucide-react";
import { Card } from "@/components/ui/card";
import { cn } from "@/lib/utils";

export function KpiCard({ label, value, sub, change, invert, icon: Icon, tone = "default", spark, onClick }: {
  label: string; value: string; sub?: string; change?: number; invert?: boolean; icon: LucideIcon;
  tone?: "default" | "success" | "warning" | "destructive" | "info"; spark?: number[]; onClick?: () => void;
}) {
  const up = (change ?? 0) > 0.5, down = (change ?? 0) < -0.5;
  const good = invert ? down : up, bad = invert ? up : down;
  const iconBg = { default: "bg-slate-100 text-slate-600", success: "bg-emerald-50 text-emerald-600", warning: "bg-amber-50 text-amber-600", destructive: "bg-red-50 text-red-600", info: "bg-blue-50 text-blue-600" }[tone];
  return (
    <Card className={cn("p-4 transition-shadow", onClick && "cursor-pointer hover:shadow-pop")} onClick={onClick} role={onClick ? "button" : undefined}>
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="truncate text-xs font-medium text-muted-foreground">{label}</div>
          <div className="mt-1 text-2xl font-semibold tabular tracking-tight">{value}</div>
        </div>
        <div className={cn("rounded-md p-2", iconBg)}><Icon className="h-4 w-4" /></div>
      </div>
      <div className="mt-2 flex items-center justify-between gap-2">
        <div className="flex items-center gap-1.5 text-xs">
          {change !== undefined && (
            <span className={cn("inline-flex items-center gap-0.5 rounded px-1 py-0.5 font-medium tabular", good ? "bg-emerald-50 text-emerald-700" : bad ? "bg-red-50 text-red-700" : "bg-slate-100 text-slate-600")}>
              {up ? <ArrowUpRight className="h-3 w-3" /> : down ? <ArrowDownRight className="h-3 w-3" /> : <Minus className="h-3 w-3" />}
              {Math.abs(change).toFixed(change !== 0 && Math.abs(change) < 10 ? 1 : 0)}%
            </span>
          )}
          {sub && <span className="truncate text-muted-foreground">{sub}</span>}
        </div>
        {spark && spark.length > 1 && <Sparkline data={spark} tone={good ? "#16a34a" : bad ? "#dc2626" : "#64748b"} />}
      </div>
    </Card>
  );
}

export function Sparkline({ data, tone = "#2563eb", w = 64, h = 20 }: { data: number[]; tone?: string; w?: number; h?: number }) {
  const max = Math.max(...data), min = Math.min(...data), span = max - min || 1;
  const pts = data.map((v, i) => `${(i / (data.length - 1)) * w},${h - ((v - min) / span) * (h - 2) - 1}`).join(" ");
  return (
    <svg width={w} height={h} className="shrink-0" aria-hidden>
      <polyline points={pts} fill="none" stroke={tone} strokeWidth="1.5" strokeLinejoin="round" strokeLinecap="round" />
    </svg>
  );
}
