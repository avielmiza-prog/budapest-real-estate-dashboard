"use client";

import { useMemo } from "react";
import { GeoJSON } from "react-leaflet";
import type { Layer } from "leaflet";
import type { Feature, FeatureCollection, Geometry } from "geojson";

import budapestDistricts from "@/lib/data/budapest-districts.json";
import { formatHuf } from "@/lib/format";
import type { Currency, DistrictBenchmark } from "@/lib/types";

// Boundaries: OpenStreetMap-derived administrative boundaries from
// github.com/integralvision/geo-data-hungary (CC BY-SA 3.0).
const DISTRICTS_GEOJSON = budapestDistricts as unknown as FeatureCollection<Geometry, { district: string; district_number: number; name: string }>;

// Sequential blue scale for the €/m² choropleth — deliberately not the
// green/amber/red deal-score palette used elsewhere, since this encodes
// price *level*, not deal *quality* (a high €/m² district isn't "bad").
const NO_DATA_FILL = "#e5e7eb";
const SCALE_STOPS = ["#eff6ff", "#bfdbfe", "#60a5fa", "#2563eb", "#1e3a8a"];

function priceToColor(value: number, min: number, max: number): string {
  if (max <= min) return SCALE_STOPS[Math.floor(SCALE_STOPS.length / 2)]!;
  const t = Math.max(0, Math.min(1, (value - min) / (max - min)));
  const idx = Math.min(SCALE_STOPS.length - 1, Math.floor(t * SCALE_STOPS.length));
  return SCALE_STOPS[idx]!;
}

interface DistrictPolygonsProps {
  benchmarks: DistrictBenchmark[];
  currency: Currency;
  eurHufRate: number;
}

export function DistrictPolygons({ benchmarks, currency, eurHufRate }: DistrictPolygonsProps) {
  const byDistrictNumber = useMemo(() => {
    const map = new Map<number, DistrictBenchmark>();
    for (const b of benchmarks) map.set(b.district_number, b);
    return map;
  }, [benchmarks]);

  const { min, max } = useMemo(() => {
    const values = benchmarks
      .map((b) => b.avg_price_sqm_renovated)
      .filter((v): v is number => v !== null && v !== undefined);
    if (values.length === 0) return { min: 0, max: 0 };
    return { min: Math.min(...values), max: Math.max(...values) };
  }, [benchmarks]);

  const style = (feature?: Feature<Geometry, { district_number: number }>) => {
    const benchmark = feature ? byDistrictNumber.get(feature.properties.district_number) : undefined;
    const value = benchmark?.avg_price_sqm_renovated;
    return {
      color: "#475569",
      weight: 1,
      opacity: 0.5,
      fillOpacity: 0.35,
      fillColor: value !== null && value !== undefined ? priceToColor(value, min, max) : NO_DATA_FILL,
    };
  };

  const onEachFeature = (feature: Feature<Geometry, { district: string; district_number: number; name: string }>, layer: Layer) => {
    const benchmark = byDistrictNumber.get(feature.properties.district_number);
    const perSqm = benchmark?.avg_price_sqm_renovated;
    layer.bindTooltip(
      `<div style="font-size:12px;line-height:1.4">
        <strong>District ${feature.properties.district}</strong><br/>
        ${
          perSqm !== null && perSqm !== undefined
            ? `${currency === "EUR" ? `€${Math.round(perSqm / eurHufRate).toLocaleString()}` : formatHuf(perSqm)}/m² (renovated avg)`
            : "No benchmark on file yet"
        }<br/>
        <span style="opacity:0.7">No historical trend on file yet</span>
      </div>`,
      { sticky: true, direction: "top" }
    );
  };

  return <GeoJSON data={DISTRICTS_GEOJSON} style={style} onEachFeature={onEachFeature} />;
}
