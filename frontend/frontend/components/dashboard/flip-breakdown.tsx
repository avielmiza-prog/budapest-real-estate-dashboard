"use client";

import { formatCurrency, formatPercent } from "@/lib/format";
import { useFlipText, type FlipTextKey } from "@/lib/flip-text";
import type { Currency, FlipResult } from "@/lib/types";
import { cn } from "@/lib/utils";

import { VerdictBadge } from "./verdict-badge";

const SCOPE_KEY: Record<FlipResult["scope"], FlipTextKey> = {
  full: "scopeFull",
  medium: "scopeMedium",
  refresh: "scopeRefresh",
  none: "scopeNone",
};

const REASON_KEYS = ["fallback_benchmark", "no_condition", "no_building_type", "above_renovated_market", "unusual_size"];

/** Line-by-line flip math from backend/app/flip_model.py, readable top to bottom. */
export function FlipBreakdown({
  flip,
  currency,
  eurHufRate,
}: {
  flip: FlipResult;
  currency: Currency;
  eurHufRate: number;
}) {
  const t = useFlipText();
  const money = (v: number | null | undefined) => formatCurrency(v, currency, eurHufRate);

  const rows: { label: string; value: number; sign?: "-" | "+"; strong?: boolean }[] = [
    { label: t("purchase"), value: flip.purchase_price_huf },
    { label: t("purchaseCosts"), value: flip.purchase_costs_huf, sign: "+" },
    { label: t("reno", { scope: t(SCOPE_KEY[flip.scope]) }), value: flip.renovation_cost_huf, sign: "+" },
    { label: t("contingency"), value: flip.contingency_huf, sign: "+" },
    { label: t("holding", { n: flip.holding_months }), value: flip.holding_cost_huf, sign: "+" },
    { label: t("totalCash"), value: flip.total_cash_needed_huf, strong: true },
    { label: t("salePrice"), value: flip.exit_price_huf, strong: true },
    { label: t("saleCosts"), value: flip.sale_costs_huf, sign: "-" },
    { label: t("tax"), value: flip.gains_tax_huf, sign: "-" },
  ];

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <VerdictBadge verdict={flip.verdict} size="lg" />
        <div className="text-sm">
          <span className="text-muted-foreground">{t("roi")}: </span>
          <span className="font-semibold">{formatPercent(flip.roi_percent)}</span>
          <span className="text-muted-foreground">
            {" "}
            ({formatPercent(flip.annualized_roi_percent)} {t("perYear")}, {flip.holding_months} {t("months")})
          </span>
        </div>
      </div>

      <div className="rounded-lg border bg-muted/40 p-4">
        <div className="text-xs uppercase tracking-wide text-muted-foreground">{t("offerUpTo")}</div>
        <div className="text-2xl font-bold">
          {flip.max_offer_price_huf ? money(flip.max_offer_price_huf) : t("noOffer")}
        </div>
        {flip.offer_gap_percent !== null && (
          <div
            className={cn(
              "text-sm",
              flip.offer_gap_percent > 0 ? "text-amber-700 dark:text-amber-400" : "text-emerald-700 dark:text-emerald-400"
            )}
          >
            {flip.offer_gap_percent > 0
              ? t("askingAbove", { n: Math.round(flip.offer_gap_percent) })
              : t("askingBelow", { n: Math.round(-flip.offer_gap_percent) })}
          </div>
        )}
        <p className="mt-1 text-xs text-muted-foreground">{t("maxOfferExplain")}</p>
      </div>

      <dl className="divide-y rounded-lg border text-sm">
        {rows.map((r) => (
          <div key={r.label} className={cn("flex justify-between gap-4 px-3 py-2", r.strong && "bg-muted/40 font-semibold")}>
            <dt className={r.strong ? "" : "text-muted-foreground"}>{r.label}</dt>
            <dd className="tabular-nums">
              {r.sign ?? ""}
              {money(r.value)}
            </dd>
          </div>
        ))}
        <div className="flex justify-between gap-4 px-3 py-2 text-base font-bold">
          <dt>{t("net")}</dt>
          <dd
            className={cn(
              "tabular-nums",
              flip.net_profit_huf >= 0 ? "text-emerald-700 dark:text-emerald-400" : "text-destructive"
            )}
          >
            {money(flip.net_profit_huf)}
          </dd>
        </div>
      </dl>

      <p className="text-xs text-muted-foreground">
        {t("exitBasis")}: {flip.exit_basis}, {money(flip.exit_price_sqm_huf)}/m²
      </p>
      {flip.confidence_reasons.length > 0 && (
        <div className="text-xs text-muted-foreground">
          <span className="font-medium">{t("whyLow")}</span>
          <ul className="ml-4 list-disc">
            {flip.confidence_reasons.map((r) => (
              <li key={r}>{REASON_KEYS.includes(r) ? t(`reason_${r}` as FlipTextKey) : r}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
