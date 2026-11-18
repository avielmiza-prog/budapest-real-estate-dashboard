import { getStoredPasscode, passcodeHeaders } from "@/lib/access";
import type { DashboardStats, Deal, DealFilters, DistrictBenchmark, FxRate, PipelineStatus, ScraperStatus } from "@/lib/types";

// NEXT_PUBLIC_API_URL is the primary name (matches most starter templates);
// NEXT_PUBLIC_API_BASE_URL is kept as a fallback for anyone who already set
// that one. Both are inlined at build time by Next.js — set them in your
// deployment platform's env config before building, not after. Either one,
// if set, always wins over everything below.
//
// With neither set, this now branches on where the page is actually being
// viewed from (window.location.hostname), not just NODE_ENV — a build-time
// flag can't tell "vercel prod build" apart from "vercel prod build running
// via `vercel dev` on localhost", but the browser's own hostname always
// reflects reality. Local dev (localhost/127.0.0.1) falls back to
// localhost:8000; anything else (the deployed Vercel domain, a preview
// URL, SSR/build-time evaluation with no window) falls back to the
// deployed Render backend, so a local `next dev` never accidentally reads
// from — or mutates — the live production database.
const LOCAL_HOSTNAMES = new Set(["localhost", "127.0.0.1", "[::1]"]);
const PRODUCTION_API_FALLBACK = "https://budapest-real-estate-dashboard.onrender.com";
const LOCAL_API_FALLBACK = "http://localhost:8000";

function resolveApiBaseUrl(): string {
  const explicit = process.env.NEXT_PUBLIC_API_URL || process.env.NEXT_PUBLIC_API_BASE_URL;
  if (explicit) return explicit;
  if (typeof window !== "undefined" && LOCAL_HOSTNAMES.has(window.location.hostname)) {
    return LOCAL_API_FALLBACK;
  }
  return PRODUCTION_API_FALLBACK;
}

export const API_BASE_URL = resolveApiBaseUrl();

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

async function getJsonWithHeaders<T>(
  path: string,
  params: Record<string, string | number | boolean | null | undefined> = {}
): Promise<{ data: T; headers: Headers }> {
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
    throw new ApiError(`Could not reach the API at ${API_BASE_URL}.`, 0);
  }
  if (!response.ok) {
    const detail = await response.text().catch(() => "");
    throw new ApiError(detail || `Request to ${path} failed with status ${response.status}`, response.status);
  }
  return { data: (await response.json()) as T, headers: response.headers };
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
export function triggerScraperScan(maxListings = 150): Promise<ScraperStatus> {
  return postJson<ScraperStatus>("/api/scraper/trigger", { max_listings: maxListings });
}

export function getScraperStatus(): Promise<ScraperStatus> {
  return getJson<ScraperStatus>("/api/scraper/status");
}

export function getDashboardStats(eurHufRate: number): Promise<DashboardStats> {
  return getJson<DashboardStats>("/dashboard/stats", { eur_huf_rate: eurHufRate });
}

function dealFiltersToParams(
  filters: DealFilters,
  eurHufRate: number
): Record<string, string | number | boolean | null | undefined> {
  return {
    district: filters.districts.length > 0 ? filters.districts.join(",") : null,
    min_roi: filters.minRoi,
    min_size_sqm: filters.minSize,
    max_size_sqm: filters.maxSize,
    min_price_huf: filters.minPrice,
    max_price_huf: filters.maxPrice,
    min_price_per_sqm: filters.minPricePerSqm,
    max_price_per_sqm: filters.maxPricePerSqm,
    portal: filters.portals.length > 0 ? filters.portals.join(",") : null,
    favorites_only: filters.favoritesOnly || null,
    pipeline_status: filters.pipelineStatus,
    eur_huf_rate: eurHufRate,
    sort: filters.sortBy,
    verdict: filters.verdict === "buy" ? "buy" : filters.verdict === "consider" ? "buy,consider" : null,
    // The backend no longer applies a hidden 10% hurdle; send an explicit
    // "no hurdle" so older backends don't silently hide listings either.
    min_flip_roi: -1000,
  };
}

export const DEALS_PAGE_SIZE = 40;

/**
 * One page of deals plus the total number matching (X-Total-Count).
 * Paging matters: rendering thousands of rows at once froze the browser,
 * especially on a phone.
 */
export async function getDeals(
  filters: DealFilters,
  eurHufRate: number,
  skip = 0,
  limit = DEALS_PAGE_SIZE
): Promise<{ deals: Deal[]; total: number }> {
  const { data, headers } = await getJsonWithHeaders<Deal[]>("/deals", {
    ...dealFiltersToParams(filters, eurHufRate),
    skip,
    limit,
  });
  const total = Number(headers.get("X-Total-Count"));
  return { deals: data, total: Number.isFinite(total) && total > 0 ? total : skip + data.length };
}

/**
 * Direct download URL for GET /deals/export.csv — the exact same
 * filtered/sorted set getDeals() would return for these filters, as a CSV
 * file. Same plain-<a>-navigation convention as getSpecSheetUrl below.
 */
export function getDealsExportCsvUrl(filters: DealFilters, eurHufRate: number): string {
  const url = new URL("/deals/export.csv", API_BASE_URL);
  for (const [key, value] of Object.entries(dealFiltersToParams(filters, eurHufRate))) {
    if (value !== null && value !== undefined && value !== "") {
      url.searchParams.set(key, String(value));
    }
  }
  applyPasscodeQueryParam(url);
  return url.toString();
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
  patch: Partial<{ is_favorite: boolean; pipeline_status: PipelineStatus; notes: string }>
): Promise<{ is_favorite: boolean; pipeline_status: PipelineStatus; notes: string | null }> {
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
  return response.json() as Promise<{ is_favorite: boolean; pipeline_status: PipelineStatus; notes: string | null }>;
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

/** Same download-link convention as getSpecSheetUrl, for the (English) Deal Memo PDF. */
export function getInvestmentMemoUrl(propertyId: number, eurHufRate: number): string {
  const url = new URL(`/properties/${propertyId}/investment-memo`, API_BASE_URL);
  url.searchParams.set("eur_huf_rate", String(eurHufRate));
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
