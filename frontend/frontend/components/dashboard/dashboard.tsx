"use client";

import { useState } from "react";
import { AlertTriangle, CheckCircle2, RefreshCw, XCircle } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { updateDealInList, useDashboardData } from "@/hooks/use-dashboard-data";
import { useFxRate } from "@/hooks/use-fx-rate";
import { useScraperSync } from "@/hooks/use-scraper-sync";
import { cn } from "@/lib/utils";
import type { Currency, Deal, ViewMode } from "@/lib/types";

import { DealDetailModal } from "./deal-detail-modal";
import { FiltersBar } from "./filters-bar";
import { KpiCards } from "./kpi-cards";
import { ListingsCards } from "./listings-cards";
import { ListingsTable } from "./listings-table";
import { ScanMarketButton } from "./scan-market-button";
import { SplitView } from "./split-view";
import { TopBar } from "./top-bar";

export function Dashboard() {
  const fx = useFxRate();
  const { stats, deals, setDeals, filters, setFilters, isLoading, error, refresh } = useDashboardData(fx.rate);
  const scraperSync = useScraperSync(refresh);
  const [view, setView] = useState<ViewMode>("table");
  const [currency, setCurrency] = useState<Currency>("HUF");
  const [selectedDeal, setSelectedDeal] = useState<Deal | null>(null);
  const [selectedDealId, setSelectedDealId] = useState<number | null>(null);

  const handleDealUpdated = (updated: Deal) => {
    setDeals((prev) => updateDealInList(prev, updated));
    setSelectedDeal((prev) => (prev && prev.id === updated.id ? { ...prev, ...updated } : prev));
  };

  return (
    <div className="mx-auto flex max-w-7xl flex-col gap-6 p-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Budapest Apartments</h1>
          <p className="text-sm text-muted-foreground">Deal analysis &amp; underwriting platform</p>
        </div>
        <div className="flex items-center gap-2">
          <ScanMarketButton isRunning={scraperSync.isRunning} onScan={scraperSync.scan} />
          <Button variant="outline" size="sm" onClick={refresh}>
            <RefreshCw className="h-4 w-4" />
            Refresh
          </Button>
        </div>
      </div>

      {scraperSync.notification && (
        <div
          className={cn(
            "flex items-start justify-between gap-3 rounded-lg border p-4 text-sm",
            scraperSync.notification.type === "success"
              ? "border-emerald-500/50 bg-emerald-500/10"
              : "border-destructive/50 bg-destructive/10"
          )}
        >
          <div className="flex items-start gap-3">
            {scraperSync.notification.type === "success" ? (
              <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-emerald-600" />
            ) : (
              <XCircle className="mt-0.5 h-4 w-4 shrink-0 text-destructive" />
            )}
            <p className={scraperSync.notification.type === "success" ? "text-emerald-700 dark:text-emerald-400" : "text-destructive"}>
              {scraperSync.notification.message}
            </p>
          </div>
          <button
            type="button"
            onClick={scraperSync.dismissNotification}
            className="text-xs text-muted-foreground hover:text-foreground"
          >
            Dismiss
          </button>
        </div>
      )}

      <TopBar
        currency={currency}
        onCurrencyChange={setCurrency}
        eurHufRate={fx.rate}
        onEurHufRateChange={fx.setRate}
        isLive={fx.isLive}
        fxUpdatedAt={fx.source}
        onRefreshFxRate={fx.refresh}
      />

      <KpiCards stats={stats} isLoading={isLoading} />

      <FiltersBar
        filters={filters}
        onFiltersChange={setFilters}
        view={view}
        onViewChange={setView}
        currency={currency}
        eurHufRate={fx.rate}
      />

      {error && (
        <div className="flex items-start gap-3 rounded-lg border border-destructive/50 bg-destructive/10 p-4 text-sm">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-destructive" />
          <div>
            <p className="font-medium text-destructive">Couldn&apos;t load the dashboard</p>
            <p className="text-muted-foreground">{error}</p>
          </div>
        </div>
      )}

      {isLoading && !error && (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {[0, 1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-64 w-full" />
          ))}
        </div>
      )}

      {!isLoading && !error && deals.length === 0 && (
        <p className="rounded-lg border border-dashed p-8 text-center text-sm text-muted-foreground">
          {filters.minRoi !== null && filters.minRoi > 0
            ? `No deals found meeting the minimum ${filters.minRoi}% Net ROI requirement in this selection.`
            : "No listings match these filters yet."}
        </p>
      )}

      {!isLoading && !error && deals.length > 0 && (
        <>
          {view === "table" && (
            <ListingsTable
              deals={deals}
              onSelectDeal={setSelectedDeal}
              onDealUpdated={handleDealUpdated}
              currency={currency}
              eurHufRate={fx.rate}
            />
          )}
          {view === "card" && (
            <ListingsCards
              deals={deals}
              onSelectDeal={setSelectedDeal}
              onDealUpdated={handleDealUpdated}
              currency={currency}
              eurHufRate={fx.rate}
            />
          )}
          {view === "split" && (
            <SplitView
              deals={deals}
              selectedDealId={selectedDealId}
              onSelectDeal={setSelectedDealId}
              onSelectDealForModal={setSelectedDeal}
              onDealUpdated={handleDealUpdated}
              currency={currency}
              eurHufRate={fx.rate}
            />
          )}
        </>
      )}

      <DealDetailModal
        deal={selectedDeal}
        onOpenChange={(open) => !open && setSelectedDeal(null)}
        onDealUpdated={handleDealUpdated}
        currency={currency}
        eurHufRate={fx.rate}
      />
    </div>
  );
}
