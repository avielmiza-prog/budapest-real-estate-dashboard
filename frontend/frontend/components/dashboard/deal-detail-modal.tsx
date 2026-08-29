"use client";

import Image from "next/image";
import {
  AlertTriangle,
  ChevronLeft,
  ChevronRight,
  Expand,
  ExternalLink,
  FileText,
  ImageOff,
  ShieldCheck,
  Sparkles,
  Wrench,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Separator } from "@/components/ui/separator";
import { Slider } from "@/components/ui/slider";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { getInvestmentMemoUrl, getSpecSheetUrl } from "@/lib/api";
import { getSourceListingUrl, isMockListingUrl } from "@/lib/deal-links";
import { computeCustomTier } from "@/lib/financial-calc";
import { formatCurrency, formatDate, formatEur, formatHuf, formatPercent, formatRooms, formatSqm } from "@/lib/format";
import { TIER_LABELS } from "@/lib/constants";
import { cn } from "@/lib/utils";
import type { Currency, Deal, RenovationTier, RenovationTierName } from "@/lib/types";

import { ConditionBadge } from "./condition-badge";
import { DealScoreBadge } from "./deal-score-badge";
import { FavoriteToggle, PipelineStatusSelect } from "./deal-actions";
import { ImageLightbox } from "./image-lightbox";
import { RoiBadge } from "./roi-badge";

interface DealDetailModalProps {
  deal: Deal | null;
  onOpenChange: (open: boolean) => void;
  onDealUpdated: (deal: Deal) => void;
  currency: Currency;
  eurHufRate: number;
}

function PhotoGallery({ images, title }: { images: string[]; title: string }) {
  const [activeIndex, setActiveIndex] = useState(0);
  const [lightboxOpen, setLightboxOpen] = useState(false);

  if (images.length === 0) {
    return (
      <div className="flex aspect-video w-full flex-col items-center justify-center gap-2 rounded-md bg-muted text-muted-foreground">
        <ImageOff className="h-10 w-10" />
        <span className="text-sm">No photos available from listing</span>
      </div>
    );
  }

  const goPrev = () => setActiveIndex((i) => (i - 1 + images.length) % images.length);
  const goNext = () => setActiveIndex((i) => (i + 1) % images.length);

  return (
    <div className="space-y-2">
      <div className="group relative aspect-video w-full overflow-hidden rounded-md bg-muted">
        <button
          type="button"
          onClick={() => setLightboxOpen(true)}
          className="absolute inset-0 h-full w-full cursor-zoom-in"
          aria-label="Open full-screen preview"
        >
          <Image src={images[activeIndex]!} alt={title} fill className="object-cover" unoptimized />
        </button>

        <div className="pointer-events-none absolute right-2 top-2 rounded-full bg-black/50 p-1.5 text-white opacity-0 transition-opacity group-hover:opacity-100">
          <Expand className="h-4 w-4" />
        </div>

        {images.length > 1 && (
          <>
            <button
              type="button"
              onClick={goPrev}
              className="absolute left-2 top-1/2 -translate-y-1/2 rounded-full bg-black/40 p-1.5 text-white opacity-0 transition-opacity hover:bg-black/60 group-hover:opacity-100"
              aria-label="Previous photo"
            >
              <ChevronLeft className="h-5 w-5" />
            </button>
            <button
              type="button"
              onClick={goNext}
              className="absolute right-2 top-1/2 -translate-y-1/2 rounded-full bg-black/40 p-1.5 text-white opacity-0 transition-opacity hover:bg-black/60 group-hover:opacity-100"
              aria-label="Next photo"
            >
              <ChevronRight className="h-5 w-5" />
            </button>
            <span className="absolute bottom-2 right-2 rounded-full bg-black/50 px-2 py-0.5 text-xs text-white">
              {activeIndex + 1} / {images.length}
            </span>
          </>
        )}
      </div>

      {images.length > 1 && (
        <div className="flex gap-2 overflow-x-auto">
          {images.map((src, index) => (
            <button
              key={src}
              type="button"
              onClick={() => setActiveIndex(index)}
              className={cn(
                "relative h-14 w-20 shrink-0 overflow-hidden rounded-md border-2",
                index === activeIndex ? "border-primary" : "border-transparent opacity-70 hover:opacity-100"
              )}
            >
              <Image src={src} alt={`${title} photo ${index + 1}`} fill className="object-cover" unoptimized />
            </button>
          ))}
        </div>
      )}

      {lightboxOpen && (
        <ImageLightbox
          images={images}
          index={activeIndex}
          title={title}
          onIndexChange={setActiveIndex}
          onClose={() => setLightboxOpen(false)}
        />
      )}
    </div>
  );
}

function BenchmarkComparison({ deal, currency, eurHufRate }: { deal: Deal; currency: Currency; eurHufRate: number }) {
  const analysis = deal.analysis;
  if (!analysis) {
    return (
      <p className="text-sm text-muted-foreground">
        No district benchmark on file yet for district {deal.district} — can&apos;t compare this asking
        price to the market.
      </p>
    );
  }

  const askingPerSqm = deal.price_per_sqm;
  const benchmarkPerSqm = analysis.avg_price_sqm_renovated_huf;
  const deltaPercent = deal.discount_percent;

  const maxValue = Math.max(askingPerSqm ?? 0, benchmarkPerSqm ?? 0) || 1;

  return (
    <div className="space-y-3">
      <div className="space-y-1">
        <div className="flex items-center justify-between text-sm">
          <span className="text-muted-foreground">Asking price</span>
          <span className="font-medium">{formatCurrency(askingPerSqm, currency, eurHufRate)}/sqm</span>
        </div>
        <div className="h-2 w-full overflow-hidden rounded-full bg-muted">
          <div
            className="h-full rounded-full bg-primary"
            style={{ width: `${((askingPerSqm ?? 0) / maxValue) * 100}%` }}
          />
        </div>
      </div>
      <div className="space-y-1">
        <div className="flex items-center justify-between text-sm">
          <span className="text-muted-foreground">District Median (Turnkey)</span>
          <span className="font-medium">{formatCurrency(benchmarkPerSqm, currency, eurHufRate)}/sqm</span>
        </div>
        <div className="h-2 w-full overflow-hidden rounded-full bg-muted">
          <div
            className="h-full rounded-full bg-chart-2"
            style={{ width: `${((benchmarkPerSqm ?? 0) / maxValue) * 100}%` }}
          />
        </div>
      </div>
      {deltaPercent !== null && (
        <p className="text-sm">
          Discount vs. District Median:{" "}
          <span className={cn("font-semibold", deltaPercent > 0 ? "text-emerald-600" : "text-red-600")}>
            {deltaPercent > 0 ? "-" : "+"}
            {formatPercent(Math.abs(deltaPercent))}
          </span>{" "}
          ({deltaPercent > 0 ? "below" : "above"} the district&apos;s turnkey median).
        </p>
      )}
      {analysis.district_median_sample_count !== null && analysis.district_median_source && (
        <p className="text-xs text-muted-foreground">
          {analysis.district_median_source === "live" ? (
            <>
              Live Database Samples Used: based on {analysis.district_median_sample_count} recent listing
              {analysis.district_median_sample_count === 1 ? "" : "s"} in District {deal.district}.
            </>
          ) : (
            <>
              Documented baseline benchmark ({analysis.district_median_sample_count} live listing
              {analysis.district_median_sample_count === 1 ? "" : "s"} on file — below the 10-sample minimum for a
              live median).
            </>
          )}
        </p>
      )}
    </div>
  );
}

function TierComparisonTable({
  tiers,
  bestTier,
  currency,
  eurHufRate,
}: {
  tiers: RenovationTier[];
  bestTier?: string;
  currency: Currency;
  eurHufRate: number;
}) {
  const maxProfit = Math.max(...tiers.map((t) => Math.abs(t.net_profit_huf)), 0) || 1;

  return (
    <div className="space-y-4">
      <div className="overflow-x-auto rounded-lg border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Tier</TableHead>
              <TableHead>Reno. cost</TableHead>
              <TableHead>Contingency</TableHead>
              <TableHead>Total investment</TableHead>
              <TableHead>Break-even</TableHead>
              <TableHead>Net profit</TableHead>
              <TableHead>ROI</TableHead>
              <TableHead>Net CoC</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {tiers.map((tier) => (
              <TableRow key={tier.tier} className={cn(tier.tier === bestTier && "bg-emerald-50 dark:bg-emerald-950/30")}>
                <TableCell className="font-medium">
                  {TIER_LABELS[tier.tier] ?? tier.tier}
                  {tier.tier === bestTier && (
                    <Badge variant="success" className="ml-2">
                      Best
                    </Badge>
                  )}
                </TableCell>
                <TableCell>{formatCurrency(tier.renovation_cost_huf, currency, eurHufRate)}</TableCell>
                <TableCell>{formatCurrency(tier.safety_buffer_huf, currency, eurHufRate)}</TableCell>
                <TableCell>{formatCurrency(tier.total_investment_huf, currency, eurHufRate)}</TableCell>
                <TableCell>{formatCurrency(tier.break_even_price_huf, currency, eurHufRate)}</TableCell>
                <TableCell className={tier.net_profit_huf < 0 ? "text-red-600" : "text-emerald-600"}>
                  {formatCurrency(tier.net_profit_huf, currency, eurHufRate)}
                </TableCell>
                <TableCell>{formatPercent(tier.roi_percent)}</TableCell>
                <TableCell>{formatPercent(tier.net_yield_percent)}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>

      <div className="space-y-2">
        <p className="text-sm font-medium">Net profit projection</p>
        {tiers.map((tier) => (
          <div key={tier.tier} className="space-y-1">
            <div className="flex items-center justify-between text-xs text-muted-foreground">
              <span>{TIER_LABELS[tier.tier] ?? tier.tier}</span>
              <span>{formatCurrency(tier.net_profit_huf, currency, eurHufRate)}</span>
            </div>
            <div className="h-2 w-full overflow-hidden rounded-full bg-muted">
              <div
                className={cn(
                  "h-full rounded-full",
                  tier.net_profit_huf < 0 ? "bg-red-500" : tier.tier === bestTier ? "bg-emerald-500" : "bg-chart-1"
                )}
                style={{ width: `${Math.max((Math.abs(tier.net_profit_huf) / maxProfit) * 100, 2)}%` }}
              />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function FinancialBreakdownSection({
  deal,
  currency,
  eurHufRate,
  customCostInput,
  onCustomCostInputChange,
}: {
  deal: Deal;
  currency: Currency;
  eurHufRate: number;
  customCostInput: string;
  onCustomCostInputChange: (value: string) => void;
}) {
  const analysis = deal.analysis;
  const [selectedTierName, setSelectedTierName] = useState<RenovationTierName>(
    (deal.best_tier?.tier as RenovationTierName) ?? "medium"
  );

  const customCost = customCostInput.trim() === "" ? null : Number(customCostInput);
  const customTier = useMemo(() => {
    if (!analysis || customCost === null || Number.isNaN(customCost) || customCost < 0) return null;
    return computeCustomTier(analysis, customCost);
  }, [analysis, customCost]);

  if (!analysis) {
    return (
      <p className="text-sm text-muted-foreground">
        No district benchmark on file yet — add one via <code>POST /district-benchmarks</code> to see a
        renovation ROI projection for this listing.
      </p>
    );
  }

  const allTiers = customTier ? [...analysis.tiers, customTier] : analysis.tiers;
  const selectedTier = allTiers.find((t) => t.tier === selectedTierName) ?? allTiers[0];
  if (!selectedTier) return null;
  const bestTier = deal.best_tier?.tier;
  const isProfit = selectedTier.net_profit_huf >= 0;

  return (
    <div className="space-y-4">
      <div className="space-y-3 rounded-lg border p-3">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="custom-reno-cost">Custom renovation cost (€/m²)</Label>
            <Input
              id="custom-reno-cost"
              type="number"
              inputMode="decimal"
              min={0}
              placeholder="e.g. 350"
              className="w-40"
              value={customCostInput}
              onChange={(e) => {
                onCustomCostInputChange(e.target.value);
                if (e.target.value.trim() !== "") setSelectedTierName("custom");
              }}
            />
          </div>
          <p className="max-w-sm text-xs text-muted-foreground">
            Overrides the Light/Medium/Full presets with your own €/m² figure — recalculates every metric
            instantly, using {analysis.usable_area_sqm.toFixed(1)} sqm usable area (interior + 50% of
            balcony/terrace).
          </p>
        </div>
        <Slider
          min={0}
          max={1200}
          step={10}
          value={customCost ?? 0}
          onValueChange={(value) => {
            onCustomCostInputChange(String(value));
            setSelectedTierName("custom");
          }}
          formatLabel={(v) => `${v} €/m²`}
        />
      </div>

      <Tabs value={selectedTierName} onValueChange={(v) => setSelectedTierName(v as RenovationTierName)}>
        <TabsList>
          {allTiers.map((tier) => (
            <TabsTrigger key={tier.tier} value={tier.tier}>
              {TIER_LABELS[tier.tier] ?? tier.tier}
              {tier.tier === bestTier && <Badge variant="success" className="ml-1.5">Best</Badge>}
            </TabsTrigger>
          ))}
        </TabsList>
      </Tabs>

      <div className="grid gap-4 rounded-lg border p-4 sm:grid-cols-3">
        <div>
          <p className="text-xs text-muted-foreground">Net Flip Profit</p>
          <p className={cn("text-2xl font-bold", isProfit ? "text-emerald-600" : "text-red-600")}>
            {formatCurrency(selectedTier.net_profit_huf, currency, eurHufRate)}
          </p>
        </div>
        <div>
          <p className="text-xs text-muted-foreground">ROI</p>
          <RoiBadge roiPercent={selectedTier.roi_percent} />
        </div>
        <div>
          <p className="text-xs text-muted-foreground">Gross Yield / Net Cash-on-Cash</p>
          <p className="text-sm font-medium">
            {formatPercent(selectedTier.gross_yield_percent)} / {formatPercent(selectedTier.net_yield_percent)}
          </p>
        </div>
      </div>

      <dl className="space-y-1.5 text-sm">
        <div className="flex justify-between">
          <dt className="text-muted-foreground">Purchase price</dt>
          <dd className="font-medium">{formatCurrency(deal.price_huf, currency, eurHufRate)}</dd>
        </div>
        <div className="flex justify-between">
          <dt className="text-muted-foreground">Property transfer tax (illeték, 4%)</dt>
          <dd className="font-medium">{formatCurrency(analysis.property_transfer_tax_huf, currency, eurHufRate)}</dd>
        </div>
        <div className="flex justify-between">
          <dt className="text-muted-foreground">Legal / notary fee (1%)</dt>
          <dd className="font-medium">{formatCurrency(analysis.legal_notary_fee_huf, currency, eurHufRate)}</dd>
        </div>
        <div className="flex justify-between">
          <dt className="text-muted-foreground">
            Renovation cost ({TIER_LABELS[selectedTier.tier] ?? selectedTier.tier}, {selectedTier.cost_eur_per_sqm} €/sqm)
          </dt>
          <dd className="font-medium">{formatCurrency(selectedTier.renovation_cost_huf, currency, eurHufRate)}</dd>
        </div>
        <div className="flex justify-between">
          <dt className="text-muted-foreground">Contingency reserve (5%)</dt>
          <dd className="font-medium">{formatCurrency(selectedTier.safety_buffer_huf, currency, eurHufRate)}</dd>
        </div>
        <div className="flex justify-between border-t pt-1.5">
          <dt className="text-muted-foreground">Total investment (incl. contingency reserve)</dt>
          <dd className="font-medium">{formatCurrency(selectedTier.total_investment_huf, currency, eurHufRate)}</dd>
        </div>
        <div className="flex justify-between">
          <dt className="text-muted-foreground">Break-even sale price</dt>
          <dd className="font-medium">{formatCurrency(selectedTier.break_even_price_huf, currency, eurHufRate)}</dd>
        </div>
        <div className="flex justify-between">
          <dt className="text-muted-foreground">Weighted usable area</dt>
          <dd className="font-medium">
            {formatSqm(analysis.usable_area_sqm)}
            {analysis.balcony_sqm ? ` (${formatSqm(deal.size_sqm)} + ${formatSqm(analysis.balcony_sqm)} balcony × 50%)` : ""}
          </dd>
        </div>
        <div className="flex justify-between">
          <dt className="text-muted-foreground">Projected exit sale price</dt>
          <dd className="font-medium">{formatCurrency(selectedTier.exit_price_huf, currency, eurHufRate)}</dd>
        </div>
        {selectedTier.gross_annual_rent_huf !== null && (
          <div className="flex justify-between">
            <dt className="text-muted-foreground">Est. gross annual rent</dt>
            <dd className="font-medium">{formatCurrency(selectedTier.gross_annual_rent_huf, currency, eurHufRate)}</dd>
          </div>
        )}
      </dl>

      <Separator />

      <div>
        <h5 className="mb-2 text-sm font-semibold">Compare all tiers</h5>
        <TierComparisonTable tiers={allTiers} bestTier={bestTier} currency={currency} eurHufRate={eurHufRate} />
      </div>

      <p className="text-xs text-muted-foreground">
        Assumes a {analysis.eur_huf_rate.toFixed(0)} HUF/EUR rate and the district&apos;s average renovated
        €/sqm as exit price for every tier. Net yield assumes 20% of gross rent goes to
        management/maintenance/vacancy.
      </p>
    </div>
  );
}

function AutomatedUnderwritingSection({ deal, currency, eurHufRate }: { deal: Deal; currency: Currency; eurHufRate: number }) {
  const uw = deal.underwriting;
  if (!uw) {
    return (
      <p className="text-sm text-muted-foreground">
        Not yet underwritten by the automated agent — this runs automatically on the next scan, or trigger it
        manually via <code>POST /properties/{deal.id}/underwrite</code>.
      </p>
    );
  }

  const isRisk = uw.status?.startsWith("risk:") ?? false;
  const riskReasons = isRisk ? uw.status!.replace("risk:", "").split(",") : [];
  const riskLabels: Record<string, string> = {
    overpriced: "Asking price is above the district's turnkey median",
    below_hurdle_roi: "Projected flip ROI is below the 12% minimum hurdle rate",
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        {uw.confidence_tag === "High Potential Flip" && (
          <Badge variant="success" className="gap-1">
            <Sparkles className="h-3 w-3" />
            High Potential Flip
          </Badge>
        )}
        {uw.confidence_tag === "Buy & Hold Yield" && (
          <Badge variant="default" className="gap-1">
            <ShieldCheck className="h-3 w-3" />
            Buy &amp; Hold Yield
          </Badge>
        )}
        {!isRisk && uw.status === "validated" && (
          <Badge variant="outline" className="gap-1 text-emerald-600">
            <ShieldCheck className="h-3 w-3" />
            Validated
          </Badge>
        )}
        <Badge variant="secondary" className="gap-1">
          <Wrench className="h-3 w-3" />
          Est. renovation: {formatCurrency(uw.renovation_cost_huf, currency, eurHufRate)}
        </Badge>
      </div>

      {isRisk && (
        <div className="flex items-start gap-2 rounded-lg border border-destructive/50 bg-destructive/10 p-3 text-sm">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-destructive" />
          <div className="space-y-0.5">
            {riskReasons.map((reason) => (
              <p key={reason} className="text-destructive">
                {riskLabels[reason] ?? reason}
              </p>
            ))}
          </div>
        </div>
      )}

      <div className="grid gap-4 rounded-lg border p-4 sm:grid-cols-3">
        <div>
          <p className="text-xs text-muted-foreground">Net Profit (HUF / EUR)</p>
          <p
            className={cn(
              "text-lg font-bold",
              (uw.net_profit_huf ?? 0) >= 0 ? "text-emerald-600" : "text-red-600"
            )}
          >
            {formatHuf(uw.net_profit_huf)}
          </p>
          <p className="text-xs text-muted-foreground">
            {uw.net_profit_huf !== null ? formatEur(uw.net_profit_huf / eurHufRate) : "—"}
          </p>
        </div>
        <div>
          <p className="text-xs text-muted-foreground">Validated Flip ROI</p>
          <RoiBadge roiPercent={uw.flip_roi_percent} />
        </div>
        <div>
          <p className="text-xs text-muted-foreground">Agent Deal Score</p>
          <p className="text-lg font-bold">{uw.deal_score !== null ? `${uw.deal_score}/100` : "—"}</p>
        </div>
      </div>

      <dl className="space-y-1.5 text-sm">
        <div className="flex justify-between">
          <dt className="text-muted-foreground">Estimated market value (turnkey)</dt>
          <dd className="font-medium">{formatCurrency(uw.estimated_market_value_huf, currency, eurHufRate)}</dd>
        </div>
        <div className="flex justify-between">
          <dt className="text-muted-foreground">Total investment</dt>
          <dd className="font-medium">{formatCurrency(uw.total_investment_huf, currency, eurHufRate)}</dd>
        </div>
        <div className="flex justify-between">
          <dt className="text-muted-foreground">Rental yield</dt>
          <dd className="font-medium">{formatPercent(uw.rental_yield_percent)}</dd>
        </div>
      </dl>

      <p className="text-xs text-muted-foreground">
        Automated verdict from the underwriting agent, computed at the last scan
        {uw.updated_at ? ` (${formatDate(uw.updated_at)})` : ""} — a point-in-time read, not a live number. Uses a
        condition-based renovation estimate, 4% acquisition tax + 1.5% legal/closing, and a 3% broker fee on
        exit, independent of the interactive Light/Medium/Full tool above.
      </p>
    </div>
  );
}

export function DealDetailModal({ deal, onOpenChange, onDealUpdated, currency, eurHufRate }: DealDetailModalProps) {
  const sourceUrl = deal ? getSourceListingUrl(deal) : null;
  const isMock = deal ? isMockListingUrl(deal.source_url ?? deal.url) : false;
  const [customCostInput, setCustomCostInput] = useState<string>("");
  const customCostEurSqm = customCostInput.trim() === "" ? null : Number(customCostInput);

  // Reset the custom-cost input when a different deal is opened in the same modal instance.
  useEffect(() => {
    setCustomCostInput("");
  }, [deal?.id]);

  return (
    <Dialog open={deal !== null} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-3xl">
        {deal && (
          <>
            <DialogHeader>
              <div className="flex items-start justify-between gap-2 pr-8">
                <DialogTitle>{deal.title}</DialogTitle>
                <div className="flex shrink-0 items-center gap-2">
                  <ConditionBadge tag={deal.condition_tag} />
                  <DealScoreBadge score={deal.deal_score} band={deal.deal_score_band} />
                  <FavoriteToggle deal={deal} onUpdated={onDealUpdated} />
                </div>
              </div>
              <DialogDescription>
                District {deal.district} · {formatSqm(deal.size_sqm)} · {formatRooms(deal.rooms)} rooms
                {deal.condition ? ` · ${deal.condition}` : ""}
                {deal.portal ? ` · via ${deal.portal}` : ""}
              </DialogDescription>
            </DialogHeader>

            <div className="flex flex-wrap items-center gap-2">
              {sourceUrl ? (
                <Button className="w-fit" asChild>
                  <a href={sourceUrl} target="_blank" rel="noopener noreferrer">
                    <ExternalLink />
                    View Original Listing
                  </a>
                </Button>
              ) : (
                isMock && (
                  <Button className="w-fit" variant="outline" disabled title="Demo listing — no live source to open">
                    <ExternalLink />
                    View Original Listing
                  </Button>
                )
              )}
              <Button variant="outline" className="w-fit" asChild>
                <a href={getSpecSheetUrl(deal.id, eurHufRate)} target="_blank" rel="noreferrer">
                  <FileText />
                  Contractor Spec Sheet
                </a>
              </Button>
              <Button variant="outline" className="w-fit" asChild>
                <a href={getInvestmentMemoUrl(deal.id, eurHufRate)} target="_blank" rel="noreferrer">
                  <Sparkles />
                  Export Deal Memo (PDF)
                </a>
              </Button>
              <PipelineStatusSelect deal={deal} onUpdated={onDealUpdated} className="ml-auto w-40" />
            </div>
            {isMock && (
              <p className="-mt-1 text-xs text-muted-foreground">
                This is a demo listing — it has no real source page to link to.
              </p>
            )}

            <PhotoGallery images={deal.images ?? []} title={deal.title} />

            <div className="grid gap-6 sm:grid-cols-2">
              <div>
                <h4 className="mb-2 text-sm font-semibold">Asking price vs. district benchmark</h4>
                <BenchmarkComparison deal={deal} currency={currency} eurHufRate={eurHufRate} />
              </div>
              <div>
                <h4 className="mb-2 text-sm font-semibold">Listing summary</h4>
                <dl className="space-y-1 text-sm">
                  <div className="flex justify-between">
                    <dt className="text-muted-foreground">Asking price</dt>
                    <dd className="font-medium">{formatCurrency(deal.price_huf, currency, eurHufRate)}</dd>
                  </div>
                  <div className="flex justify-between">
                    <dt className="text-muted-foreground">Price / sqm</dt>
                    <dd className="font-medium">{formatCurrency(deal.price_per_sqm, currency, eurHufRate)}</dd>
                  </div>
                  {deal.balcony_sqm !== null && (
                    <div className="flex justify-between">
                      <dt className="text-muted-foreground">Balcony / terrace</dt>
                      <dd className="font-medium">{formatSqm(deal.balcony_sqm)}</dd>
                    </div>
                  )}
                </dl>
              </div>
            </div>

            <Separator />

            <div>
              <h4 className="mb-3 text-sm font-semibold">Financial ROI &amp; profit potential</h4>
              <FinancialBreakdownSection
                key={deal.id}
                deal={deal}
                currency={currency}
                eurHufRate={eurHufRate}
                customCostInput={customCostInput}
                onCustomCostInputChange={setCustomCostInput}
              />
            </div>

            <Separator />

            <div>
              <h4 className="mb-3 text-sm font-semibold">Automated underwriting verdict</h4>
              <AutomatedUnderwritingSection deal={deal} currency={currency} eurHufRate={eurHufRate} />
            </div>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}
