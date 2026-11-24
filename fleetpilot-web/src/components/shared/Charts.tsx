import * as React from "react";
import { ResponsiveContainer, Tooltip, CartesianGrid, XAxis, YAxis } from "recharts";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";

export const C = { navy: "#0f2a4a", blue: "#2563eb", teal: "#14b8a6", amber: "#d97706", red: "#dc2626", green: "#16a34a", slate: "#94a3b8", grid: "#e5e9f0" };

export function ChartCard({ title, description, children, className, actions, height = 240 }: { title: string; description?: string; children: React.ReactNode; className?: string; actions?: React.ReactNode; height?: number }) {
  return (
    <Card className={cn("flex flex-col", className)}>
      <CardHeader className="flex-row items-start justify-between space-y-0">
        <div><CardTitle>{title}</CardTitle>{description && <CardDescription className="mt-1">{description}</CardDescription>}</div>
        {actions}
      </CardHeader>
      <CardContent className="flex-1">
        <div style={{ height }}>
          <ResponsiveContainer width="100%" height="100%">{children as React.ReactElement}</ResponsiveContainer>
        </div>
      </CardContent>
    </Card>
  );
}

export const grid = <CartesianGrid vertical={false} stroke={C.grid} strokeDasharray="0" />;
export const xAxis = (key: string) => <XAxis dataKey={key} tickLine={false} axisLine={false} tickMargin={8} interval="preserveStartEnd" />;
export const yAxis = (fmt?: (v: number) => string, width = 40) => <YAxis tickLine={false} axisLine={false} width={width} tickFormatter={fmt} />;
export const tip = (fmt?: (v: number, name: string) => string) => (
  <Tooltip cursor={{ fill: "rgba(148,163,184,.12)" }} contentStyle={{ borderRadius: 8, border: "1px solid #e5e9f0", boxShadow: "0 8px 24px -8px rgb(16 24 40 / .18)", fontSize: 12 }} formatter={fmt ? (v: number, n: string) => [fmt(v, n), n] : undefined} />
);

export function Legend({ items }: { items: { color: string; label: string }[] }) {
  return (
    <div className="flex flex-wrap items-center gap-3 text-xs text-muted-foreground">
      {items.map((i) => <span key={i.label} className="inline-flex items-center gap-1.5"><span className="h-2 w-2 rounded-sm" style={{ background: i.color }} />{i.label}</span>)}
    </div>
  );
}
