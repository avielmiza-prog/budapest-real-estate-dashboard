// Budapest's 23 districts, in their conventional roman-numeral form — the
// same values app.analyzer.district_number_to_roman() on the backend
// produces, so these line up with what Property.district / DistrictBenchmark
// actually store.
export const BUDAPEST_DISTRICTS: string[] = [
  "I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X",
  "XI", "XII", "XIII", "XIV", "XV", "XVI", "XVII", "XVIII", "XIX", "XX",
  "XXI", "XXII", "XXIII",
];

export const DEFAULT_EUR_HUF_RATE = 400;

export const TIER_LABELS: Record<string, string> = {
  light: "Light",
  medium: "Medium",
  full: "Full",
  custom: "Custom",
};

// Portals the scraper engine supports — see backend/scraper/registry.py.
export const PORTALS: string[] = ["jofogas", "otthonterkep", "ingatlanbazar"];

export const PORTAL_LABELS: Record<string, string> = {
  jofogas: "Jófogás",
  otthonterkep: "Otthontérkép",
  ingatlanbazar: "Ingatlanbazár",
  mock: "Demo data",
};

// Slider bounds for the advanced filters — generous enough to cover the
// Budapest apartment market; each slider still accepts values beyond its
// travel range via the paired numeric inputs.
export const SIZE_FILTER_MIN_SQM = 0;
export const SIZE_FILTER_MAX_SQM = 300;

export const PRICE_FILTER_MIN_HUF = 0;
export const PRICE_FILTER_MAX_HUF = 300_000_000;

export const ROI_FILTER_MIN_PERCENT = -20;
export const ROI_FILTER_MAX_PERCENT = 60;

// Backend anomaly guardrails (scraper/anomaly_filter.py) reject anything
// outside 400k-4.5M HUF/sqm, so real listings never fall outside this
// range — a little headroom above/below keeps the slider's own extremes
// from looking like an artificial clamp.
export const PRICE_PER_SQM_FILTER_MIN_HUF = 0;
export const PRICE_PER_SQM_FILTER_MAX_HUF = 5_000_000;
