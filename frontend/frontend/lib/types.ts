// Mirrors the shapes returned by the FastAPI backend — see
// backend/app/dashboard.py (list_deals/compute_stats), backend/app/analyzer.py
// (PropertyAnalysis/RenovationTierResult), and backend/app/deal_score.py.

export type RenovationTierName = "light" | "medium" | "full" | "custom";

export interface RenovationTier {
  tier: RenovationTierName;
  cost_eur_per_sqm: number;
  renovation_cost_huf: number;
  safety_buffer_huf: number;
  total_investment_huf: number;
  break_even_price_huf: number;
  exit_price_huf: number;
  broker_fee_huf: number;
  net_profit_huf: number;
  roi_percent: number | null;
  gross_annual_rent_huf: number | null;
  gross_yield_percent: number | null;
  net_yield_percent: number | null;
}

export interface PropertyAnalysis {
  size_sqm: number;
  district: string | null;
  asking_price_huf: number;
  eur_huf_rate: number;
  acquisition_cost_huf: number;
  property_transfer_tax_huf: number;
  legal_notary_fee_huf: number;
  avg_price_sqm_renovated_huf: number;
  exit_price_huf: number;
  balcony_sqm: number | null;
  usable_area_sqm: number;
  avg_rent_huf_sqm: number | null;
  tiers: RenovationTier[];
  // Transparency on avg_price_sqm_renovated_huf's origin — see
  // backend/app/services/stats_service.py's live-vs-fallback median computation.
  district_median_sample_count: number | null;
  district_median_source: "live" | "fallback" | null;
}

export type PipelineStatus = "new" | "reviewing" | "tour_scheduled" | "offer_sent" | "archived";

export const PIPELINE_STATUSES: PipelineStatus[] = [
  "new",
  "reviewing",
  "tour_scheduled",
  "offer_sent",
  "archived",
];

export const PIPELINE_STATUS_LABELS: Record<PipelineStatus, string> = {
  new: "New Deal",
  reviewing: "Under Review",
  tour_scheduled: "Tour Bookmarked",
  offer_sent: "LOI / Offer Sent",
  archived: "Archived",
};

export type DealScoreBand = "high" | "fair" | "low";

export type UnderwritingConfidenceTag = "High Potential Flip" | "Buy & Hold Yield";

// Persisted verdict from the backend's automated underwriting agent
// (app/services/valuation_agent.py) — computed once per scan, not live like
// `analysis`/`deal_score` above. null until at least one scan (or a manual
// POST /properties/{id}/underwrite) has processed this listing.
export interface Underwriting {
  estimated_market_value_huf: number | null;
  renovation_cost_huf: number | null;
  total_investment_huf: number | null;
  net_profit_huf: number | null;
  flip_roi_percent: number | null;
  rental_yield_percent: number | null;
  deal_score: number | null;
  status: string | null; // "validated" | "risk:overpriced" | "risk:below_hurdle_roi" | "risk:overpriced,below_hurdle_roi" | "no_benchmark" | "insufficient_data"
  confidence_tag: UnderwritingConfidenceTag | null;
  updated_at: string | null;
}

// Standardized English condition tag — see backend/app/condition_classifier.py.
export type ConditionTag = "Needs Renovation" | "Average" | "Renovated" | "New Construction";

export const CONDITION_TAG_COLORS: Record<ConditionTag, string> = {
  "Needs Renovation": "bg-amber-100 text-amber-800 border-amber-200",
  Average: "bg-slate-100 text-slate-700 border-slate-200",
  Renovated: "bg-emerald-100 text-emerald-800 border-emerald-200",
  "New Construction": "bg-blue-100 text-blue-800 border-blue-200",
};

// One Conservative/Base/Optimistic sensitivity scenario — see
// backend/app/services/scenario_analysis.py.
export interface Scenario {
  exit_price_huf: number;
  renovation_cost_huf: number;
  total_investment_huf: number;
  net_profit_huf: number;
  roi_percent: number | null;
}

export type ScenarioName = "conservative" | "base" | "optimistic";

export const SCENARIO_NAMES: ScenarioName[] = ["conservative", "base", "optimistic"];

export const SCENARIO_LABELS: Record<ScenarioName, string> = {
  conservative: "Conservative",
  base: "Base",
  optimistic: "Optimistic",
};

export interface Scenarios {
  conservative: Scenario;
  base: Scenario;
  optimistic: Scenario;
}

// Building construction type — see backend/app/building_classifier.py.
export type BuildingType = "Brick Classical (Polgári)" | "Panel Block (Panelház)" | "New Build (Új építés)";

export interface Deal {
  id: number;
  title: string;
  district: string;
  sub_district: string | null; // micro-neighborhood, e.g. "Újlipótváros" — see backend/app/sub_district.py
  address: string | null;
  size_sqm: number | null;
  rooms: number | null;
  balcony_sqm: number | null;
  building_type: BuildingType | string | null;
  ceiling_height_m: number | null;
  price_huf: number | null;
  price_eur: number | null;
  price_per_sqm: number | null;
  url: string | null;
  source_url: string | null; // the exact source-portal listing page (alias of `url`)
  duplicate_source_urls: string[]; // other portals' URLs for this same listing — see scraper/dedup.py
  condition: string | null;
  condition_tag: ConditionTag; // standardized English tag derived from `condition` — see app.condition_classifier
  images: string[] | null;
  portal: string | null;
  latitude: number | null;
  longitude: number | null;
  is_favorite: boolean;
  pipeline_status: PipelineStatus;
  notes: string | null;
  created_at: string | null;
  analysis: PropertyAnalysis | null;
  best_tier: RenovationTier | null;
  discount_percent: number | null;
  deal_score: number | null;
  deal_score_band: DealScoreBand | null;
  underwriting: Underwriting | null;
  scenarios: Scenarios | null;
  // Freshness + realistic flip verdict (backend/app/flip_model.py)
  last_seen_at?: string | null;
  is_stale?: boolean;
  previous_price_huf?: number | null;
  price_drop_percent?: number | null;
  flip?: FlipResult | null;
}

export type Verdict = "buy" | "consider" | "skip";

export interface FlipResult {
  condition_tag: string;
  scope: "full" | "medium" | "refresh" | "none";
  usable_area_sqm: number;
  purchase_price_huf: number;
  purchase_costs_huf: number;
  renovation_cost_huf: number;
  contingency_huf: number;
  holding_months: number;
  holding_cost_huf: number;
  total_cash_needed_huf: number;
  exit_price_sqm_huf: number;
  exit_price_huf: number;
  sale_costs_huf: number;
  profit_before_tax_huf: number;
  gains_tax_huf: number;
  net_profit_huf: number;
  roi_percent: number;
  annualized_roi_percent: number;
  max_offer_price_huf: number | null;
  offer_gap_percent: number | null;
  discount_vs_market_percent: number | null;
  verdict: Verdict;
  confidence: "high" | "medium" | "low";
  confidence_reasons: string[];
  exit_basis: string;
}

export interface TopUndervaluedDeal {
  property_id: number;
  title: string;
  district: string;
  price_huf: number | null;
  price_per_sqm: number | null;
  benchmark_price_per_sqm: number | null;
  discount_percent: number | null;
}

export interface DashboardStats {
  total_listings: number;
  avg_price_sqm_huf: number | null;
  avg_price_sqm_eur: number | null;
  eur_huf_rate: number;
  top_undervalued: TopUndervaluedDeal[];
  is_today_only: boolean;
  today_new_listings: number;
  verdict_counts?: Record<Verdict, number>;
  last_scan_at?: string | null;
  computed_at: string;
}

// Mirrors app/dashboard.py's SORT_OPTIONS — kept in this exact order since
// the sort dropdown renders options in this order.
export type SortOption =
  | "newest"
  | "price_desc"
  | "price_asc"
  | "score_desc"
  | "roi_desc"
  | "sqm_asc"
  | "roi_score_desc"
  | "profit_desc";

export const SORT_OPTIONS: SortOption[] = [
  "roi_score_desc",
  "newest",
  "price_desc",
  "price_asc",
  "score_desc",
  "roi_desc",
  "sqm_asc",
  "profit_desc",
];

// Default sort: strict Net ROI (underwriting flip_roi_percent) descending,
// Deal Score as the tiebreaker — surfaces the best underwritten deals first.
export const DEFAULT_SORT: SortOption = "roi_score_desc";

// Default minimum Net ROI filter — matches the backend's strict profitability
// hurdle (app/services/valuation_agent.MIN_HURDLE_ROI_PERCENT). The backend
// already enforces this hurdle server-side regardless of this client filter,
// so this just keeps the UI's own slider in sync with what's actually shown.
export const DEFAULT_MIN_ROI_PERCENT = 10;

export const SORT_OPTION_LABELS: Record<SortOption, string> = {
  roi_score_desc: "Highest ROI / Best Deal Score",
  profit_desc: "Highest net profit",
  newest: "Newest Added",
  price_desc: "Price: High to Low",
  price_asc: "Price: Low to High",
  score_desc: "Highest Deal Score",
  roi_desc: "Best ROI / Yield",
  sqm_asc: "Price/sqm: Low to High",
};

export interface DealFilters {
  districts: string[]; // roman numerals, e.g. ["VII", "VIII"] — empty means "all districts"
  minRoi: number | null; // percent
  minSize: number | null; // sqm
  maxSize: number | null; // sqm
  minPrice: number | null; // HUF
  maxPrice: number | null; // HUF
  minPricePerSqm: number | null; // HUF/sqm
  maxPricePerSqm: number | null; // HUF/sqm
  portals: string[]; // e.g. ["jofogas", "ingatlanbazar"] — empty means "all portals"
  favoritesOnly: boolean;
  pipelineStatus: PipelineStatus | null; // null means "all statuses"
  sortBy: SortOption;
  verdict: "buy" | "consider" | "all"; // "consider" tab shows buy + consider
}

// Also doubles as "Clear filters" — clearing resets to the platform's
// strict 10% Net ROI baseline, not an unfiltered view (the backend enforces
// that hurdle server-side by default regardless, so this keeps the UI honest
// about what's actually being shown).
export const EMPTY_FILTERS: DealFilters = {
  districts: [],
  // No ROI slider default any more: the verdict tabs (buy / worth
  // negotiating / all) do that job, using the after-tax flip model.
  minRoi: null,
  minSize: null,
  maxSize: null,
  minPrice: null,
  maxPrice: null,
  minPricePerSqm: null,
  maxPricePerSqm: null,
  portals: [],
  favoritesOnly: false,
  pipelineStatus: null,
  sortBy: DEFAULT_SORT,
  verdict: "consider",
};

export type ViewMode = "simple" | "table" | "card" | "split";

export interface DistrictBenchmark {
  district_number: number;
  avg_price_sqm_raw: number | null;
  avg_price_sqm_renovated: number | null;
  avg_rent_huf_sqm: number | null;
  centroid_lat: number | null;
  centroid_lng: number | null;
  updated_at: string;
  // Set by backend/app/services/stats_service.py's update_district_benchmarks().
  sample_count_raw: number | null;
  sample_count_renovated: number | null;
  source_raw: "live" | "fallback" | null;
  source_renovated: "live" | "fallback" | null;
  p85_price_sqm_renovated: number | null;
}

// Median HUF/sqm segmented by district AND building type — see
// backend/app/models.py's BuildingTypeBenchmark.
export interface BuildingTypeBenchmark {
  district_number: number;
  building_type: string;
  avg_price_sqm: number | null;
  sample_count: number;
  updated_at: string;
}

export interface ScraperStatus {
  is_running: boolean;
  started_at: string | null;
  finished_at: string | null;
  last_result: { stored: number; total: number } | null;
  error: string | null;
}

export type Currency = "HUF" | "EUR";

export interface FxRate {
  rate: number;
  updated_at: string;
  source: string;
  is_live: boolean;
}
