"use client";

import { Loader2, Radar } from "lucide-react";

import { Button } from "@/components/ui/button";

interface ScanMarketButtonProps {
  isRunning: boolean;
  onScan: () => void;
}

/** Prominent header CTA that triggers the backend's autonomous ingestion agent (POST /api/scraper/trigger). */
export function ScanMarketButton({ isRunning, onScan }: ScanMarketButtonProps) {
  return (
    <Button onClick={onScan} disabled={isRunning} className="gap-2">
      {isRunning ? <Loader2 className="h-4 w-4 animate-spin" /> : <Radar className="h-4 w-4" />}
      {isRunning ? "Scanning market…" : "Scan Market"}
    </Button>
  );
}
