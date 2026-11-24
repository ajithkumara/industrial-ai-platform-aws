import * as React from "react";
import { ArrowDown, ArrowUp, ArrowUpDown, ChevronLeft, ChevronRight, Download, Search } from "lucide-react";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Checkbox } from "@/components/ui/misc";
import { cn, downloadCsv } from "@/lib/utils";

export interface Column<T> {
  key: string;
  header: string;
  cell: (row: T) => React.ReactNode;
  sortValue?: (row: T) => string | number;
  csv?: (row: T) => string | number;
  className?: string;
  width?: string;
  align?: "left" | "right";
}

export interface FilterDef<T> { key: string; label: string; options: { value: string; label: string }[]; predicate: (row: T, value: string) => boolean }

export function DataTable<T>({ rows, columns, rowKey, searchKeys, filters, pageSize = 10, onRowClick, exportName, toolbar, selectable, bulkActions, emptyText = "No records match the current filters.", dense, initialSort }: {
  rows: T[]; columns: Column<T>[]; rowKey: (r: T) => string; searchKeys?: (r: T) => string; filters?: FilterDef<T>[]; pageSize?: number;
  onRowClick?: (r: T) => void; exportName?: string; toolbar?: React.ReactNode; selectable?: boolean; bulkActions?: (ids: string[], clear: () => void) => React.ReactNode;
  emptyText?: string; dense?: boolean; initialSort?: { key: string; dir: "asc" | "desc" };
}) {
  const [q, setQ] = React.useState("");
  const [fv, setFv] = React.useState<Record<string, string>>({});
  const [sort, setSort] = React.useState<{ key: string; dir: "asc" | "desc" } | null>(initialSort ?? null);
  const [page, setPage] = React.useState(0);
  const [sel, setSel] = React.useState<Set<string>>(new Set());

  const filtered = React.useMemo(() => {
    let out = rows;
    if (q && searchKeys) { const n = q.toLowerCase(); out = out.filter((r) => searchKeys(r).toLowerCase().includes(n)); }
    for (const f of filters ?? []) { const v = fv[f.key]; if (v && v !== "all") out = out.filter((r) => f.predicate(r, v)); }
    if (sort) {
      const col = columns.find((c) => c.key === sort.key);
      const sv = col?.sortValue;
      if (sv) out = [...out].sort((a, b) => { const x = sv(a), y = sv(b); const c = typeof x === "number" && typeof y === "number" ? x - y : String(x).localeCompare(String(y)); return sort.dir === "asc" ? c : -c; });
    }
    return out;
  }, [rows, q, fv, sort, columns, filters, searchKeys]);

  const pages = Math.max(1, Math.ceil(filtered.length / pageSize));
  const cur = Math.min(page, pages - 1);
  const slice = filtered.slice(cur * pageSize, cur * pageSize + pageSize);
  React.useEffect(() => { setPage(0); }, [q, fv]);

  const toggleSort = (key: string) => setSort((s) => (s?.key === key ? (s.dir === "asc" ? { key, dir: "desc" } : null) : { key, dir: "asc" }));
  const exportCsv = () => downloadCsv(`${exportName ?? "export"}.csv`, filtered.map((r) => Object.fromEntries(columns.filter((c) => c.csv || c.sortValue).map((c) => [c.header, (c.csv ?? c.sortValue)!(r)]))));
  const allOnPage = slice.length > 0 && slice.every((r) => sel.has(rowKey(r)));

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        {searchKeys && (
          <div className="relative">
            <Search className="pointer-events-none absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
            <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search…" className="h-9 w-56 pl-8" />
          </div>
        )}
        {filters?.map((f) => (
          <Select key={f.key} value={fv[f.key] ?? "all"} onValueChange={(v) => setFv((s) => ({ ...s, [f.key]: v }))}>
            <SelectTrigger className="h-9 w-auto min-w-[9rem]"><SelectValue placeholder={f.label} /></SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All {f.label.toLowerCase()}</SelectItem>
              {f.options.map((o) => <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>)}
            </SelectContent>
          </Select>
        ))}
        <div className="ml-auto flex items-center gap-2">
          {selectable && sel.size > 0 && bulkActions && (
            <div className="flex items-center gap-2 rounded-md border bg-accent/50 px-2 py-1 text-xs">
              <span className="font-medium">{sel.size} selected</span>
              {bulkActions([...sel], () => setSel(new Set()))}
            </div>
          )}
          {toolbar}
          {exportName && <Button variant="outline" size="sm" onClick={exportCsv}><Download className="h-3.5 w-3.5" />Export CSV</Button>}
        </div>
      </div>
      <div className="overflow-hidden rounded-lg border bg-card">
        <Table>
          <TableHeader>
            <TableRow className="hover:bg-transparent">
              {selectable && <TableHead className="w-8"><Checkbox checked={allOnPage} onChange={() => setSel((s) => { const n = new Set(s); slice.forEach((r) => (allOnPage ? n.delete(rowKey(r)) : n.add(rowKey(r)))); return n; })} /></TableHead>}
              {columns.map((c) => (
                <TableHead key={c.key} className={cn(c.width, c.align === "right" && "text-right")}>
                  {c.sortValue ? (
                    <button className="inline-flex items-center gap-1 hover:text-foreground" onClick={() => toggleSort(c.key)}>
                      {c.header}
                      {sort?.key === c.key ? (sort.dir === "asc" ? <ArrowUp className="h-3 w-3" /> : <ArrowDown className="h-3 w-3" />) : <ArrowUpDown className="h-3 w-3 opacity-40" />}
                    </button>
                  ) : c.header}
                </TableHead>
              ))}
            </TableRow>
          </TableHeader>
          <TableBody>
            {slice.length === 0 && (
              <TableRow><TableCell colSpan={columns.length + (selectable ? 1 : 0)} className="py-10 text-center text-sm text-muted-foreground">{emptyText}</TableCell></TableRow>
            )}
            {slice.map((r) => {
              const k = rowKey(r);
              return (
                <TableRow key={k} className={cn(onRowClick && "cursor-pointer", dense && "[&>td]:py-1.5")} onClick={() => onRowClick?.(r)} data-state={sel.has(k) ? "selected" : undefined}>
                  {selectable && <TableCell onClick={(e) => e.stopPropagation()}><Checkbox checked={sel.has(k)} onChange={() => setSel((s) => { const n = new Set(s); n.has(k) ? n.delete(k) : n.add(k); return n; })} /></TableCell>}
                  {columns.map((c) => <TableCell key={c.key} className={cn(c.className, c.align === "right" && "text-right tabular")}>{c.cell(r)}</TableCell>)}
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
        <div className="flex items-center justify-between border-t px-3 py-2 text-xs text-muted-foreground">
          <span>{filtered.length === 0 ? "0 results" : `${cur * pageSize + 1}–${Math.min(filtered.length, (cur + 1) * pageSize)} of ${filtered.length}`}</span>
          <div className="flex items-center gap-1">
            <Button variant="ghost" size="iconSm" disabled={cur === 0} onClick={() => setPage(cur - 1)}><ChevronLeft className="h-4 w-4" /></Button>
            <span className="tabular">Page {cur + 1} / {pages}</span>
            <Button variant="ghost" size="iconSm" disabled={cur >= pages - 1} onClick={() => setPage(cur + 1)}><ChevronRight className="h-4 w-4" /></Button>
          </div>
        </div>
      </div>
    </div>
  );
}
