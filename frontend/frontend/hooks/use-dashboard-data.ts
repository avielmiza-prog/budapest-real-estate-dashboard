"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { ApiError, DEALS_PAGE_SIZE, getDashboardStats, getDeals } from "@/lib/api";
import type { DashboardStats, Deal, DealFilters } from "@/lib/types";
import { EMPTY_FILTERS } from "@/lib/types";

import { useDebouncedValue } from "./use-debounced-value";

interface UseDashboardDataResult {
  stats: DashboardStats | null;
  deals: Deal[];
  total: number;
  setDeals: (updater: Deal[] | ((prev: Deal[]) => Deal[])) => void;
  filters: DealFilters;
  setFilters: (filters: DealFilters) => void;
  isLoading: boolean;
  isLoadingMore: boolean;
  isSlow: boolean;
  error: string | null;
  refresh: () => void;
  loadMore: () => void;
}

/** Merges a favorite/status PATCH result into the deals list without a full refetch. */
export function updateDealInList(deals: Deal[], updated: Deal): Deal[] {
  return deals.map((d) => (d.id === updated.id ? { ...d, ...updated } : d));
}

// The free Render server sleeps after 15 idle minutes; the first request
// then takes ~50s. After this long we tell the user it's waking up instead
// of showing an endless spinner that looks like the site is broken.
const SLOW_REQUEST_MS = 6000;

/**
 * eurHufRate is owned by the caller (see hooks/use-fx-rate.ts). Deals are
 * fetched one page at a time (DEALS_PAGE_SIZE); loadMore() appends the next.
 */
export function useDashboardData(eurHufRate: number): UseDashboardDataResult {
  const [filters, setFilters] = useState<DealFilters>(EMPTY_FILTERS);
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [deals, setDeals] = useState<Deal[]>([]);
  const [total, setTotal] = useState(0);
  const [isLoading, setIsLoading] = useState(true);
  const [isLoadingMore, setIsLoadingMore] = useState(false);
  const [isSlow, setIsSlow] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [refreshToken, setRefreshToken] = useState(0);
  const debouncedFilters = useDebouncedValue(filters, 300);
  const requestId = useRef(0);

  const refresh = useCallback(() => setRefreshToken((t) => t + 1), []);

  useEffect(() => {
    const id = ++requestId.current;
    setIsLoading(true);
    setIsSlow(false);
    setError(null);
    const slowTimer = setTimeout(() => {
      if (requestId.current === id) setIsSlow(true);
    }, SLOW_REQUEST_MS);

    Promise.all([getDashboardStats(eurHufRate), getDeals(debouncedFilters, eurHufRate, 0, DEALS_PAGE_SIZE)])
      .then(([statsResult, page]) => {
        if (requestId.current !== id) return;
        setStats(statsResult);
        setDeals(page.deals);
        setTotal(page.total);
      })
      .catch((err: unknown) => {
        if (requestId.current !== id) return;
        setError(err instanceof ApiError ? err.message : "Something went wrong loading the dashboard.");
      })
      .finally(() => {
        clearTimeout(slowTimer);
        if (requestId.current === id) {
          setIsLoading(false);
          setIsSlow(false);
        }
      });

    return () => clearTimeout(slowTimer);
  }, [debouncedFilters, eurHufRate, refreshToken]);

  const loadMore = useCallback(() => {
    if (isLoadingMore || deals.length >= total) return;
    const id = requestId.current;
    setIsLoadingMore(true);
    getDeals(debouncedFilters, eurHufRate, deals.length, DEALS_PAGE_SIZE)
      .then((page) => {
        if (requestId.current !== id) return;
        setDeals((prev) => {
          const seen = new Set(prev.map((d) => d.id));
          return [...prev, ...page.deals.filter((d) => !seen.has(d.id))];
        });
        setTotal(page.total);
      })
      .catch(() => {
        /* keep what we have; the button stays available to retry */
      })
      .finally(() => setIsLoadingMore(false));
  }, [debouncedFilters, eurHufRate, deals.length, total, isLoadingMore]);

  return {
    stats,
    deals,
    total,
    setDeals,
    filters,
    setFilters,
    isLoading,
    isLoadingMore,
    isSlow,
    error,
    refresh,
    loadMore,
  };
}
