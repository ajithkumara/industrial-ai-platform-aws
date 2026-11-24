import type { Settings } from "@/types";

const KM_TO_MI = 0.621371, L_TO_GAL = 0.264172;

export function makeFormatter(s: Settings) {
  const locale = s.country === "US" ? "en-US" : "en-CA";
  const money = new Intl.NumberFormat(locale, { style: "currency", currency: s.currency, maximumFractionDigits: 0 });
  const money2 = new Intl.NumberFormat(locale, { style: "currency", currency: s.currency, maximumFractionDigits: 2 });
  const num = (n: number, d = 0) => new Intl.NumberFormat(locale, { maximumFractionDigits: d, minimumFractionDigits: d }).format(n);
  const dist = (km: number, d = 0) => (s.distanceUnit === "mi" ? `${num(km * KM_TO_MI, d)} mi` : `${num(km, d)} km`);
  const distValue = (km: number) => (s.distanceUnit === "mi" ? km * KM_TO_MI : km);
  const vol = (l: number, d = 0) => (s.volumeUnit === "gal" ? `${num(l * L_TO_GAL, d)} gal` : `${num(l, d)} L`);
  const speed = (kmh: number) => (s.distanceUnit === "mi" ? `${num(kmh * KM_TO_MI)} mph` : `${num(kmh)} km/h`);
  const temp = (c: number) => (s.tempUnit === "F" ? `${num(c * 9 / 5 + 32)} °F` : `${num(c)} °C`);
  const economy = (l100: number) => {
    if (!l100) return "—";
    return s.volumeUnit === "gal" ? `${num(235.215 / l100, 1)} mpg` : `${num(l100, 1)} L/100 km`;
  };
  const perDist = (perKm: number) => (s.distanceUnit === "mi" ? `${money2.format(perKm / KM_TO_MI)}/mi` : `${money2.format(perKm)}/km`);
  const dateOpts: Intl.DateTimeFormatOptions = { timeZone: s.timezone };
  const date = (iso: string) => {
    const d = new Date(iso);
    const y = d.toLocaleDateString("en-CA", { ...dateOpts, year: "numeric" }), m = d.toLocaleDateString("en-CA", { ...dateOpts, month: "2-digit" }), day = d.toLocaleDateString("en-CA", { ...dateOpts, day: "2-digit" });
    return s.dateFormat === "MM/DD/YYYY" ? `${m}/${day}/${y}` : s.dateFormat === "DD/MM/YYYY" ? `${day}/${m}/${y}` : `${y}-${m}-${day}`;
  };
  const time = (iso: string) => new Date(iso).toLocaleTimeString(locale, { ...dateOpts, hour: "numeric", minute: "2-digit" });
  const dateTime = (iso: string) => `${date(iso)} ${time(iso)}`;
  const shortDate = (iso: string) => new Date(iso).toLocaleDateString(locale, { ...dateOpts, month: "short", day: "numeric" });
  const relative = (iso: string, now = new Date()) => {
    const m = Math.round((now.getTime() - new Date(iso).getTime()) / 60000);
    if (m < 1) return "just now"; if (m < 60) return `${m} min ago`;
    const h = Math.round(m / 60); if (h < 24) return `${h} h ago`;
    const d = Math.round(h / 24); return d === 1 ? "yesterday" : `${d} days ago`;
  };
  const duration = (min: number) => { const h = Math.floor(min / 60), m = Math.round(min % 60); return h ? `${h} h ${m} m` : `${m} min`; };
  const pct = (n: number, d = 0) => `${num(n, d)}%`;
  const distUnit = s.distanceUnit, volUnit = s.volumeUnit;
  return { locale, money: (n: number) => money.format(n), money2: (n: number) => money2.format(n), num, dist, distValue, vol, speed, temp, economy, perDist, date, time, dateTime, shortDate, relative, duration, pct, distUnit, volUnit };
}

export type Fmt = ReturnType<typeof makeFormatter>;
