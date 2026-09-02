// Client-side mirror of backend/app/analyzer.py's per-tier math, used only
// for instant recalculation as the user edits the custom renovation €/sqm
// input in the deal detail modal (no network round-trip per keystroke). The
// server-computed `analysis` on the Deal is always the source of truth for
// the light/medium/full tiers and for the PDF export — this only recomputes
// the *custom* tier as a live preview. Keep this in sync with analyzer.py if
// the formulas there ever change.
import type { PropertyAnalysis, RenovationTier } from "@/lib/types";

const SAFETY_BUFFER_RATE = 0.05;
const RENTAL_OPEX_RATE = 0.2;
// 3% sales/broker commission on the exit price — matches backend/app/analyzer.py's
// BROKER_FEE_RATE, the platform's single source of truth for this fee.
const BROKER_FEE_RATE = 0.03;

export function computeCustomTier(analysis: PropertyAnalysis, customCostEurPerSqm: number): RenovationTier {
  const renovationCostHuf = analysis.usable_area_sqm * customCostEurPerSqm * analysis.eur_huf_rate;
  const safetyBufferHuf =
    SAFETY_BUFFER_RATE *
    (analysis.asking_price_huf + analysis.property_transfer_tax_huf + analysis.legal_notary_fee_huf + renovationCostHuf);
  const totalInvestmentHuf =
    analysis.asking_price_huf + analysis.acquisition_cost_huf + renovationCostHuf + safetyBufferHuf;
  const brokerFeeHuf = analysis.exit_price_huf * BROKER_FEE_RATE;
  const netProfitHuf = analysis.exit_price_huf - totalInvestmentHuf - brokerFeeHuf;
  const roiPercent = totalInvestmentHuf > 0 ? (netProfitHuf / totalInvestmentHuf) * 100 : null;

  let grossAnnualRentHuf: number | null = null;
  let grossYieldPercent: number | null = null;
  let netYieldPercent: number | null = null;
  if (analysis.avg_rent_huf_sqm && totalInvestmentHuf > 0) {
    grossAnnualRentHuf = analysis.avg_rent_huf_sqm * analysis.usable_area_sqm * 12;
    grossYieldPercent = (grossAnnualRentHuf / totalInvestmentHuf) * 100;
    netYieldPercent = ((grossAnnualRentHuf * (1 - RENTAL_OPEX_RATE)) / totalInvestmentHuf) * 100;
  }

  return {
    tier: "custom",
    cost_eur_per_sqm: customCostEurPerSqm,
    renovation_cost_huf: renovationCostHuf,
    safety_buffer_huf: safetyBufferHuf,
    total_investment_huf: totalInvestmentHuf,
    break_even_price_huf: totalInvestmentHuf / (1 - BROKER_FEE_RATE),
    exit_price_huf: analysis.exit_price_huf,
    broker_fee_huf: brokerFeeHuf,
    net_profit_huf: netProfitHuf,
    roi_percent: roiPercent,
    gross_annual_rent_huf: grossAnnualRentHuf,
    gross_yield_percent: grossYieldPercent,
    net_yield_percent: netYieldPercent,
  };
}
