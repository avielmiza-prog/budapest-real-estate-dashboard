import { Badge } from "@/components/ui/badge";
import type { DealScoreBand } from "@/lib/types";

// Same green/yellow/red convention the split-view map pins use — one glance
// at either tells you the same story.
export function bandToColor(band: DealScoreBand | null | undefined): string {
  if (band === "high") return "#16a34a"; // emerald-600
  if (band === "fair") return "#f59e0b"; // amber-500
  if (band === "low") return "#dc2626"; // red-600
  return "#9ca3af"; // gray-400 — no score available
}

export function DealScoreBadge({
  score,
  band,
  className,
}: {
  score: number | null | undefined;
  band: DealScoreBand | null | undefined;
  className?: string;
}) {
  if (score === null || score === undefined) {
    return (
      <Badge variant="outline" className={className}>
        No score
      </Badge>
    );
  }
  const variant = band === "high" ? "success" : band === "fair" ? "warning" : "destructive";
  return (
    <Badge variant={variant} className={className} title="Deal Attractiveness Score (0-100)">
      {score}/100
    </Badge>
  );
}
