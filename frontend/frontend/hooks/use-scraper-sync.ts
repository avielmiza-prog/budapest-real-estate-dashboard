"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { ApiError, getScraperStatus, triggerScraperScan } from "@/lib/api";
import type { ScraperStatus } from "@/lib/types";

const POLL_INTERVAL_MS = 2000;

export interface ScraperNotification {
  type: "success" | "error";
  message: string;
}

interface UseScraperSyncResult {
  isRunning: boolean;
  notification: ScraperNotification | null;
  dismissNotification: () => void;
  scan: () => void;
}

/**
 * Drives the "Scan Market" button: triggers the backend ingestion agent
 * (POST /api/scraper/trigger), polls GET /api/scraper/status until it
 * finishes, then surfaces a success/error notification and calls
 * onFinished() (the dashboard's refresh()) so new listings show up without
 * a manual reload.
 */
export function useScraperSync(onFinished: () => void): UseScraperSyncResult {
  const [isRunning, setIsRunning] = useState(false);
  const [notification, setNotification] = useState<ScraperNotification | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const onFinishedRef = useRef(onFinished);
  onFinishedRef.current = onFinished;

  const stopPolling = useCallback(() => {
    if (pollRef.current !== null) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }, []);

  const handleFinished = useCallback(
    (status: ScraperStatus) => {
      stopPolling();
      setIsRunning(false);
      if (status.error) {
        setNotification({ type: "error", message: `Scan failed: ${status.error}` });
      } else if (status.last_result) {
        const { stored, total } = status.last_result;
        setNotification({
          type: "success",
          message:
            total > 0
              ? `Scan complete — ${stored} of ${total} listing${total === 1 ? "" : "s"} synced.`
              : "Scan complete — no listings found this time.",
        });
      } else {
        setNotification({ type: "success", message: "Scan complete." });
      }
      onFinishedRef.current();
    },
    [stopPolling]
  );

  const startPolling = useCallback(() => {
    stopPolling();
    pollRef.current = setInterval(() => {
      getScraperStatus()
        .then((status) => {
          if (!status.is_running) handleFinished(status);
        })
        .catch(() => {
          // Transient poll failure — try again next tick rather than giving up mid-scan.
        });
    }, POLL_INTERVAL_MS);
  }, [handleFinished, stopPolling]);

  const scan = useCallback(() => {
    if (isRunning) return;
    setNotification(null);
    setIsRunning(true);
    triggerScraperScan()
      .then((status) => {
        if (!status.is_running) {
          // Finished (or failed) before the first poll tick had a chance to run.
          handleFinished(status);
        } else {
          startPolling();
        }
      })
      .catch((err: unknown) => {
        setIsRunning(false);
        const message = err instanceof ApiError ? err.message : "Could not start the scan.";
        setNotification({ type: "error", message });
      });
  }, [isRunning, handleFinished, startPolling]);

  // If a scan was already in flight (e.g. started from another tab) when this
  // component mounted, pick it up rather than showing a stale idle button.
  useEffect(() => {
    let cancelled = false;
    getScraperStatus()
      .then((status) => {
        if (cancelled || !status.is_running) return;
        setIsRunning(true);
        startPolling();
      })
      .catch(() => {
        // No status yet / API unreachable — button just starts idle.
      });
    return () => {
      cancelled = true;
      stopPolling();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return { isRunning, notification, dismissNotification: () => setNotification(null), scan };
}
