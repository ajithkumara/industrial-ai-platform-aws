import { Info } from "lucide-react";
import { isDemo } from "@/services/mode";

/** Live accounts only: says plainly which figures the current tracker cannot supply, instead of estimating them. */
export function DeviceLimitNotice({ children }: { children: React.ReactNode }) {
  if (isDemo()) return null;
  return (
    <div className="mb-4 flex items-start gap-2 rounded-lg border border-sky-200 bg-sky-50 p-3 text-sm text-sky-900">
      <Info className="mt-0.5 h-4 w-4 shrink-0" />
      <div><strong>Not available with this device.</strong> {children}</div>
    </div>
  );
}
