import type { Deal } from "@/lib/types";

// Mirrors app.crud.MOCK_URL_PREFIX on the backend — scripts/seed_data.py
// stamps every fake/demo listing's url with this prefix specifically so
// mock rows can always be told apart from real scraped ones.
const MOCK_URL_PREFIX = "https://mock.";

export function isMockListingUrl(url: string | null | undefined): boolean {
  return !!url && url.startsWith(MOCK_URL_PREFIX);
}

/**
 * The real, external source-portal URL for a deal's "View Original Listing"
 * link — or null if there isn't one to show (missing, or a mock/demo
 * listing with no live source to send someone to).
 */
export function getSourceListingUrl(deal: Deal): string | null {
  const url = deal.source_url ?? deal.url;
  if (!url || isMockListingUrl(url)) return null;
  return url;
}
