"use client";

import { Download, RotateCcw } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { RangeSlider, Slider } from "@/components/ui/slider";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { getDealsExportCsvUrl } from "@/lib/api";
import {
  PORTALS,
  PORTAL_LABELS,
  PRICE_FILTER_MAX_HUF,
  PRICE_FILTER_MIN_HUF,
  PRICE_PER_SQM_FILTER_MAX_HUF,
  PRICE_PER_SQM_FILTER_MIN_HUF,
  ROI_FILTER_MAX_PERCENT,
  ROI_FILTER_MIN_PERCENT,
  SIZE_FILTER_MAX_SQM,
  SIZE_FILTER_MIN_SQM,
} from "@/lib/constants";
import { formatCurrency, formatPercent, formatSqm } from "@/lib/format";
import { cn } from "@/lib/utils";
import {
  EMPTY_FILTERS,
  PIPELINE_STATUSES,
  PIPELINE_STATUS_LABELS,
  SORT_OPTIONS,
  SORT_OPTION_LABELS,
  type Currency,
  type DealFilters,
  type SortOption,
  type ViewMode,
} from "@/lib/types";

import { DistrictMultiSelect } from "./district-multiselect";

interface FiltersBarProps {
  filters: DealFilters;
  onFiltersChange: (filters: DealFilters) => void;
  // The view switcher moved to the dashboard header row; kept optional so
  // existing callers still type-check.
  view?: ViewMode;
  onViewChange?: (view: ViewMode) => void;
  currency: Currency;
  eurHufRate: number;
}

function numberOrNull(value: string): number | null {
  if (value.trim() === "") return null;
  const parsed = Number(value);
  return Number.isNaN(parsed) ? null : parsed;
}

export function FiltersBar({ filters, onFiltersChange, currency, eurHufRate }: FiltersBarProps) {
  const update = (patch: Partial<DealFilters>) => onFiltersChange({ ...filters, ...patch });

  const sizeRange: [number, number] = [
    filters.minSize ?? SIZE_FILTER_MIN_SQM,
    filters.maxSize ?? SIZE_FILTER_MAX_SQM,
  ];
  const priceRange: [number, number] = [
    filters.minPrice ?? PRICE_FILTER_MIN_HUF,
    filters.maxPrice ?? PRICE_FILTER_MAX_HUF,
  ];
  const pricePerSqmRange: [number, number] = [
    filters.minPricePerSqm ?? PRICE_PER_SQM_FILTER_MIN_HUF,
    filters.maxPricePerSqm ?? PRICE_PER_SQM_FILTER_MAX_HUF,
  ];
  const minRoi = filters.minRoi ?? ROI_FILTER_MIN_PERCENT;

  const togglePortal = (portal: string) => {
    if (filters.portals.includes(portal)) {
      update({ portals: filters.portals.filter((p) => p !== portal) });
    } else {
      update({ portals: [...filters.portals, portal] });
    }
  };

  return (
    <div className="flex flex-col gap-5 rounded-lg border bg-card p-4 shadow-sm">
      <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-5">
        <div className="flex flex-col gap-1.5">
          <Label>Districts</Label>
          <DistrictMultiSelect selected={filters.districts} onChange={(districts) => update({ districts })} />
        </div>

        <div className="flex flex-col gap-1.5">
          <div className="flex items-center justify-between">
            <Label>Size (sqm)</Label>
            <span className="text-xs text-muted-foreground">
              {formatSqm(sizeRange[0])} – {formatSqm(sizeRange[1])}
            </span>
          </div>
          <RangeSlider
            min={SIZE_FILTER_MIN_SQM}
            max={SIZE_FILTER_MAX_SQM}
            step={5}
            value={sizeRange}
            onValueChange={([minSize, maxSize]) => update({ minSize, maxSize })}
            className="mt-2.5"
          />
          <div className="mt-1 grid grid-cols-2 gap-2">
            <Input
              type="number"
              inputMode="decimal"
              placeholder="Min"
              value={filters.minSize ?? ""}
              onChange={(e) => update({ minSize: numberOrNull(e.target.value) })}
            />
            <Input
              type="number"
              inputMode="decimal"
              placeholder="Max"
              value={filters.maxSize ?? ""}
              onChange={(e) => update({ maxSize: numberOrNull(e.target.value) })}
            />
          </div>
        </div>

        <div className="flex flex-col gap-1.5">
          <Label>Price ({currency})</Label>
          <span className="text-xs text-muted-foreground">
            {formatCurrency(priceRange[0], currency, eurHufRate)} – {formatCurrency(priceRange[1], currency, eurHufRate)}
          </span>
          <RangeSlider
            min={PRICE_FILTER_MIN_HUF}
            max={PRICE_FILTER_MAX_HUF}
            step={1_000_000}
            value={priceRange}
            onValueChange={([minPrice, maxPrice]) => update({ minPrice, maxPrice })}
            className="mt-1"
          />
        </div>

        <div className="flex flex-col gap-1.5">
          <Label>Price / sqm</Label>
          <span className="text-xs text-muted-foreground">
            {formatCurrency(pricePerSqmRange[0], "EUR", eurHufRate)}/sqm – {formatCurrency(pricePerSqmRange[1], "EUR", eurHufRate)}/sqm
            <br />
            ({formatCurrency(pricePerSqmRange[0], "HUF", eurHufRate)}/sqm – {formatCurrency(pricePerSqmRange[1], "HUF", eurHufRate)}/sqm)
          </span>
          <RangeSlider
            min={PRICE_PER_SQM_FILTER_MIN_HUF}
            max={PRICE_PER_SQM_FILTER_MAX_HUF}
            step={50_000}
            value={pricePerSqmRange}
            onValueChange={([minPricePerSqm, maxPricePerSqm]) => update({ minPricePerSqm, maxPricePerSqm })}
            className="mt-1"
          />
        </div>

        <div className="flex flex-col gap-1.5">
          <div className="flex items-center justify-between">
            <Label>Min ROI</Label>
            <span className="text-xs text-muted-foreground">{formatPercent(minRoi)}+</span>
          </div>
          <Slider
            min={ROI_FILTER_MIN_PERCENT}
            max={ROI_FILTER_MAX_PERCENT}
            step={1}
            value={minRoi}
            onValueChange={(minRoi) => update({ minRoi })}
            className="mt-2.5"
          />
          <Input
            id="filter-min-roi"
            type="number"
            inputMode="decimal"
            placeholder="e.g. 15"
            value={filters.minRoi ?? ""}
            onChange={(e) => update({ minRoi: numberOrNull(e.target.value) })}
            className="mt-1"
          />
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-1.5 border-t pt-4">
        <span className="mr-1 text-xs font-medium text-muted-foreground">Pipeline</span>
        <button
          type="button"
          onClick={() => update({ pipelineStatus: null })}
          className={cn(
            "rounded-full border px-2.5 py-1 text-xs font-medium transition-colors",
            filters.pipelineStatus === null
              ? "border-primary bg-primary text-primary-foreground"
              : "border-input bg-background hover:bg-accent"
          )}
        >
          All
        </button>
        {PIPELINE_STATUSES.map((status) => (
          <button
            key={status}
            type="button"
            onClick={() => update({ pipelineStatus: filters.pipelineStatus === status ? null : status })}
            className={cn(
              "rounded-full border px-2.5 py-1 text-xs font-medium transition-colors",
              filters.pipelineStatus === status
                ? "border-primary bg-primary text-primary-foreground"
                : "border-input bg-background hover:bg-accent"
            )}
          >
            {PIPELINE_STATUS_LABELS[status]}
          </button>
        ))}
      </div>

      <div className="flex flex-col gap-3 border-t pt-4 sm:flex-row sm:items-end sm:justify-between">
        <div className="flex flex-wrap items-end gap-4">
          <div className="flex flex-col gap-1.5">
            <Label>Portal</Label>
            <div className="flex flex-wrap gap-1.5">
              {PORTALS.map((portal) => {
                const active = filters.portals.includes(portal);
                return (
                  <button
                    key={portal}
                    type="button"
                    onClick={() => togglePortal(portal)}
                    className={cn(
                      "rounded-md border px-2 py-1 text-xs font-medium transition-colors",
                      active
                        ? "border-primary bg-primary text-primary-foreground"
                        : "border-input bg-background hover:bg-accent"
                    )}
                  >
                    {PORTAL_LABELS[portal] ?? portal}
                  </button>
                );
              })}
            </div>
          </div>

          <div className="flex flex-col gap-1.5 pb-0.5">
            <Label>Shortlist</Label>
            <Tabs value={filters.favoritesOnly ? "shortlist" : "all"} onValueChange={(v) => update({ favoritesOnly: v === "shortlist" })}>
              <TabsList>
                <TabsTrigger value="all">All Deals</TabsTrigger>
                <TabsTrigger value="shortlist">My Saved Shortlist</TabsTrigger>
              </TabsList>
            </Tabs>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <Button variant="ghost" size="sm" onClick={() => onFiltersChange({ ...EMPTY_FILTERS, verdict: filters.verdict })} className="shrink-0">
            <RotateCcw />
            Reset
          </Button>

          <Button variant="outline" size="sm" className="shrink-0" asChild>
            <a href={getDealsExportCsvUrl(filters, eurHufRate)} target="_blank" rel="noreferrer">
              <Download />
              Export CSV
            </a>
          </Button>

          <Select value={filters.sortBy} onValueChange={(sortBy) => update({ sortBy: sortBy as SortOption })}>
            <SelectTrigger className="w-[180px]">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {SORT_OPTIONS.map((option) => (
                <SelectItem key={option} value={option}>
                  {SORT_OPTION_LABELS[option]}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>

        </div>
      </div>
    </div>
  );
}
