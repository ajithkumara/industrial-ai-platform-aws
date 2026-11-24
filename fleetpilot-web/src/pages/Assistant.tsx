import * as React from "react";
import { Sparkles, Send, Plus, MessageSquare, Database, Calculator, ChevronDown } from "lucide-react";
import { Bar, BarChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { PageHeader } from "@/components/shared/PageHeader";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { Avatar } from "@/components/ui/misc";
import { useFleet } from "@/store/FleetStore";
import { answer, SUGGESTED } from "@/lib/assistant";
import { C } from "@/components/shared/Charts";
import { uid, cn } from "@/lib/utils";
import { DeviceLimitNotice } from "@/components/shared/DeviceLimitNotice";
import type { ChatMessage, Conversation } from "@/types";

export default function AssistantPage() {
  const { s, fmt, actions } = useFleet();
  const [activeId, setActiveId] = React.useState<string | null>(s.conversations[0]?.id ?? null);
  const [input, setInput] = React.useState("");
  const [thinking, setThinking] = React.useState(false);
  const endRef = React.useRef<HTMLDivElement>(null);
  const conv = s.conversations.find((c) => c.id === activeId) ?? null;
  React.useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth" }); }, [conv?.messages.length, thinking]);

  const ask = (q: string) => {
    const text = q.trim(); if (!text || thinking) return;
    setInput("");
    let id = activeId;
    const user: ChatMessage = { id: uid("m"), role: "user", text, time: new Date().toISOString() };
    if (!conv) { id = uid("conv"); const c: Conversation = { id, title: text.slice(0, 60), started: new Date().toISOString(), messages: [user] }; actions.saveConversation(c); setActiveId(id); }
    else actions.appendMessage(id!, user);
    setThinking(true);
    setTimeout(() => { actions.appendMessage(id!, { id: uid("m"), role: "assistant", time: new Date().toISOString(), ...answer(text, s, fmt) }); setThinking(false); }, 650 + Math.random() * 500);
  };

  return (
    <>
      <PageHeader title="AI Fleet Assistant" description="Ask questions in plain language. Answers are computed from this fleet’s records with the same calculations as the dashboards." demo />
      <DeviceLimitNotice>The assistant is a preview. It answers from your vehicles and trips; questions about fuel, safety or maintenance have no data from your tracker yet.</DeviceLimitNotice>
      <div className="grid gap-4 lg:grid-cols-4">
        <Card className="hidden flex-col lg:flex" style={{ height: "calc(100vh - 13rem)" }}>
          <div className="flex items-center justify-between border-b p-3"><span className="text-sm font-semibold">Conversations</span><Button size="iconSm" variant="ghost" onClick={() => setActiveId(null)} aria-label="New conversation"><Plus className="h-4 w-4" /></Button></div>
          <div className="flex-1 overflow-y-auto p-2">
            {s.conversations.length === 0 && <div className="p-3 text-xs text-muted-foreground">No conversations yet.</div>}
            {s.conversations.map((c) => <button key={c.id} onClick={() => setActiveId(c.id)} className={cn("mb-1 flex w-full items-start gap-2 rounded-md px-2 py-2 text-left text-xs hover:bg-accent", activeId === c.id && "bg-accent")}><MessageSquare className="mt-0.5 h-3.5 w-3.5 shrink-0 text-muted-foreground" /><div className="min-w-0"><div className="truncate font-medium">{c.title}</div><div className="text-muted-foreground">{fmt.shortDate(c.started)} · {c.messages.length} messages</div></div></button>)}
          </div>
        </Card>
        <Card className="flex flex-col lg:col-span-3" style={{ height: "calc(100vh - 13rem)" }}>
          <div className="flex items-center gap-2 border-b px-4 py-3"><div className="rounded-md bg-brand/15 p-1.5"><Sparkles className="h-4 w-4 text-brand" /></div><div className="flex-1"><div className="text-sm font-semibold">FleetPilot Assistant</div><div className="text-xs text-muted-foreground">Simulated responses · governed analytics over your fleet data</div></div><Badge variant="warning">Simulated AI</Badge></div>
          <div className="flex-1 space-y-4 overflow-y-auto p-4">
            {!conv && (
              <div className="mx-auto max-w-xl py-8 text-center">
                <div className="mx-auto mb-3 w-fit rounded-full bg-brand/15 p-3"><Sparkles className="h-6 w-6 text-brand" /></div>
                <h2 className="text-base font-semibold">What would you like to know about your fleet?</h2>
                <p className="mt-1 text-sm text-muted-foreground">Every answer shows the records it used and how the number was calculated.</p>
                <div className="mt-5 grid gap-2 sm:grid-cols-2">{SUGGESTED.map((q) => <button key={q} onClick={() => ask(q)} className="rounded-md border bg-card px-3 py-2 text-left text-sm hover:bg-accent/50">{q}</button>)}</div>
              </div>
            )}
            {conv?.messages.map((m) => <Message key={m.id} m={m} fmt={fmt} />)}
            {thinking && <div className="flex items-center gap-2 text-xs text-muted-foreground"><span className="h-2 w-2 animate-bounce rounded-full bg-brand" /><span className="h-2 w-2 animate-bounce rounded-full bg-brand [animation-delay:120ms]" /><span className="h-2 w-2 animate-bounce rounded-full bg-brand [animation-delay:240ms]" />Analyzing fleet records…</div>}
            <div ref={endRef} />
          </div>
          {conv && <div className="flex gap-2 overflow-x-auto border-t px-4 py-2 scrollbar-none">{SUGGESTED.slice(0, 5).map((q) => <button key={q} onClick={() => ask(q)} className="shrink-0 rounded-full border px-3 py-1 text-xs hover:bg-accent">{q}</button>)}</div>}
          <form className="flex gap-2 border-t p-3" onSubmit={(e) => { e.preventDefault(); ask(input); }}>
            <Input value={input} onChange={(e) => setInput(e.target.value)} placeholder="Ask about fuel, idling, maintenance, safety, costs…" className="flex-1" />
            <Button type="submit" disabled={!input.trim() || thinking}><Send className="h-4 w-4" />Ask</Button>
          </form>
        </Card>
      </div>
    </>
  );
}

function Message({ m, fmt }: { m: ChatMessage; fmt: ReturnType<typeof useFleet>["fmt"] }) {
  const [open, setOpen] = React.useState(false);
  if (m.role === "user") return <div className="flex justify-end gap-2"><div className="max-w-[80%] rounded-2xl rounded-br-sm bg-primary px-4 py-2 text-sm text-primary-foreground">{m.text}</div><Avatar name="You" size="sm" /></div>;
  return (
    <div className="flex gap-2">
      <div className="mt-1 h-6 w-6 shrink-0 rounded-full bg-brand/15 p-1"><Sparkles className="h-4 w-4 text-brand" /></div>
      <div className="max-w-[85%] space-y-3">
        <div className="rounded-2xl rounded-bl-sm border bg-card px-4 py-3 text-sm leading-6 shadow-card">{m.text}</div>
        {m.cards && m.cards.length > 0 && <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">{m.cards.map((c, i) => <div key={i} className="rounded-md border bg-card p-2.5"><div className="text-[11px] text-muted-foreground">{c.label}</div><div className="text-sm font-semibold tabular">{c.value}</div>{c.sub && <div className="truncate text-[11px] text-muted-foreground">{c.sub}</div>}</div>)}</div>}
        {m.chart && m.chart.data.length > 0 && (
          <div className="rounded-md border bg-card p-3"><div className="h-40"><ResponsiveContainer width="100%" height="100%"><BarChart data={m.chart.data} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}><XAxis dataKey="name" tickLine={false} axisLine={false} tick={{ fontSize: 11 }} interval={0} /><YAxis tickLine={false} axisLine={false} width={36} tick={{ fontSize: 11 }} /><Tooltip contentStyle={{ fontSize: 12, borderRadius: 8 }} formatter={(v: number) => [`${v}${m.chart?.unit ? ` ${m.chart.unit}` : ""}`, ""]} /><Bar dataKey="value" fill={C.teal} radius={[3, 3, 0, 0]} /></BarChart></ResponsiveContainer></div></div>
        )}
        {(m.sources?.length || m.calc) && (
          <div className="text-xs">
            <button onClick={() => setOpen((o) => !o)} className="inline-flex items-center gap-1 text-muted-foreground hover:text-foreground"><ChevronDown className={cn("h-3 w-3 transition-transform", open && "rotate-180")} />Sources and calculation</button>
            {open && <div className="mt-2 space-y-1.5 rounded-md border bg-muted/40 p-3">{m.sources && m.sources.length > 0 && <div className="flex flex-wrap items-center gap-1.5"><Database className="h-3.5 w-3.5 text-muted-foreground" />{m.sources.map((sr) => <Badge key={sr} variant="muted">{sr}</Badge>)}</div>}{m.calc && <div className="flex items-start gap-1.5 text-muted-foreground"><Calculator className="mt-0.5 h-3.5 w-3.5 shrink-0" />{m.calc}</div>}<div className="text-[11px] text-muted-foreground">Generated {fmt.time(m.time)} · simulated assistant over demo data</div></div>}
          </div>
        )}
      </div>
    </div>
  );
}
