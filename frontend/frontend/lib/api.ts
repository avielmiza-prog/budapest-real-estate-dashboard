import { getStoredPasscode, passcodeHeaders } from "@/lib/access";
import type { DashboardStats, Deal, DealFilters, DistrictBenchmark, FxRate, PipelineStatus, ScraperStatus } from "@/lib/types";

// NEXT_PUBLIC_API_URL is the primary name (matches most starter templates);
// NEXT_PUBLIC_API_BASE_URL is kept as a fallback for anyone who already set
// that one. Both are inlined at build time by Next.js — set them in your
// deployment platform's env config before building, not after.
const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function getJson<T>(path: string, params: Record<string, string | number | boolean | null | undefined> = {}): Promise<T> {
  const url = new URL(path, API_BASE_URL);
  for (const [key, value] of Object.entries(params)) {
    if (value !== null && value !== undefined && value !== "") {
      url.searchParams.set(key, String(value));
    }
  }

  let response: Response;
  try {
    response = await fetch(url.toString(), { cache: "no-store", headers: passcodeHeaders() });
  } catch {
    throw new ApiError(
      `Could not reach the API at ${API_BASE_URL}. Is the FastAPI backend running (uvicorn app.main:app --reload)?`,
      0
    );
  }

  if (!response.ok) {
    const detail = await response.text().catch(() => "");
    throw new ApiError(detail || `Request to ${path} failed with status ${response.status}`, response.status);
  }

  return response.json() as Promise<T>;
}

async function postJson<T>(path: string, params: Record<string, string | number | boolean | null | undefined> = {}): Promise<T> {
  const url = new URL(path, API_BASE_URL);
  for (const [key, value] of Object.entries(params)) {
    if (value !== null && value !== undefined && value !== "") {
      url.searchParams.set(key, String(value));
    }
  }

  let response: Response;
  try {
    response = await fetch(url.toString(), { method: "POST", cache: "no-store", headers: passcodeHeaders() });
  } catch {
    throw new ApiError(
      `Could not reach the API at ${API_BASE_URL}. Is the FastAPI backend running (uvicorn app.main:app --reload)?`,
      0
    );
  }

  if (!response.ok) {
    const detail = await response.text().catch(() => "");
    throw new ApiError(detail || `Request to ${path} failed with status ${response.status}`, response.status);
  }

  return response.json() as Promise<T>;
}

/** Kicks off the autonomous multi-portal ingestion agent server-side (a no-op if a scan is already running). */
export function triggerScraperScan(maxListings = 30): Promise<ScraperStatus> {
  return postJson<ScraperStatus>("/api/scraper/trigger", { max_listings: maxListings });
}

export function getScraperStatus(): Promise<ScraperStatus> {
  return getJson<ScraperStatus>("/api/scraper/status");
}

export function getDashboardStats(eurHufRate: number): Promise<DashboardStats> {
  return getJson<DashboardStats>("/dashboard/stats", { eur_huf_rate: eurHufRate });
}

export function getDeals(filters: DealFilters, eurHufRate: number): Promise<Deal[]> {
  return getJson<Deal[]>("/deals", {
    district: filters.districts.length > 0 ? filters.districts.join(",") : null,
    min_roi: filters.minRoi,
    min_size_sqm: filters.minSize,
    max_size_sqm: filters.maxSize,
    min_price_huf: filters.minPrice,
    max_price_huf: filters.maxPrice,
    portal: filters.portals.length > 0 ? filters.portals.join(",") : null,
    favorites_only: filters.favoritesOnly || null,
    pipeline_status: filters.pipelineStatus,
    eur_huf_rate: eurHufRate,
  });
}

/**
 * PATCH a property's favorite/pipeline-status (or any other editable field) —
 * thin wrapper around the generic PATCH /properties/{id} endpoint. Returns
 * only the confirmed field values (the endpoint's response is a bare
 * PropertyOut, not the fully-enriched Deal shape with analysis/deal_score/
 * etc. — callers should merge these into their existing Deal, not replace it).
 */
export async function updateProperty(
  propertyId: number,
  patch: Partial<{ is_favorite: boolean; pipeline_status: PipelineStatus }>
): Promise<{ is_favorite: boolean; pipeline_status: PipelineStatus }> {
  const url = new URL(`/properties/${propertyId}`, API_BASE_URL);
  const response = await fetch(url.toString(), {
    method: "PATCH",
    headers: { "Content-Type": "application/json", ...passcodeHeaders() },
    body: JSON.stringify(patch),
  });
  if (!response.ok) {
    const detail = await response.text().catch(() => "");
    throw new ApiError(detail || `Failed to update property ${propertyId}`, response.status);
  }
  return response.json() as Promise<{ is_favorite: boolean; pipeline_status: PipelineStatus }>;
}

export function getFxRate(refresh = false): Promise<FxRate> {
  return getJson<FxRate>("/fx-rate", { refresh: refresh || null });
}

/** All district benchmarks on file — powers the map's district-polygon €/m² overlay. */
export function getDistrictBenchmarks(): Promise<DistrictBenchmark[]> {
  return getJson<DistrictBenchmark[]>("/district-benchmarks");
}

/**
 * Direct download URL for a property's Contractor Spec Sheet PDF — meant to
 * be used as a plain <a href> (browser navigation), not fetched via JS. The
 * backend sets Content-Disposition: attachment, which triggers a normal
 * download even across the localhost:3000 -> localhost:8000 origin boundary
 * (CORS only restricts JS reading a response, not top-level navigation).
 */
export function getSpecSheetUrl(propertyId: number, eurHufRate: number): string {
  const url = new URL(`/properties/${propertyId}/spec-sheet`, API_BASE_URL);
  url.searchParams.set("eur_huf_rate", String(eurHufRate));
  applyPasscodeQueryParam(url);
  return url.toString();
}

/** Same download-link convention as getSpecSheetUrl, for the Investment One-Pager PDF. */
export function getInvestmentMemoUrl(
  propertyId: number,
  eurHufRate: number,
  customRenovationCostEurSqm?: number | null
): string {
  const url = new URL(`/properties/${propertyId}/investment-memo`, API_BASE_URL);
  url.searchParams.set("eur_huf_rate", String(eurHufRate));
  if (customRenovationCostEurSqm !== null && customRenovationCostEurSqm !== undefined) {
    url.searchParams.set("custom_renovation_cost_eur_sqm", String(customRenovationCostEurSqm));
  }
  applyPasscodeQueryParam(url);
  return url.toString();
}

/**
 * These two links are opened as plain <a href> browser navigations, not
 * fetch() calls, so they can't carry the X-Access-Passcode header — the
 * backend's passcode gate accepts a `?passcode=` query param as a fallback
 * specifically for this (see app/access_control.py).
 */
function applyPasscodeQueryParam(url: URL): void {
  const passcode = getStoredPasscode();
  if (passcode) url.searchParams.set("passcode", passcode);
}
