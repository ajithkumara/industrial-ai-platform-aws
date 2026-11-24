/**
 * Simulated AI Fleet Assistant. Intent matching + the same metrics functions the
 * dashboards use, so answers always agree with the screens. Every answer carries
 * `sources` (which records) and `calc` (how the number was produced).
 *
 * To connect a real LLM: replace `answer()` with a call to a governed analytics
 * backend that exposes these same tool functions; keep the ChatMessage shape.
 */
import type { ChatMessage, FleetSnapshot } from "@/types";
import type { Fmt } from "./format";
import { allVehicleStats, driverSafety, makeRange, replacementReview, sum, tripsIn, fuelIn, monthlyCosts, safetyIn, previousRange } from "./metrics";
import { aiDailySummary } from "@/pages/Dashboard";

export const SUGGESTED = [
  "Which vehicle consumed the most fuel this month?",
  "Show me all vehicles with overdue maintenance",
  "Which driver has the lowest safety score?",
  "How much money did unnecessary idling cost us?",
  "Which vehicles travelled the most kilometres this week?",
  "Compare fuel expenses for the last two months",
  "Which vehicles should I consider replacing?",
  "Summarize yesterday's fleet operations",
];

const has = (q: string, ...words: string[]) => words.some((w) => q.includes(w));

export function answer(q: string, s: FleetSnapshot, fmt: Fmt): Omit<ChatMessage, "id" | "role" | "time"> {
  const ql = q.toLowerCase();
  const vn = (id: string) => s.vehicles.find((v) => v.id === id)?.name ?? id;
  const month = makeRange("month"), week = makeRange("7d"), thirty = makeRange("30d");

  if (has(ql, "replac")) {
    const r = replacementReview(s, allVehicleStats(s, thirty));
    return { text: r.length ? `${r.length} vehicle${r.length > 1 ? "s" : ""} meet the replacement-review criteria over the last 30 days: ${r.map((x) => `${x.vehicle.name} (${x.reasons.join(", ")})`).join("; ")}. Start with the oldest and highest cost per ${fmt.distUnit}; compare a 5-year TCO against a new ${r[0]?.vehicle.make} before deciding.` : "No vehicles meet the replacement-review criteria right now.", cards: r.slice(0, 3).map((x) => ({ label: x.vehicle.name, value: fmt.perDist(x.costPerKm), sub: `${x.vehicle.year} · ${fmt.dist(x.vehicle.odometerKm)}` })), sources: ["vehicles", "trips (30 d)", "fuel transactions", "maintenance records", "diagnostics"], calc: `Flag if age ≥ 8 yrs, or cost/${fmt.distUnit} > 1.5× fleet median with > 200 ${fmt.distUnit} driven, or ≥ 2 diagnostic codes, or odometer > 240,000 ${fmt.distUnit}.` };
  }
  if (has(ql, "idle", "idling")) {
    const st = allVehicleStats(s, thirty);
    const cost = sum(st.map((x) => x.idleCost)), mins = sum(st.map((x) => x.idleMin));
    const top = [...st].sort((a, b) => b.idleCost - a.idleCost).slice(0, 5);
    return { text: `Over the last 30 days the fleet idled for ${fmt.duration(mins)}, burning about ${fmt.vol(sum(st.map((x) => x.idleFuelL)))} of fuel, roughly ${fmt.money(cost)}. ${top[0] ? `${top[0].vehicle.name} alone accounts for ${fmt.money(top[0].idleCost)}.` : ""} An engine-off policy at job sites longer than 5 minutes would recover most of it.`, chart: { kind: "bar", data: top.map((x) => ({ name: x.vehicle.name, value: Math.round(x.idleCost) })), unit: s.settings.currency }, cards: [{ label: "Idle time", value: fmt.duration(mins) }, { label: "Estimated cost", value: fmt.money(cost) }, { label: "Idle fuel", value: fmt.vol(sum(st.map((x) => x.idleFuelL))) }], sources: ["trips (30 d)", "settings: idle fuel rate, fuel price"], calc: `idle minutes ÷ 60 × ${s.settings.idleFuelLPerHour} L/h × ${fmt.money2(s.settings.fuelPricePerL)}/L.` };
  }
  if (has(ql, "overdue", "maintenance due", "needs service", "service due")) {
    const od = s.maintenance.filter((m) => m.status === "overdue"), sched = s.maintenance.filter((m) => m.status === "scheduled").sort((a, b) => a.date.localeCompare(b.date));
    return { text: od.length ? `${od.length} vehicle${od.length > 1 ? "s are" : " is"} overdue: ${od.map((m) => `${vn(m.vehicleId)} (${m.type}, ${m.notes?.toLowerCase() ?? ""})`).join("; ")}. Next scheduled: ${sched.slice(0, 3).map((m) => `${vn(m.vehicleId)} ${m.type} on ${fmt.shortDate(m.date)}`).join(", ")}.` : `Nothing is overdue. ${sched.length} services are scheduled; the next is ${sched[0] ? `${vn(sched[0].vehicleId)} ${sched[0].type} on ${fmt.shortDate(sched[0].date)}` : "—"}.`, cards: od.map((m) => ({ label: vn(m.vehicleId), value: m.type, sub: m.notes })), sources: ["maintenance records", "vehicle odometers"], calc: "Overdue = next-service odometer below current odometer, or scheduled date in the past." };
  }
  if (has(ql, "lowest safety", "worst driver", "lowest score", "risk")) {
    const ranked = s.drivers.map((d) => ({ d, ...driverSafety(s, d.id, thirty) })).filter((x) => x.km > 0).sort((a, b) => a.score - b.score);
    const w = ranked[0];
    return { text: w ? `${w.d.name} has the lowest safety score at ${w.score}/100 over the last 30 days, with ${w.counts.harsh_braking} harsh-braking, ${w.counts.speeding} speeding and ${w.counts.harsh_acceleration} harsh-acceleration events across ${fmt.dist(w.km)}. The next lowest are ${ranked.slice(1, 3).map((x) => `${x.d.name} (${x.score})`).join(" and ")}.` : "No drivers have trips in the period.", chart: { kind: "bar", data: ranked.slice(0, 6).map((x) => ({ name: x.d.name.split(" ")[0]!, value: x.score })) }, sources: ["safety events (30 d)", "trips", "settings: safety weights"], calc: "100 − 1.8 × (weighted events per 100 km). Weights configurable in Settings." };
  }
  if (has(ql, "most fuel", "fuel consum", "burned the most")) {
    const st = allVehicleStats(s, month).sort((a, b) => b.fuelL - a.fuelL);
    const top = st[0];
    return { text: top ? `${top.vehicle.name} purchased the most fuel this month: ${fmt.vol(top.fuelL)} for ${fmt.money(top.fuelSpend)} over ${fmt.dist(top.distance)} (${fmt.economy(top.l100)}). ${st[1] ? `${st[1].vehicle.name} is second at ${fmt.vol(st[1].fuelL)}.` : ""}` : "No fuel transactions this month.", chart: { kind: "bar", data: st.slice(0, 6).map((x) => ({ name: x.vehicle.name, value: Math.round(x.fuelL) })), unit: fmt.volUnit }, sources: ["fuel transactions (this month)", "trips"], calc: "Sum of fuel-card litres per vehicle, month to date." };
  }
  if (has(ql, "most kilometres", "most km", "most miles", "travelled the most", "traveled the most", "furthest")) {
    const st = allVehicleStats(s, week).sort((a, b) => b.distance - a.distance);
    return { text: `This week ${st[0]?.vehicle.name} travelled the most, ${fmt.dist(st[0]?.distance ?? 0)} in ${st[0]?.trips} trips, followed by ${st.slice(1, 3).map((x) => `${x.vehicle.name} (${fmt.dist(x.distance)})`).join(" and ")}. Fleet total: ${fmt.dist(sum(st.map((x) => x.distance)))}.`, chart: { kind: "bar", data: st.slice(0, 8).map((x) => ({ name: x.vehicle.name, value: Math.round(x.distance) })), unit: fmt.distUnit }, sources: ["trips (last 7 days)"], calc: "Sum of trip distance per vehicle." };
  }
  if (has(ql, "compare fuel", "last two months", "fuel expenses")) {
    const m = monthlyCosts(s, 2);
    const [a, b] = m;
    const diff = a && b ? b.fuel - a.fuel : 0;
    return { text: a && b ? `Fuel spend was ${fmt.money(b.fuel)} in ${b.month} versus ${fmt.money(a.fuel)} in ${a.month}, ${diff >= 0 ? "up" : "down"} ${fmt.money(Math.abs(diff))} (${a.fuel ? Math.abs(Math.round((diff / a.fuel) * 100)) : 0}%). Note the current month is incomplete, so compare like for like before drawing conclusions.` : "Not enough history.", chart: { kind: "bar", data: m.map((x) => ({ name: x.month, value: x.fuel })), unit: s.settings.currency }, sources: ["fuel transactions"], calc: "Sum of fuel-card totals per calendar month." };
  }
  if (has(ql, "yesterday", "summar")) {
    const sm = aiDailySummary(s, fmt);
    return { text: `${sm.lines.join(" ")} ${sm.action}`, sources: ["trips (yesterday)", "safety events (7 d)", "maintenance records"], calc: "Aggregated from yesterday’s completed trips and this week’s safety events." };
  }
  if (has(ql, "cost the most", "most expensive", "highest cost", "costing")) {
    const st = allVehicleStats(s, thirty).filter((x) => x.distance > 50).sort((a, b) => b.costPerKm - a.costPerKm);
    return { text: `By cost per ${fmt.distUnit} over 30 days: ${st.slice(0, 3).map((x) => `${x.vehicle.name} ${fmt.perDist(x.costPerKm)}`).join(", ")}. By total operating spend: ${[...st].sort((a, b) => b.opCost - a.opCost).slice(0, 3).map((x) => `${x.vehicle.name} ${fmt.money(x.opCost)}`).join(", ")}.`, chart: { kind: "bar", data: st.slice(0, 6).map((x) => ({ name: x.vehicle.name, value: +x.costPerKm.toFixed(2) })), unit: `${s.settings.currency}/${fmt.distUnit}` }, sources: ["fuel transactions (30 d)", "maintenance records (30 d)", "trips"], calc: `(fuel + maintenance) ÷ distance per vehicle.` };
  }
  if (has(ql, "offline", "not reporting")) {
    const off = s.vehicles.filter((v) => v.status === "offline" && !v.archived);
    return { text: off.length ? `${off.map((v) => `${v.name} has not reported since ${fmt.dateTime(v.lastUpdate)}`).join("; ")}. Check that the OBD tracker is seated and the vehicle battery is healthy.` : "All vehicles are reporting.", sources: ["vehicle telemetry status"], calc: "Offline = no position update for more than 60 minutes." };
  }
  if (has(ql, "speeding", "speed")) {
    const ev = safetyIn(s, thirty).filter((e) => e.type === "speeding"), prev = safetyIn(s, previousRange(thirty)).filter((e) => e.type === "speeding");
    const by = Object.entries(ev.reduce((a, e) => ((a[e.driverId] = (a[e.driverId] ?? 0) + 1), a), {} as Record<string, number>)).sort((a, b) => b[1] - a[1]);
    return { text: `${ev.length} speeding events in the last 30 days (${prev.length} in the prior 30). ${by[0] ? `${s.drivers.find((d) => d.id === by[0]![0])?.name} has the most at ${by[0]![1]}.` : ""} The threshold is ${fmt.speed(s.settings.speedLimitKmh)}; change it in Settings → Fleet configuration.`, chart: { kind: "bar", data: by.slice(0, 6).map(([id, n]) => ({ name: s.drivers.find((d) => d.id === id)?.name.split(" ")[0] ?? id, value: n })) }, sources: ["safety events (30 d)"], calc: "Count of speeding events per driver." };
  }
  if (has(ql, "how many trips", "trips today", "trips this week")) {
    const r = ql.includes("today") ? makeRange("today") : week;
    const t = tripsIn(s, r);
    return { text: `${t.length} trips ${ql.includes("today") ? "today" : "this week"}, ${fmt.dist(sum(t.map((x) => x.distanceKm)))} in total, by ${new Set(t.map((x) => x.vehicleId)).size} vehicles.`, sources: ["trips"], calc: "Trips starting inside the period." };
  }
  if (has(ql, "fuel spend", "spent on fuel", "fuel cost")) {
    const f = fuelIn(s, thirty);
    return { text: `${fmt.money(sum(f.map((x) => x.totalCost)))} on ${fmt.vol(sum(f.map((x) => x.litres)))} across ${f.length} fuel-card transactions in the last 30 days.`, sources: ["fuel transactions (30 d)"], calc: "Sum of transaction totals." };
  }
  return { text: "I can answer questions about fuel, idling, maintenance, safety scores, distance, costs and vehicle replacement using the fleet’s own records. Try one of the suggested questions, or ask things like “which vehicle costs the most per km?” or “how many speeding events this month?”. A connected LLM backend will handle free-form questions here.", sources: [], calc: "No matching analysis for this question in the prototype." };
}
