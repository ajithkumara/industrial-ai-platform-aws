import * as React from "react";
import { Plug, CheckCircle2, Clock, Settings2, Search } from "lucide-react";
import { PageHeader, Field } from "@/components/shared/PageHeader";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { useFleet } from "@/store/FleetStore";
import { useToast } from "@/components/ui/toast";
import { cn } from "@/lib/utils";
import type { Integration } from "@/types";

const CATS = ["All", "Accounting", "Field Service", "Fuel Cards", "GPS Hardware", "AI Dashcams", "OEM Data", "Compliance", "EV Charging"] as const;

export default function IntegrationsPage() {
  const { s, actions } = useFleet();
  const { toast } = useToast();
  const [cat, setCat] = React.useState<(typeof CATS)[number]>("All");
  const [q, setQ] = React.useState("");
  const [cfg, setCfg] = React.useState<Integration | undefined>();
  const list = s.integrations.filter((i) => (cat === "All" || i.category === cat) && (!q || `${i.name} ${i.description}`.toLowerCase().includes(q.toLowerCase())));
  const connected = s.integrations.filter((i) => i.status === "connected").length;

  return (
    <>
      <PageHeader title="Integrations" description={`${connected} connected · Connect accounting, field-service, fuel-card and hardware systems. Cards marked “demo” simulate the connection flow only.`} demo={false} />
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <div className="relative"><Search className="pointer-events-none absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" /><Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search integrations" className="w-56 pl-8" /></div>
        <div className="flex flex-wrap gap-1">{CATS.map((c) => <button key={c} onClick={() => setCat(c)} className={cn("rounded-full border px-3 py-1 text-xs font-medium", cat === c ? "border-primary bg-primary text-primary-foreground" : "bg-card hover:bg-accent")}>{c}</button>)}</div>
      </div>
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {list.map((i) => (
          <Card key={i.id} className="flex flex-col">
            <CardContent className="flex flex-1 flex-col p-4">
              <div className="flex items-start justify-between gap-2">
                <div className="flex items-center gap-2.5"><div className="rounded-md bg-muted p-2"><Plug className="h-4 w-4 text-muted-foreground" /></div><div><div className="text-sm font-semibold">{i.name}</div><div className="text-xs text-muted-foreground">{i.category}</div></div></div>
                {i.status === "connected" ? <Badge variant="success"><CheckCircle2 className="h-3 w-3" />Connected</Badge> : i.status === "coming_soon" ? <Badge variant="muted"><Clock className="h-3 w-3" />Coming soon</Badge> : <Badge variant="info">Available</Badge>}
              </div>
              <p className="mt-3 flex-1 text-xs leading-5 text-muted-foreground">{i.description}</p>
              <div className="mt-3 flex items-center gap-2">
                {i.status === "connected" && <Button size="sm" variant="outline" onClick={() => setCfg(i)}><Settings2 className="h-3.5 w-3.5" />Configure</Button>}
                {i.status === "connected" && i.demo && <Button size="sm" variant="ghost" onClick={() => { actions.setIntegrationStatus(i.id, "available"); toast({ title: `${i.name} disconnected` }); }}>Disconnect</Button>}
                {i.status === "available" && <Button size="sm" onClick={() => setCfg(i)}>Connect</Button>}
                {i.status === "coming_soon" && <Button size="sm" variant="outline" onClick={() => toast({ title: "Added to waitlist", description: `We’ll notify ${s.users[0]?.email} when ${i.name} is available.`, tone: "info" })}>Notify me</Button>}
                {i.demo && <span className="ml-auto text-[10px] uppercase tracking-wide text-amber-700">demo</span>}
              </div>
            </CardContent>
          </Card>
        ))}
      </div>
      <Dialog open={!!cfg} onOpenChange={(o) => !o && setCfg(undefined)}>
        <DialogContent>
          {cfg && (<>
            <DialogHeader><DialogTitle>{cfg.status === "connected" ? `Configure ${cfg.name}` : `Connect ${cfg.name}`}</DialogTitle><DialogDescription>{cfg.demo ? "Demo connection: no credentials are sent anywhere and no external data is loaded." : "Device data arrives through the FleetPilot ingestion service; no credentials are required here."}</DialogDescription></DialogHeader>
            {cfg.category === "GPS Hardware" && !cfg.demo ? (
              <div className="space-y-3 text-sm">
                <div className="rounded-md border bg-muted/40 p-3 text-xs"><div className="font-medium">Ingestion endpoint</div><div className="font-mono">tcp://tracker.fleetpilot.example:5013</div><div className="mt-1 text-muted-foreground">Point each MP91 at this host/port (TCP, H02 protocol). Register the device ID under Vehicles → Edit to link it.</div></div>
                <Field label="Auto-create vehicles for unknown device IDs"><Switch defaultChecked={false} /></Field>
              </div>
            ) : (
              <div className="space-y-3">
                {cfg.category === "Accounting" && <><Field label="Company file"><Input placeholder="NorthStar Mechanical Services Inc." /></Field><Field label="Expense account for fuel"><Input placeholder="6210 · Vehicle fuel" /></Field><Field label="Sync frequency"><Input defaultValue="Nightly at 02:00" readOnly /></Field></>}
                {cfg.category === "Fuel Cards" && <><Field label="Account number"><Input placeholder="•••• •••• 4821" /></Field><Field label="Match transactions to vehicles by"><Input defaultValue="Card → vehicle mapping" readOnly /></Field></>}
                {cfg.category === "Field Service" && <><Field label="API key"><Input placeholder="Paste key from your account settings" type="password" /></Field><Field label="Create geofences from job addresses"><Switch defaultChecked /></Field></>}
                {cfg.category === "OEM Data" && <><Field label="Fleet account email"><Input placeholder="fleet@northstarmech.ca" /></Field><Field label="Import oil-life and fuel level"><Switch defaultChecked /></Field></>}
                {!["Accounting", "Fuel Cards", "Field Service", "OEM Data"].includes(cfg.category) && <Field label="Account"><Input placeholder="Provider account ID" /></Field>}
              </div>
            )}
            <DialogFooter><Button variant="outline" onClick={() => setCfg(undefined)}>Close</Button>{cfg.status !== "connected" && <Button onClick={() => { actions.setIntegrationStatus(cfg.id, "connected"); toast({ title: `${cfg.name} connected (demo)`, description: "Status updated. No external data is exchanged in the prototype." }); setCfg(undefined); }}>Connect</Button>}</DialogFooter>
          </>)}
        </DialogContent>
      </Dialog>
    </>
  );
}
