"use client";

import Image from "next/image";
import { ChevronLeft, ChevronRight, ExternalLink, FileText, ImageOff } from "lucide-react";
import { useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { getSpecSheetUrl } from "@/lib/api";
import { getSourceListingUrl, isMockListingUrl } from "@/lib/deal-links";
import { formatCurrency, formatRooms, formatSqm } from "@/lib/format";
import type { Currency, Deal } from "@/lib/types";

import { DealMicroBadges } from "./deal-micro-badges";
import { DealScoreBadge } from "./deal-score-badge";
import { FavoriteToggle, PipelineStatusSelect } from "./deal-actions";
import { RoiBadge } from "./roi-badge";

interface ListingsCardsProps {
  deals: Deal[];
  onSelectDeal: (deal: Deal) => void;
  onDealUpdated: (deal: Deal) => void;
  currency: Currency;
  eurHufRate: number;
}

function CardImageCarousel({ images, title }: { images: string[]; title: string }) {
  const [index, setIndex] = useState(0);

  if (images.length === 0) {
    return (
      <div className="flex h-full w-full flex-col items-center justify-center gap-1 text-muted-foreground">
        <ImageOff className="h-8 w-8" />
        <span className="text-center text-[11px] leading-tight">No photos available from listing</span>
      </div>
    );
  }

  const goPrev = (e: React.MouseEvent) => {
    e.stopPropagation();
    setIndex((i) => (i - 1 + images.length) % images.length);
  };
  const goNext = (e: React.MouseEvent) => {
    e.stopPropagation();
    setIndex((i) => (i + 1) % images.length);
  };

  return (
    <div className="group/carousel relative h-full w-full">
      <Image src={images[index]!} alt={title} fill className="object-cover" unoptimized />
      {images.length > 1 && (
        <>
          <button
            type="button"
            onClick={goPrev}
            className="absolute left-1.5 top-1/2 -translate-y-1/2 rounded-full bg-black/40 p-1 text-white opacity-0 transition-opacity hover:bg-black/60 group-hover/carousel:opacity-100"
            aria-label="Previous photo"
          >
            <ChevronLeft className="h-4 w-4" />
          </button>
          <button
            type="button"
            onClick={goNext}
            className="absolute right-1.5 top-1/2 -translate-y-1/2 rounded-full bg-black/40 p-1 text-white opacity-0 transition-opacity hover:bg-black/60 group-hover/carousel:opacity-100"
            aria-label="Next photo"
          >
            <ChevronRight className="h-4 w-4" />
          </button>
          <span className="absolute bottom-1.5 right-1.5 rounded-full bg-black/50 px-1.5 py-0.5 text-[10px] text-white">
            {index + 1}/{images.length}
          </span>
        </>
      )}
    </div>
  );
}

export function ListingsCards({ deals, onSelectDeal, onDealUpdated, currency, eurHufRate }: ListingsCardsProps) {
  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
      {deals.map((deal) => {
        const netProfit = deal.best_tier?.net_profit_huf;
        const isProfit = netProfit !== undefined && netProfit !== null && netProfit >= 0;
        const sourceUrl = getSourceListingUrl(deal);
        const isMock = isMockListingUrl(deal.source_url ?? deal.url);
        return (
          <Card key={deal.id} className="flex flex-col overflow-hidden">
            <div className="relative aspect-video w-full bg-muted">
              <CardImageCarousel images={deal.images ?? []} title={deal.title} />
              <Badge className="pointer-events-none absolute left-2 top-2" variant="secondary">
                District {deal.district}
              </Badge>
              <DealScoreBadge score={deal.deal_score} band={deal.deal_score_band} className="absolute right-2 top-2" />
              <FavoriteToggle deal={deal} onUpdated={onDealUpdated} className="absolute bottom-1 right-1 bg-black/30 text-white hover:bg-black/50 hover:text-white" />
            </div>

            <CardHeader className="pb-2">
              <CardTitle className="line-clamp-2 text-sm">{deal.title}</CardTitle>
            </CardHeader>

            <CardContent className="flex-1 space-y-2 pb-2 text-sm text-muted-foreground">
              <DealMicroBadges deal={deal} className="flex flex-wrap gap-1" />
              <div className="flex items-center justify-between">
                <span>{formatCurrency(deal.price_huf, currency, eurHufRate)}</span>
                <span>{formatCurrency(deal.price_per_sqm, currency, eurHufRate)}/sqm</span>
              </div>
              <div className="flex items-center justify-between">
                <span>{formatSqm(deal.size_sqm)}</span>
                <span>{formatRooms(deal.rooms)} rooms</span>
              </div>

              <div className="flex items-center justify-between rounded-md border bg-background px-2 py-1.5">
                <div>
                  <p className="text-[11px] text-muted-foreground">Net profit potential</p>
                  <p className={isProfit ? "text-sm font-semibold text-emerald-600" : "text-sm font-semibold text-red-600"}>
                    {netProfit !== undefined && netProfit !== null ? formatCurrency(netProfit, currency, eurHufRate) : "—"}
                  </p>
                </div>
                <RoiBadge roiPercent={deal.best_tier?.roi_percent} />
              </div>

              <PipelineStatusSelect deal={deal} onUpdated={onDealUpdated} className="w-full" />
            </CardContent>

            <CardFooter className="flex-col gap-2">
              <div className="flex w-full gap-2">
                <Button className="flex-1" variant="outline" onClick={() => onSelectDeal(deal)}>
                  View details
                </Button>
                <Button variant="ghost" size="icon" title="Download Contractor Spec Sheet" asChild>
                  <a href={getSpecSheetUrl(deal.id, eurHufRate)} target="_blank" rel="noreferrer">
                    <FileText />
                  </a>
                </Button>
              </div>
              {sourceUrl ? (
                <Button className="w-full" variant="secondary" asChild>
                  <a href={sourceUrl} target="_blank" rel="noopener noreferrer">
                    <ExternalLink />
                    View Original Listing
                  </a>
                </Button>
              ) : (
                isMock && (
                  <p className="w-full text-center text-[11px] text-muted-foreground">
                    Demo listing — no live source
                  </p>
                )
              )}
            </CardFooter>
          </Card>
        );
      })}
    </div>
  );
}
