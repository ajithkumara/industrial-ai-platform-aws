import * as React from "react";
import { cn } from "@/lib/utils";

export const Separator = ({ className, vertical }: { className?: string; vertical?: boolean }) => (
  <div role="separator" className={cn("shrink-0 bg-border", vertical ? "h-full w-px" : "h-px w-full", className)} />
);

export const Skeleton = ({ className }: { className?: string }) => <div className={cn("animate-pulse rounded-md bg-muted", className)} />;

export const Progress = ({ value, className, tone = "secondary" }: { value: number; className?: string; tone?: "secondary" | "success" | "warning" | "destructive" | "brand" }) => (
  <div className={cn("h-1.5 w-full overflow-hidden rounded-full bg-muted", className)}>
    <div className={cn("h-full rounded-full transition-all", { secondary: "bg-secondary", success: "bg-success", warning: "bg-warning", destructive: "bg-destructive", brand: "bg-brand" }[tone])} style={{ width: `${Math.max(0, Math.min(100, value))}%` }} />
  </div>
);

export const Avatar = ({ name, src, className, size = "md" }: { name: string; src?: string; className?: string; size?: "sm" | "md" | "lg" }) => {
  const initials = name.split(/\s+/).filter(Boolean).slice(0, 2).map((p) => p[0]!.toUpperCase()).join("");
  const sz = { sm: "h-6 w-6 text-[10px]", md: "h-8 w-8 text-xs", lg: "h-12 w-12 text-sm" }[size];
  return src ? (
    <img src={src} alt={name} className={cn("rounded-full object-cover", sz, className)} />
  ) : (
    <div className={cn("flex shrink-0 items-center justify-center rounded-full bg-slate-200 font-semibold text-slate-700", sz, className)}>{initials}</div>
  );
};

export const Checkbox = React.forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(({ className, ...props }, ref) => (
  <input ref={ref} type="checkbox" role="checkbox" className={cn("h-4 w-4 rounded border-input text-secondary focus:ring-ring", className)} {...props} />
));
Checkbox.displayName = "Checkbox";
