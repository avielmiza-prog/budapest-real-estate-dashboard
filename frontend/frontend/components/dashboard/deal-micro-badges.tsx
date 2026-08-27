import { Badge } from "@/components/ui/badge";
import type { Deal } from "@/lib/types";

// Net Cash-on-Cash (net_yield_percent) at or above this is called out as a
// "High Yield" deal — an all-cash-flip-model equivalent tends to run
// 2-4% net in this dataset, so 5%+ is a genuine standout, not the median.
const HIGH_YIELD_NET_PERCENT = 5;

// ROI badge tiers — same roi_percent already shown by RoiBadge next to these
// (deal.best_tier), so the two never disagree about which number is "the ROI".
const HIGH_ROI_PERCENT = 20;
const PRIME_FLIP_MIN_PERCENT = 15;

/** Small, glanceable signals shared by every card layout (grid/table/split). */
export function DealMicroBadges({ deal, className }: { deal: Deal; className?: string }) {
  const belowMarket = deal.discount_percent !== null && deal.discount_percent > 0;
  const highYield =
    deal.best_tier?.net_yield_percent !== null &&
    deal.best_tier?.net_yield_percent !== undefined &&
    deal.best_tier.net_yield_percent >= HIGH_YIELD_NET_PERCENT;
  const hasBalcony = deal.balcony_sqm !== null && deal.balcony_sqm > 0;
  // Persisted verdict from the backend's automated underwriting agent (see
  // app/services/valuation_agent.py) — null until at least one scan has
  // processed this listing, distinct from the live discount/yield signals above.
  const confidenceTag = deal.underwriting?.confidence_tag ?? null;
  const isRisk = deal.underwriting?.status?.startsWith("risk:") ?? false;

  const roiPercent = deal.best_tier?.roi_percent ?? null;
  const isHighRoi = roiPercent !== null && roiPercent > HIGH_ROI_PERCENT;
  const isPrimeFlip = roiPercent !== null && roiPercent >= PRIME_FLIP_MIN_PERCENT && roiPercent <= HIGH_ROI_PERCENT;

  if (!belowMarket && !highYield && !hasBalcony && !confidenceTag && !isRisk && !isHighRoi && !isPrimeFlip) return null;

  return (
    <div className={className}>
      {isHighRoi && (
        <Badge variant="success" className="text-[10px]">
          High ROI: &gt;20%
        </Badge>
      )}
      {isPrimeFlip && (
        <Badge variant="success" className="text-[10px]">
          Prime Flip: 15-20%
        </Badge>
      )}
      {confidenceTag === "High Potential Flip" && (
        <Badge variant="success" className="text-[10px]">
          High Potential Flip
        </Badge>
      )}
      {confidenceTag === "Buy & Hold Yield" && (
        <Badge variant="default" className="text-[10px]">
          Buy &amp; Hold Yield
        </Badge>
      )}
      {isRisk && (
        <Badge variant="destructive" className="text-[10px]">
          Risk Flagged
        </Badge>
      )}
      {belowMarket && (
        <Badge variant="success" className="text-[10px]">
          Below Market
        </Badge>
      )}
      {highYield && (
        <Badge variant="warning" className="text-[10px]">
          High Yield
        </Badge>
      )}
      {hasBalcony && (
        <Badge variant="outline" className="text-[10px]">
          Balcony
        </Badge>
      )}
    </div>
  );
}
