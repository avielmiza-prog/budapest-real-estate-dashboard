"use client";

import { Home, TrendingDown } from "lucide-react";
import { useState } from "react";

import { formatCurrency, formatPercent, formatRooms, formatSqm } from "@/lib/format";
import { useFlipText, type FlipTextKey } from "@/lib/flip-text";
import type { Currency, Deal } from "@/lib/types";
import { cn } from "@/lib/utils";

import { FavoriteToggle } from "./deal-actions";
import { VerdictBadge } from "./verdict-badge";

interface SimpleDealListProps {
  deals: Deal[];
  onSelectDeal: (deal: Deal) => void;
  onDealUpdated: (deal: Deal) => void;
  currency: Currency;
  eurHufRate: number;
}

/**
 * The default view: one card per listing answering three questions —
 * should I buy it, how much can I offer, how much would I make.
 */
export function SimpleDealList({ deals, onSelectDeal, onDealUpdated, currency, eurHufRate }: SimpleDealListProps) {
  const t = useFlipText();
  const money = (v: number | null | undefined) => formatCurrency(v, currency, eurHufRate);

  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {deals.map((deal) => {
        const flip = deal.flip;
        const image = deal.images?.[0];
        return (
          <article
            key={deal.id}
            className="group flex cursor-pointer flex-col overflow-hidden rounded-xl border bg-card shadow-sm transition hover:shadow-md"
            onClick={() => onSelectDeal(deal)}
            onKeyDown={(e) => (e.key === "Enter" ? onSelectDeal(deal) : null)}
            tabIndex={0}
          >
            <div className="relative aspect-[16/9] bg-muted">
              <CardImage src={image} />
              <div className="absolute left-3 top-3">{flip && <VerdictBadge verdict={flip.verdict} />}</div>
              <div className="absolute right-2 top-2 rounded-full bg-background/90" onClick={(e) => e.stopPropagation()}>
                <FavoriteToggle deal={deal} onUpdated={onDealUpdated} />
              </div>
            </div>

            <div className="flex flex-1 flex-col gap-3 p-4">
              <div>
                <div className="flex items-baseline justify-between gap-2">
                  <h3 className="font-semibold">
                    {deal.district}.{deal.sub_district ? ` ${deal.sub_district}` : ""} · {formatSqm(deal.size_sqm)} ·{" "}
                    {formatRooms(deal.rooms)}
                  </h3>
                </div>
                <p className="line-clamp-1 text-xs text-muted-foreground">{deal.condition ?? deal.title}</p>
              </div>

              <div className="text-lg font-bold">{money(deal.price_huf)}</div>

              {flip ? (
                <>
                  <div className="rounded-lg bg-muted/60 px-3 py-2">
                    <div className="text-xs text-muted-foreground">{t("offerUpTo")}</div>
                    <div className="font-semibold">
                      {flip.max_offer_price_huf ? money(flip.max_offer_price_huf) : t("noOffer")}
                    </div>
                    {flip.offer_gap_percent !== null && flip.max_offer_price_huf && (
                      <div
                        className={cn(
                          "text-xs",
                          flip.offer_gap_percent > 0 ? "text-amber-700 dark:text-amber-400" : "text-emerald-700 dark:text-emerald-400"
                        )}
                      >
                        {flip.offer_gap_percent > 0
                          ? t("askingAbove", { n: Math.round(flip.offer_gap_percent) })
                          : t("askingBelow", { n: Math.round(-flip.offer_gap_percent) })}
                      </div>
                    )}
                  </div>
                  <div className="grid grid-cols-2 gap-2 text-sm">
                    <div>
                      <div className="text-xs text-muted-foreground">{t("netProfit")}</div>
                      <div
                        className={cn(
                          "font-semibold",
                          flip.net_profit_huf >= 0 ? "text-emerald-700 dark:text-emerald-400" : "text-destructive"
                        )}
                      >
                        {money(flip.net_profit_huf)}
                      </div>
                    </div>
                    <div>
                      <div className="text-xs text-muted-foreground">{t("roi")}</div>
                      <div className="font-semibold">{formatPercent(flip.roi_percent)}</div>
                    </div>
                  </div>
                </>
              ) : null}

              <div className="mt-auto flex flex-wrap gap-1.5 text-xs">
                {deal.price_drop_percent !== null && deal.price_drop_percent !== undefined && deal.price_drop_percent > 0 && (
                  <span className="inline-flex items-center gap-1 rounded-full bg-emerald-100 px-2 py-0.5 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-300">
                    <TrendingDown className="h-3 w-3" />
                    {t("priceDrop", { n: deal.price_drop_percent })}
                  </span>
                )}
                {deal.is_stale && (
                  <span className="rounded-full bg-zinc-200 px-2 py-0.5 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300">
                    {t("stale")}
                  </span>
                )}
                {(flip?.red_flags ?? []).slice(0, 2).map((code) => (
                  <span key={code} className="rounded-full bg-amber-100 px-2 py-0.5 text-amber-900 dark:bg-amber-900/40 dark:text-amber-200">
                    {t(`flag_${code}` as FlipTextKey)}
                  </span>
                ))}
                {flip && flip.confidence !== "high" && (
                  <span className="rounded-full border px-2 py-0.5 text-muted-foreground">
                    {flip.confidence === "low" ? t("confidenceLow") : t("confidenceMedium")}
                  </span>
                )}
              </div>
            </div>
          </article>
        );
      })}
    </div>
  );
}

function CardImage({ src }: { src?: string }) {
  const [failed, setFailed] = useState(false);
  if (!src || failed) {
    return (
      <div className="flex h-full items-center justify-center text-muted-foreground/60">
        <Home className="h-8 w-8" />
      </div>
    );
  }
  return (
    // eslint-disable-next-line @next/next/no-img-element
    <img src={src} alt="" loading="lazy" className="h-full w-full object-cover" onError={() => setFailed(true)} />
  );
}
