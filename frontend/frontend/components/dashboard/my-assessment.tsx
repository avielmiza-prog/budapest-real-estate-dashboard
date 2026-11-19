"use client";

import { AlertTriangle, CheckCircle2, Sparkles } from "lucide-react";

import { formatCurrency } from "@/lib/format";
import { useFlipText, type FlipTextKey } from "@/lib/flip-text";
import type { Currency, FlipResult } from "@/lib/types";

const BLOCKERS = new Set(["usufruct", "municipal_rights", "auction", "co_ownership", "not_registered"]);

/** Plain-language verdict built from the flip numbers and the red flags found in the ad. */
export function MyAssessment({ flip, currency, eurHufRate }: { flip: FlipResult; currency: Currency; eurHufRate: number }) {
  const t = useFlipText();
  const money = (v: number | null | undefined) => formatCurrency(v, currency, eurHufRate);
  const red = flip.red_flags ?? [];
  const good = flip.positives ?? [];
  const hasBlocker = red.some((c) => BLOCKERS.has(c));
  const gap = flip.offer_gap_percent !== null ? Math.round(Math.abs(flip.offer_gap_percent)) : null;

  let headline: string;
  if (hasBlocker) headline = t("takeBlocker");
  else if (flip.verdict === "buy") headline = t("takeBuy", { profit: money(flip.net_profit_huf) });
  else if (flip.verdict === "consider")
    headline =
      flip.max_offer_price_huf && gap
        ? t("takeConsider", { offer: money(flip.max_offer_price_huf), gap })
        : t("takeConsiderNoGap");
  else headline = flip.max_offer_price_huf ? t("takeSkip", { offer: money(flip.max_offer_price_huf), gap: gap ?? 0 }) : t("takeSkipNever");

  const conf = flip.confidence === "high" ? t("confHigh") : flip.confidence === "medium" ? t("confMedium") : t("confLow");
  const adj = flip.flags_exit_factor !== undefined ? Math.round((1 - flip.flags_exit_factor) * 100) : 0;
  const label = (code: string) => t(`flag_${code}` as FlipTextKey);

  return (
    <div className="rounded-lg border-2 border-primary/30 bg-primary/5 p-4">
      <div className="mb-2 flex items-center gap-2 text-sm font-semibold">
        <Sparkles className="h-4 w-4" />
        {t("myTake")}
      </div>
      <p className="font-medium">{headline}</p>
      {(red.length > 0 || good.length > 0) && (
        <ul className="mt-3 space-y-1 text-sm">
          {red.map((c) => (
            <li key={c} className="flex items-start gap-2">
              <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber-600" />
              {label(c)}
            </li>
          ))}
          {good.map((c) => (
            <li key={c} className="flex items-start gap-2">
              <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-emerald-600" />
              {label(c)}
            </li>
          ))}
        </ul>
      )}
      {adj > 0 && <p className="mt-2 text-xs text-muted-foreground">{t("priceAdj", { n: adj })}</p>}
      <p className="mt-2 text-xs text-muted-foreground">{t("takeData", { conf })}</p>
    </div>
  );
}
