"use client";

import { useCallback, useEffect, useState } from "react";

import { getFxRate } from "@/lib/api";
import { DEFAULT_EUR_HUF_RATE } from "@/lib/constants";

interface UseFxRateResult {
  rate: number;
  setRate: (rate: number) => void;
  isLive: boolean;
  source: string | null;
  refresh: () => void;
}

/**
 * Fetches the live EUR->HUF rate once on mount and pre-fills the editable
 * rate the rest of the app uses. The user can override `rate` freely
 * afterwards (setRate) — this hook never overwrites a manual edit on its
 * own, only on mount/explicit refresh().
 */
export function useFxRate(): UseFxRateResult {
  const [rate, setRate] = useState<number>(DEFAULT_EUR_HUF_RATE);
  const [isLive, setIsLive] = useState(false);
  const [source, setSource] = useState<string | null>(null);
  const [refreshToken, setRefreshToken] = useState(0);

  useEffect(() => {
    let cancelled = false;
    getFxRate(refreshToken > 0)
      .then((fx) => {
        if (cancelled) return;
        setRate(fx.rate);
        setIsLive(fx.is_live);
        setSource(fx.source);
      })
      .catch(() => {
        // Live fetch failed — the editable input keeps working with the default/last-known rate.
      });
    return () => {
      cancelled = true;
    };
  }, [refreshToken]);

  const refresh = useCallback(() => setRefreshToken((t) => t + 1), []);

  return { rate, setRate, isLive, source, refresh };
}
