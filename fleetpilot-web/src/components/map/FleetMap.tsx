import * as React from "react";
import L from "leaflet";
import { MapContainer, TileLayer, Marker, Popup, Circle, Polygon, Polyline, useMap, CircleMarker, Tooltip as LTooltip } from "react-leaflet";
import type { Geofence, LatLng, Trip, Vehicle } from "@/types";
import { STATUS_META } from "@/components/shared/StatusBadge";
import { cn } from "@/lib/utils";
import { Layers, Satellite, Map as MapIcon } from "lucide-react";

export const GTA_CENTER: LatLng = { lat: 43.47, lng: -79.72 };

// Esri basemaps: no API key required for development/demo use; attribution kept.
const TILES = {
  street: { url: "https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}", attribution: "Tiles © Esri — Esri, HERE, Garmin, OpenStreetMap contributors" },
  satellite: { url: "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}", attribution: "Tiles © Esri — Source: Esri, Maxar, Earthstar Geographics" },
  light: { url: "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}", attribution: "Tiles © Esri — Esri, HERE, Garmin" },
};
export type Basemap = keyof typeof TILES;

export function vehicleIcon(v: Vehicle, selected = false) {
  const c = STATUS_META[v.status].color;
  const rot = v.status === "moving" ? v.heading : 0;
  const html = `<div style="position:relative;width:34px;height:34px;">
    <div style="position:absolute;inset:0;border-radius:50%;background:${c};opacity:${selected ? 0.28 : 0.16};transform:scale(${selected ? 1.35 : 1});transition:transform .2s"></div>
    <div style="position:absolute;left:7px;top:7px;width:20px;height:20px;border-radius:50%;background:${c};border:2px solid #fff;box-shadow:0 1px 4px rgba(0,0,0,.35);display:flex;align-items:center;justify-content:center;transform:rotate(${rot}deg)">
      ${v.status === "moving" ? '<svg width="10" height="10" viewBox="0 0 10 10"><path d="M5 0 L9 9 L5 7 L1 9 Z" fill="#fff"/></svg>' : '<div style="width:6px;height:6px;border-radius:50%;background:#fff"></div>'}
    </div>
    <div style="position:absolute;top:30px;left:50%;transform:translateX(-50%);white-space:nowrap;font:600 10px/1 Inter,system-ui,sans-serif;color:#0f2a4a;background:rgba(255,255,255,.92);padding:2px 5px;border-radius:4px;box-shadow:0 1px 2px rgba(0,0,0,.2)">${v.name}</div>
  </div>`;
  return L.divIcon({ html, className: "fp-marker", iconSize: [34, 34], iconAnchor: [17, 17], popupAnchor: [0, -14] });
}

export function FlyTo({ target, zoom = 15 }: { target?: LatLng | null; zoom?: number }) {
  const map = useMap();
  React.useEffect(() => { if (target) map.flyTo([target.lat, target.lng], Math.max(map.getZoom(), zoom), { duration: 0.6 }); }, [target?.lat, target?.lng]); // eslint-disable-line react-hooks/exhaustive-deps
  return null;
}

export function FitBounds({ points, padding = 40 }: { points: [number, number][]; padding?: number }) {
  const map = useMap();
  React.useEffect(() => { if (points.length) map.fitBounds(L.latLngBounds(points), { padding: [padding, padding], maxZoom: 15 }); }, [points.length]); // eslint-disable-line react-hooks/exhaustive-deps
  return null;
}

export function InvalidateOnMount() {
  const map = useMap();
  React.useEffect(() => { const t = setTimeout(() => map.invalidateSize(), 50); return () => clearTimeout(t); }, [map]);
  return null;
}

export function BasemapToggle({ value, onChange }: { value: Basemap; onChange: (b: Basemap) => void }) {
  const opts: { v: Basemap; icon: React.ComponentType<{ className?: string }>; label: string }[] = [{ v: "street", icon: MapIcon, label: "Map" }, { v: "satellite", icon: Satellite, label: "Satellite" }, { v: "light", icon: Layers, label: "Light" }];
  return (
    <div className="absolute right-3 top-3 z-[500] flex overflow-hidden rounded-md border bg-card shadow-card">
      {opts.map((o) => (
        <button key={o.v} onClick={() => onChange(o.v)} className={cn("flex items-center gap-1.5 px-2.5 py-1.5 text-xs font-medium hover:bg-accent", value === o.v && "bg-primary text-primary-foreground hover:bg-primary")}>
          <o.icon className="h-3.5 w-3.5" />{o.label}
        </button>
      ))}
    </div>
  );
}

export const geofenceColor = (c: Geofence["category"]) => ({ customer: "#2563eb", depot: "#0f2a4a", warehouse: "#7c3aed", restricted: "#dc2626" })[c];

export function GeofenceLayer({ geofences, onClick, selectedId, labels = true }: { geofences: Geofence[]; onClick?: (g: Geofence) => void; selectedId?: string; labels?: boolean }) {
  return (
    <>
      {geofences.map((g) => {
        const color = geofenceColor(g.category);
        const opts = { color, weight: g.id === selectedId ? 3 : 1.5, fillColor: color, fillOpacity: g.id === selectedId ? 0.22 : 0.1, dashArray: g.category === "restricted" ? "6 4" : undefined };
        const handlers = onClick ? { click: () => onClick(g) } : {};
        return g.shape === "polygon" && g.polygon ? (
          <Polygon key={g.id} positions={g.polygon.map((p) => [p.lat, p.lng] as [number, number])} pathOptions={opts} eventHandlers={handlers}>{labels && <LTooltip direction="center" permanent={false}>{g.name}</LTooltip>}</Polygon>
        ) : (
          <Circle key={g.id} center={[g.center.lat, g.center.lng]} radius={g.radiusM} pathOptions={opts} eventHandlers={handlers}>{labels && <LTooltip>{g.name}</LTooltip>}</Circle>
        );
      })}
    </>
  );
}

export function TripPath({ trip, color = "#2563eb", showEnds = true, progress }: { trip: Trip; color?: string; showEnds?: boolean; progress?: number }) {
  const pts = trip.path.map(([a, b]) => [a, b] as [number, number]);
  const cut = progress !== undefined ? Math.max(1, Math.round(progress * (pts.length - 1))) : pts.length;
  return (
    <>
      <Polyline positions={pts} pathOptions={{ color: "#94a3b8", weight: 4, opacity: 0.5 }} />
      <Polyline positions={pts.slice(0, cut + 1)} pathOptions={{ color, weight: 4 }} />
      {showEnds && <CircleMarker center={pts[0]!} radius={6} pathOptions={{ color: "#fff", fillColor: "#16a34a", fillOpacity: 1, weight: 2 }}><LTooltip>Start · {trip.startLabel}</LTooltip></CircleMarker>}
      {showEnds && trip.status === "completed" && <CircleMarker center={pts[pts.length - 1]!} radius={6} pathOptions={{ color: "#fff", fillColor: "#dc2626", fillOpacity: 1, weight: 2 }}><LTooltip>End · {trip.endLabel}</LTooltip></CircleMarker>}
      {trip.stops.map((st, i) => <CircleMarker key={i} center={[st.position.lat, st.position.lng]} radius={5} pathOptions={{ color: "#fff", fillColor: "#d97706", fillOpacity: 1, weight: 2 }}><LTooltip>Stop · {st.label} · {st.durationMin} min</LTooltip></CircleMarker>)}
      {progress !== undefined && pts[cut] && <CircleMarker center={pts[cut]!} radius={8} pathOptions={{ color: "#fff", fillColor: color, fillOpacity: 1, weight: 2 }} />}
    </>
  );
}

export function BaseMap({ children, center = GTA_CENTER, zoom = 11, basemap = "street", className, scrollWheel = true }: { children?: React.ReactNode; center?: LatLng; zoom?: number; basemap?: Basemap; className?: string; scrollWheel?: boolean }) {
  const t = TILES[basemap];
  return (
    <MapContainer center={[center.lat, center.lng]} zoom={zoom} className={cn("h-full w-full", className)} zoomControl scrollWheelZoom={scrollWheel}>
      <TileLayer key={basemap} url={t.url} attribution={t.attribution} maxZoom={19} />
      <InvalidateOnMount />
      {children}
    </MapContainer>
  );
}

export { Marker, Popup };
