"use client";

import { useFlipText } from "@/lib/flip-text";
import type { Verdict } from "@/lib/types";
import { cn } from "@/lib/utils";

const STYLE: Record<Verdict, string> = {
  buy: "bg-emerald-600 text-white",
  consider: "bg-amber-500 text-white",
  skip: "bg-zinc-200 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300",
};

export function VerdictBadge({ verdict, size = "md" }: { verdict: Verdict; size?: "md" | "lg" }) {
  const t = useFlipText();
  const label = verdict === "buy" ? t("verdictBuy") : verdict === "consider" ? t("verdictConsider") : t("verdictSkip");
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full font-semibold",
        size === "lg" ? "px-4 py-1.5 text-base" : "px-2.5 py-0.5 text-xs",
        STYLE[verdict]
      )}
    >
      {label}
    </span>
  );
}
