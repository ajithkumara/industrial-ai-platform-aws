import * as React from "react";
import { CheckCircle2, Info, AlertTriangle, X } from "lucide-react";
import { cn } from "@/lib/utils";

type Toast = { id: number; title: string; description?: string; tone?: "success" | "info" | "warning" };
const Ctx = React.createContext<{ toast: (t: Omit<Toast, "id">) => void } | null>(null);

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [items, setItems] = React.useState<Toast[]>([]);
  const toast = React.useCallback((t: Omit<Toast, "id">) => {
    const id = Date.now() + Math.random();
    setItems((s) => [...s, { ...t, id }]);
    setTimeout(() => setItems((s) => s.filter((x) => x.id !== id)), 4200);
  }, []);
  return (
    <Ctx.Provider value={{ toast }}>
      {children}
      <div className="pointer-events-none fixed bottom-4 right-4 z-[1400] flex w-80 flex-col gap-2">
        {items.map((t) => {
          const Icon = t.tone === "warning" ? AlertTriangle : t.tone === "info" ? Info : CheckCircle2;
          return (
            <div key={t.id} className="pointer-events-auto flex items-start gap-3 rounded-lg border bg-card p-3 shadow-pop animate-in slide-in-from-bottom-2 fade-in-0">
              <Icon className={cn("mt-0.5 h-4 w-4 shrink-0", t.tone === "warning" ? "text-warning" : t.tone === "info" ? "text-secondary" : "text-success")} />
              <div className="min-w-0 flex-1">
                <div className="text-sm font-medium">{t.title}</div>
                {t.description && <div className="text-xs text-muted-foreground">{t.description}</div>}
              </div>
              <button onClick={() => setItems((s) => s.filter((x) => x.id !== t.id))} className="text-muted-foreground hover:text-foreground"><X className="h-3.5 w-3.5" /></button>
            </div>
          );
        })}
      </div>
    </Ctx.Provider>
  );
}

export function useToast() {
  const ctx = React.useContext(Ctx);
  if (!ctx) throw new Error("useToast outside ToastProvider");
  return ctx;
}
