"use client";

import { useCallback, useEffect, useState } from "react";

import { ApiError, getDashboardStats, getDeals } from "@/lib/api";
import type { DashboardStats, Deal, DealFilters } from "@/lib/types";
import { EMPTY_FILTERS } from "@/lib/types";

import { useDebouncedValue } from "./use-debounced-value";

interface UseDashboardDataResult {
  stats: DashboardStats | null;
  deals: Deal[];
  setDeals: (updater: Deal[] | ((prev: Deal[]) => Deal[])) => void;
  filters: DealFilters;
  setFilters: (filters: DealFilters) => void;
  isLoading: boolean;
  error: string | null;
  refresh: () => void;
}

/** Merges a favorite/status PATCH result into the deals list without a full refetch. */
export function updateDealInList(deals: Deal[], updated: Deal): Deal[] {
  return deals.map((d) => (d.id === updated.id ? { ...d, ...updated } : d));
}

/**
 * eurHufRate is owned by the caller (see hooks/use-fx-rate.ts) — this hook
 * just consumes it to fetch stats/deals, so there's a single source of
 * truth for "the rate" shared with whatever else displays/edits it (the
 * TopBar's live FX input).
 */
export function useDashboardData(eurHufRate: number): UseDashboardDataResult {
  const [filters, setFilters] = useState<DealFilters>(EMPTY_FILTERS);
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [deals, setDeals] = useState<Deal[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [refreshToken, setRefreshToken] = useState(0);
  // Sliders fire on every drag step — debounce the fetch (not the displayed
  // filter state) so the UI stays responsive without hammering the API.
  const debouncedFilters = useDebouncedValue(filters, 300);

  const refresh = useCallback(() => setRefreshToken((t) => t + 1), []);

  useEffect(() => {
    let cancelled = false;
    setIsLoading(true);
    setError(null);

    Promise.all([getDashboardStats(eurHufRate), getDeals(debouncedFilters, eurHufRate)])
      .then(([statsResult, dealsResult]) => {
        if (cancelled) return;
        setStats(statsResult);
        setDeals(dealsResult);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        const message = err instanceof ApiError ? err.message : "Something went wrong loading the dashboard.";
        setError(message);
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });

    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [debouncedFilters, eurHufRate, refreshToken]);

  return { stats, deals, setDeals, filters, setFilters, isLoading, error, refresh };
}
