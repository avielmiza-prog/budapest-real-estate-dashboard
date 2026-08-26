"use client";

import { RefreshCw } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { formatDate } from "@/lib/format";
import type { Currency } from "@/lib/types";

interface TopBarProps {
  currency: Currency;
  onCurrencyChange: (currency: Currency) => void;
  eurHufRate: number;
  onEurHufRateChange: (rate: number) => void;
  isLive: boolean;
  fxUpdatedAt?: string | null;
  onRefreshFxRate: () => void;
}

export function TopBar({
  currency,
  onCurrencyChange,
  eurHufRate,
  onEurHufRateChange,
  isLive,
  fxUpdatedAt,
  onRefreshFxRate,
}: TopBarProps) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border bg-card px-4 py-2.5 text-sm">
      <Tabs value={currency} onValueChange={(v) => onCurrencyChange(v as Currency)}>
        <TabsList className="h-8">
          <TabsTrigger value="HUF" className="h-6 px-3 text-xs">
            Ft HUF
          </TabsTrigger>
          <TabsTrigger value="EUR" className="h-6 px-3 text-xs">
            € EUR
          </TabsTrigger>
        </TabsList>
      </Tabs>

      <div className="flex items-center gap-2">
        <span className="text-xs text-muted-foreground">1 EUR =</span>
        <Input
          type="number"
          inputMode="decimal"
          className="h-8 w-24"
          value={eurHufRate}
          onChange={(e) => {
            const parsed = Number(e.target.value);
            if (!Number.isNaN(parsed) && parsed > 0) onEurHufRateChange(parsed);
          }}
        />
        <span className="text-xs text-muted-foreground">HUF</span>
        <Button variant="ghost" size="icon" className="h-8 w-8" onClick={onRefreshFxRate} title="Refresh live rate">
          <RefreshCw className="h-3.5 w-3.5" />
        </Button>
        <span className="hidden text-[11px] text-muted-foreground sm:inline">
          {isLive ? `Live · updated ${formatDate(fxUpdatedAt)}` : "Manual override"}
        </span>
      </div>
    </div>
  );
}
