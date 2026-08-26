"use client";

import { useEffect, useState } from "react";

import { getDistrictBenchmarks } from "@/lib/api";
import type { DistrictBenchmark } from "@/lib/types";

/** Fetches every district benchmark once on mount — powers the map's district-polygon overlay. */
export function useDistrictBenchmarks(): DistrictBenchmark[] {
  const [benchmarks, setBenchmarks] = useState<DistrictBenchmark[]>([]);

  useEffect(() => {
    let cancelled = false;
    getDistrictBenchmarks()
      .then((data) => {
        if (!cancelled) setBenchmarks(data);
      })
      .catch(() => {
        // No benchmarks yet (or API unreachable) — the overlay just shows "no data" per district.
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return benchmarks;
}
