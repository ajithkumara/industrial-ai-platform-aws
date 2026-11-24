import * as React from "react";
import { useFleetRaw } from "@/store/FleetStore";
import { dataMode } from "@/services/mode";
import { fetchLive } from "@/services/live";

/**
 * Hot path while a page that shows live vehicles is open: poll GET /live.
 * - Every poll tells the server "someone is watching", which is what makes the edge server push positions.
 * - 2 s while a vehicle is moving, 5 s otherwise (a parked car still reports via the normal 15 s snapshot).
 * - Paused while the browser tab is hidden, so nobody is "watching" a background tab.
 * Returns whether live (moving) data arrived on the last poll.
 */
export function useLivePolling(active = true): boolean {
  const { actions } = useFleetRaw();
  const [live, setLive] = React.useState(false);
  React.useEffect(() => {
    if (!active || dataMode() !== "live") return;
    let stop = false;
    let timer: number | undefined;
    const loop = async () => {
      let next = 5000;
      try {
        if (!document.hidden) {
          const r = await fetchLive();
          if (stop) return;
          actions.applyLive(r);
          const moving = r.vehicles.some((v) => v.live);
          setLive(moving);
          next = moving ? 2000 : 5000;
        }
      } catch {
        next = 10_000;
      }
      if (!stop) timer = window.setTimeout(loop, next);
    };
    void loop();
    return () => { stop = true; if (timer) window.clearTimeout(timer); };
  }, [active, actions]);
  return live;
}
