import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-[11px] font-medium leading-4 transition-colors",
  {
    variants: {
      variant: {
        default: "border-transparent bg-primary text-primary-foreground",
        secondary: "border-transparent bg-accent text-accent-foreground",
        outline: "text-foreground",
        success: "border-transparent bg-emerald-50 text-emerald-700 ring-1 ring-inset ring-emerald-600/20",
        warning: "border-transparent bg-amber-50 text-amber-700 ring-1 ring-inset ring-amber-600/20",
        destructive: "border-transparent bg-red-50 text-red-700 ring-1 ring-inset ring-red-600/20",
        info: "border-transparent bg-blue-50 text-blue-700 ring-1 ring-inset ring-blue-600/20",
        muted: "border-transparent bg-slate-100 text-slate-600 ring-1 ring-inset ring-slate-500/20",
      },
    },
    defaultVariants: { variant: "default" },
  },
);

export interface BadgeProps extends React.HTMLAttributes<HTMLDivElement>, VariantProps<typeof badgeVariants> {}

function Badge({ className, variant, ...props }: BadgeProps) {
  return <div className={cn(badgeVariants({ variant }), className)} {...props} />;
}

export { Badge, badgeVariants };
