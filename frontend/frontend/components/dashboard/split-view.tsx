"use client";

import dynamic from "next/dynamic";
import { useMemo, useRef, useState } from "react";

import { formatCurrency, formatRooms, formatSqm } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { Currency, Deal } from "@/lib/types";

import { DealMicroBadges } from "./deal-micro-badges";
import { DealScoreBadge } from "./deal-score-badge";
import { FavoriteToggle, PipelineStatusSelect } from "./deal-actions";
import { RoiBadge } from "./roi-badge";

// Leaflet touches `window` at import time — must never run during SSR.
const DealMap = dynamic(() => import("./deal-map").then((m) => m.DealMap), {
  ssr: false,
  loading: () => <div className="flex h-full w-full items-center justify-center rounded-lg border text-sm text-muted-foreground">Loading map…</div>,
});

interface SplitViewProps {
  deals: Deal[];
  selectedDealId: number | null;
  onSelectDeal: (dealId: number) => void;
  onSelectDealForModal: (deal: Deal) => void;
  onDealUpdated: (deal: Deal) => void;
  currency: Currency;
  eurHufRate: number;
}

export function SplitView({
  deals,
  selectedDealId,
  onSelectDeal,
  onSelectDealForModal,
  onDealUpdated,
  currency,
  eurHufRate,
}: SplitViewProps) {
  const rankedDeals = useMemo(
    () => [...deals].sort((a, b) => (b.deal_score ?? -1) - (a.deal_score ?? -1)),
    [deals]
  );
  const cardRefs = useRef<Record<number, HTMLDivElement | null>>({});
  const [hoveredDealId, setHoveredDealId] = useState<number | null>(null);

  const handleSelectFromMap = (dealId: number) => {
    onSelectDeal(dealId);
    cardRefs.current[dealId]?.scrollIntoView({ behavior: "smooth", block: "center" });
  };

  return (
    <div className="grid h-[calc(100vh-22rem)] min-h-[500px] grid-cols-1 gap-4 lg:grid-cols-2">
      <div className="flex flex-col gap-3 overflow-y-auto pr-1">
        {rankedDeals.map((deal, index) => (
          <div
            key={deal.id}
            ref={(el) => {
              cardRefs.current[deal.id] = el;
            }}
            onClick={() => onSelectDeal(deal.id)}
            onMouseEnter={() => setHoveredDealId(deal.id)}
            onMouseLeave={() => setHoveredDealId((current) => (current === deal.id ? null : current))}
            className={cn(
              "cursor-pointer space-y-2 rounded-lg border bg-card p-3 transition-colors",
              deal.id === selectedDealId ? "border-primary ring-1 ring-primary" : "hover:border-muted-foreground/40"
            )}
          >
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0">
                <p className="text-[11px] text-muted-foreground">#{index + 1} ranked</p>
                <p className="truncate text-sm font-medium">{deal.title}</p>
                <p className="text-xs text-muted-foreground">
                  District {deal.district} · {formatSqm(deal.size_sqm)} · {formatRooms(deal.rooms)} rooms
                </p>
              </div>
              <DealScoreBadge score={deal.deal_score} band={deal.deal_score_band} className="shrink-0" />
            </div>

            <DealMicroBadges deal={deal} className="flex flex-wrap gap-1" />

            <div className="flex items-center justify-between text-sm">
              <span className="font-medium">{formatCurrency(deal.price_huf, currency, eurHufRate)}</span>
              <RoiBadge roiPercent={deal.best_tier?.roi_percent} />
            </div>

            <div className="flex items-center justify-between gap-2">
              <PipelineStatusSelect deal={deal} onUpdated={onDealUpdated} />
              <div className="flex items-center gap-1">
                <FavoriteToggle deal={deal} onUpdated={onDealUpdated} />
                <button
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation();
                    onSelectDealForModal(deal);
                  }}
                  className="text-xs font-medium text-primary underline-offset-2 hover:underline"
                >
                  View details
                </button>
              </div>
            </div>
          </div>
        ))}
        {rankedDeals.length === 0 && (
          <p className="rounded-lg border border-dashed p-8 text-center text-sm text-muted-foreground">
            No listings match these filters yet.
          </p>
        )}
      </div>

      <div className="h-full min-h-[400px]">
        <DealMap
          deals={rankedDeals}
          selectedDealId={selectedDealId}
          hoveredDealId={hoveredDealId}
          onSelectDeal={handleSelectFromMap}
          currency={currency}
          eurHufRate={eurHufRate}
        />
      </div>
    </div>
  );
}
