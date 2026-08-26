"use client";

import "leaflet/dist/leaflet.css";

import L from "leaflet";
import { useEffect, useMemo, useState } from "react";
import { MapContainer, Marker, Popup, TileLayer, useMap } from "react-leaflet";

import { useDistrictBenchmarks } from "@/hooks/use-district-benchmarks";
import { formatHuf } from "@/lib/format";
import type { Currency, Deal } from "@/lib/types";

import { bandToColor } from "./deal-score-badge";
import { DistrictPolygons } from "./district-polygons";

const BUDAPEST_CENTER: [number, number] = [47.4979, 19.0402];

function markerIcon(deal: Deal, isSelected: boolean): L.DivIcon {
  const color = bandToColor(deal.deal_score_band);
  const size = isSelected ? 26 : 18;
  return L.divIcon({
    className: "",
    html: `<div style="
      width:${size}px;height:${size}px;border-radius:9999px;
      background:${color};border:2px solid white;
      box-shadow:0 1px 4px rgba(0,0,0,0.5);
      ${isSelected ? "outline:2px solid #1d4ed8;outline-offset:1px;" : ""}
    "></div>`,
    iconSize: [size, size],
    iconAnchor: [size / 2, size / 2],
  });
}

function FlyToSelected({ deal }: { deal: Deal | null }) {
  const map = useMap();
  useEffect(() => {
    if (deal && deal.latitude !== null && deal.longitude !== null) {
      map.flyTo([deal.latitude, deal.longitude], Math.max(map.getZoom(), 14), { duration: 0.6 });
    }
  }, [deal, map]);
  return null;
}

interface DealMapProps {
  deals: Deal[];
  selectedDealId: number | null;
  hoveredDealId?: number | null;
  onSelectDeal: (dealId: number) => void;
  currency: Currency;
  eurHufRate: number;
}

export function DealMap({ deals, selectedDealId, hoveredDealId = null, onSelectDeal, currency, eurHufRate }: DealMapProps) {
  const [showDistricts, setShowDistricts] = useState(true);
  const districtBenchmarks = useDistrictBenchmarks();

  const mappable = useMemo(
    () => deals.filter((d): d is Deal & { latitude: number; longitude: number } => d.latitude !== null && d.longitude !== null),
    [deals]
  );

  const center = useMemo<[number, number]>(() => {
    if (mappable.length === 0) return BUDAPEST_CENTER;
    const avgLat = mappable.reduce((sum, d) => sum + d.latitude, 0) / mappable.length;
    const avgLng = mappable.reduce((sum, d) => sum + d.longitude, 0) / mappable.length;
    return [avgLat, avgLng];
  }, [mappable]);

  // A hovered card takes priority over the persistently-selected one — it's
  // the more immediate signal of what the user is looking at right now.
  const highlightedId = hoveredDealId ?? selectedDealId;
  const highlightedDeal = mappable.find((d) => d.id === highlightedId) ?? null;

  return (
    <div className="relative h-full w-full overflow-hidden rounded-lg border">
      <button
        type="button"
        onClick={() => setShowDistricts((v) => !v)}
        className="absolute right-2 top-2 z-[1000] rounded-md border bg-background/90 px-2 py-1 text-[11px] font-medium shadow-sm backdrop-blur hover:bg-accent"
      >
        {showDistricts ? "Hide" : "Show"} district €/m²
      </button>
      <MapContainer center={center} zoom={12} scrollWheelZoom className="h-full w-full">
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors | district boundaries © <a href="https://github.com/integralvision/geo-data-hungary">geo-data-hungary</a> (CC BY-SA)'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />
        {showDistricts && (
          <DistrictPolygons benchmarks={districtBenchmarks} currency={currency} eurHufRate={eurHufRate} />
        )}
        <FlyToSelected deal={highlightedDeal} />
        {mappable.map((deal) => (
          <Marker
            key={deal.id}
            position={[deal.latitude, deal.longitude]}
            icon={markerIcon(deal, deal.id === highlightedId)}
            eventHandlers={{ click: () => onSelectDeal(deal.id) }}
          >
            <Popup>
              <div className="space-y-0.5 text-sm">
                <p className="max-w-56 truncate font-medium">{deal.title}</p>
                <p>{formatHuf(deal.price_huf)}</p>
                <p className="text-muted-foreground">
                  District {deal.district} · Deal Score {deal.deal_score ?? "—"}
                </p>
              </div>
            </Popup>
          </Marker>
        ))}
      </MapContainer>
    </div>
  );
}
