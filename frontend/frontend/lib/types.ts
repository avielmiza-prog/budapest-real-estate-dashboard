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

export interface Deal {
  id: number;
  title: string;
  district: string;
  address: string | null;
  size_sqm: number | null;
  rooms: number | null;
  balcony_sqm: number | null;
  price_huf: number | null;
  price_eur: number | null;
  price_per_sqm: number | null;
  url: string | null;
  source_url: string | null; // the exact source-portal listing page (alias of `url`)
  condition: string | null;
  images: string[] | null;
  portal: string | null;
  latitude: number | null;
  longitude: number | null;
  is_favorite: boolean;
  pipeline_status: PipelineStatus;
  created_at: string | null;
  analysis: PropertyAnalysis | null;
  best_tier: RenovationTier | null;
  discount_percent: number | null;
  deal_score: number | null;
  deal_score_band: DealScoreBand | null;
  underwriting: Underwriting | null;
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
  computed_at: string;
}

// Mirrors app/dashboard.py's SORT_OPTIONS — kept in this exact order since
// the sort dropdown renders options in this order.
export type SortOption = "newest" | "price_desc" | "price_asc" | "score_desc" | "roi_desc" | "sqm_asc";

export const SORT_OPTIONS: SortOption[] = ["newest", "price_desc", "price_asc", "score_desc", "roi_desc", "sqm_asc"];

export const SORT_OPTION_LABELS: Record<SortOption, string> = {
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
  portals: string[]; // e.g. ["jofogas", "ingatlanbazar"] — empty means "all portals"
  favoritesOnly: boolean;
  pipelineStatus: PipelineStatus | null; // null means "all statuses"
  sortBy: SortOption;
}

export const EMPTY_FILTERS: DealFilters = {
  districts: [],
  minRoi: null,
  minSize: null,
  maxSize: null,
  minPrice: null,
  maxPrice: null,
  portals: [],
  favoritesOnly: false,
  pipelineStatus: null,
  sortBy: "newest",
};

export type ViewMode = "table" | "card" | "split";

export interface DistrictBenchmark {
  district_number: number;
  avg_price_sqm_raw: number | null;
  avg_price_sqm_renovated: number | null;
  avg_rent_huf_sqm: number | null;
  centroid_lat: number | null;
  centroid_lng: number | null;
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
