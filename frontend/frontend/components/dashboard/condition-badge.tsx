import { CONDITION_TAG_COLORS, type ConditionTag } from "@/lib/types";
import { cn } from "@/lib/utils";

/** Color-coded condition badge: Amber (Needs Renovation) / Slate (Average) / Emerald (Renovated) / Blue (New Construction). */
export function ConditionBadge({ tag, className }: { tag: ConditionTag; className?: string }) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full border px-2 py-0.5 text-[10px] font-medium",
        CONDITION_TAG_COLORS[tag],
        className
      )}
    >
      {tag}
    </span>
  );
}
