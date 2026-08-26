import { Badge } from "@/components/ui/badge";
import type { Deal } from "@/lib/types";

// Net Cash-on-Cash (net_yield_percent) at or above this is called out as a
// "High Yield" deal — an all-cash-flip-model equivalent tends to run
// 2-4% net in this dataset, so 5%+ is a genuine standout, not the median.
const HIGH_YIELD_NET_PERCENT = 5;

/** Small, glanceable signals shared by every card layout (grid/table/split). */
export function DealMicroBadges({ deal, className }: { deal: Deal; className?: string }) {
  const belowMarket = deal.discount_percent !== null && deal.discount_percent > 0;
  const highYield =
    deal.best_tier?.net_yield_percent !== null &&
    deal.best_tier?.net_yield_percent !== undefined &&
    deal.best_tier.net_yield_percent >= HIGH_YIELD_NET_PERCENT;
  const hasBalcony = deal.balcony_sqm !== null && deal.balcony_sqm > 0;

  if (!belowMarket && !highYield && !hasBalcony) return null;

  return (
    <div className={className}>
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
