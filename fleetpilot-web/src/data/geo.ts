import type { LatLng } from "@/types";

/** Named places around the GTA used by the demo generator. Coordinates are approximate town centres. */
export const PLACES: { name: string; pos: LatLng; kind: "depot" | "customer" | "supplier" | "town" }[] = [
  { name: "NorthStar Depot — Speers Rd, Oakville", pos: { lat: 43.4354, lng: -79.7085 }, kind: "depot" },
  { name: "Burlington — Appleby Line", pos: { lat: 43.3856, lng: -79.7693 }, kind: "town" },
  { name: "Burlington — Plains Rd", pos: { lat: 43.3302, lng: -79.8262 }, kind: "town" },
  { name: "Oakville — Glen Abbey", pos: { lat: 43.4316, lng: -79.7285 }, kind: "town" },
  { name: "Oakville — Bronte", pos: { lat: 43.3949, lng: -79.7118 }, kind: "town" },
  { name: "Oakville — Joshua Creek", pos: { lat: 43.4890, lng: -79.6630 }, kind: "town" },
  { name: "Mississauga — Erin Mills", pos: { lat: 43.5581, lng: -79.7138 }, kind: "town" },
  { name: "Mississauga — Port Credit", pos: { lat: 43.5520, lng: -79.5860 }, kind: "town" },
  { name: "Mississauga — Meadowvale", pos: { lat: 43.5967, lng: -79.7487 }, kind: "town" },
  { name: "Mississauga — Square One", pos: { lat: 43.5930, lng: -79.6440 }, kind: "town" },
  { name: "Milton — Derry Rd", pos: { lat: 43.5183, lng: -79.8774 }, kind: "town" },
  { name: "Milton — Main St", pos: { lat: 43.5120, lng: -79.8830 }, kind: "town" },
  { name: "Hamilton — Stoney Creek", pos: { lat: 43.2176, lng: -79.7636 }, kind: "town" },
  { name: "Hamilton — Westdale", pos: { lat: 43.2614, lng: -79.9087 }, kind: "town" },
  { name: "Toronto — Etobicoke", pos: { lat: 43.6205, lng: -79.5132 }, kind: "town" },
  { name: "Toronto — Liberty Village", pos: { lat: 43.6383, lng: -79.4186 }, kind: "town" },
  { name: "Toronto — North York", pos: { lat: 43.7615, lng: -79.4111 }, kind: "town" },
  { name: "Georgetown", pos: { lat: 43.6468, lng: -79.9280 }, kind: "town" },
  { name: "Wolseley Supply — Mississauga", pos: { lat: 43.6020, lng: -79.6880 }, kind: "supplier" },
  { name: "Noble Plumbing Supply — Burlington", pos: { lat: 43.3700, lng: -79.7920 }, kind: "supplier" },
];

export const CUSTOMER_SITES: { name: string; pos: LatLng; address: string }[] = [
  { name: "Oakville Place Mall", pos: { lat: 43.4549, lng: -79.6790 }, address: "240 Leighland Ave, Oakville, ON" },
  { name: "Burlington Mall", pos: { lat: 43.3600, lng: -79.7816 }, address: "777 Guelph Line, Burlington, ON" },
  { name: "Milton District Hospital", pos: { lat: 43.5247, lng: -79.8720 }, address: "725 Bronte St S, Milton, ON" },
  { name: "Sheridan College — Trafalgar", pos: { lat: 43.4689, lng: -79.6990 }, address: "1430 Trafalgar Rd, Oakville, ON" },
  { name: "Erin Mills Town Centre", pos: { lat: 43.5586, lng: -79.7137 }, address: "5100 Erin Mills Pkwy, Mississauga, ON" },
  { name: "Mapleview Centre", pos: { lat: 43.3305, lng: -79.8186 }, address: "900 Maple Ave, Burlington, ON" },
];

const R = 6371;
export function haversineKm(a: LatLng, b: LatLng) {
  const p = Math.PI / 180;
  const dLat = (b.lat - a.lat) * p, dLng = (b.lng - a.lng) * p;
  const x = Math.sin(dLat / 2) ** 2 + Math.cos(a.lat * p) * Math.cos(b.lat * p) * Math.sin(dLng / 2) ** 2;
  return 2 * R * Math.asin(Math.sqrt(x));
}

export function bearing(a: LatLng, b: LatLng) {
  const p = Math.PI / 180;
  const y = Math.sin((b.lng - a.lng) * p) * Math.cos(b.lat * p);
  const x = Math.cos(a.lat * p) * Math.sin(b.lat * p) - Math.sin(a.lat * p) * Math.cos(b.lat * p) * Math.cos((b.lng - a.lng) * p);
  return (Math.atan2(y, x) / p + 360) % 360;
}

/** A gently curved, slightly jittered polyline between two points. Simulated: not road-matched. */
export function simulatedPath(a: LatLng, b: LatLng, rnd: () => number, points = 24): [number, number][] {
  const out: [number, number][] = [];
  const bend = (rnd() - 0.5) * 0.02;
  for (let i = 0; i <= points; i++) {
    const t = i / points;
    const arc = Math.sin(t * Math.PI) * bend;
    const lat = a.lat + (b.lat - a.lat) * t + arc + (i && i < points ? (rnd() - 0.5) * 0.0012 : 0);
    const lng = a.lng + (b.lng - a.lng) * t - arc * 0.6 + (i && i < points ? (rnd() - 0.5) * 0.0012 : 0);
    out.push([+lat.toFixed(5), +lng.toFixed(5)]);
  }
  return out;
}

export const pointInCircle = (p: LatLng, c: LatLng, radiusM: number) => haversineKm(p, c) * 1000 <= radiusM;

export function pointInPolygon(p: LatLng, poly: LatLng[]) {
  let inside = false;
  for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
    const a = poly[i]!, b = poly[j]!;
    if (a.lng > p.lng !== b.lng > p.lng && p.lat < ((b.lat - a.lat) * (p.lng - a.lng)) / (b.lng - a.lng) + a.lat) inside = !inside;
  }
  return inside;
}
