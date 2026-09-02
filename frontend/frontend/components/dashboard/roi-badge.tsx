import { Badge } from "@/components/ui/badge";
import { formatPercent } from "@/lib/format";

// Thresholds match the platform's 10% minimum profitability hurdle (see
// backend/app/services/valuation_agent.MIN_HURDLE_ROI_PERCENT and
// app/dashboard.DEFAULT_MIN_FLIP_ROI_PERCENT): green at/above 15% (a
// healthy margin above the hurdle), yellow/orange for 10-14.9% (clears the
// hurdle but thin), red below 10% (sub-hurdle — only reachable when a
// caller explicitly widens the min-ROI filter past the default).
const ROI_GREEN_THRESHOLD_PERCENT = 15;
const ROI_HURDLE_PERCENT = 10;

export function RoiBadge({ roiPercent }: { roiPercent: number | null | undefined }) {
  if (roiPercent === null || roiPercent === undefined) {
    return <Badge variant="outline">No benchmark</Badge>;
  }
  const variant =
    roiPercent >= ROI_GREEN_THRESHOLD_PERCENT
      ? "success"
      : roiPercent >= ROI_HURDLE_PERCENT
        ? "warning"
        : "destructive";
  return <Badge variant={variant}>{formatPercent(roiPercent)} ROI</Badge>;
}
