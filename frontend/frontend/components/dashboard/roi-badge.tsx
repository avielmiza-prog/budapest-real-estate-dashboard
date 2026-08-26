import { Badge } from "@/components/ui/badge";
import { formatPercent } from "@/lib/format";

export function RoiBadge({ roiPercent }: { roiPercent: number | null | undefined }) {
  if (roiPercent === null || roiPercent === undefined) {
    return <Badge variant="outline">No benchmark</Badge>;
  }
  const variant = roiPercent >= 20 ? "success" : roiPercent >= 0 ? "warning" : "destructive";
  return <Badge variant={variant}>{formatPercent(roiPercent)} ROI</Badge>;
}
