"use client";

import { useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  Clock,
  LayoutGrid,
  LayoutList,
  Loader2,
  MapPinned,
  RefreshCw,
  SlidersHorizontal,
  TableIcon,
  XCircle,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { updateDealInList, useDashboardData } from "@/hooks/use-dashboard-data";
import { useFxRate } from "@/hooks/use-fx-rate";
import { useScraperSync } from "@/hooks/use-scraper-sync";
import { useFlipText } from "@/lib/flip-text";
import { cn } from "@/lib/utils";
import type { Currency, Deal, DealFilters, ViewMode } from "@/lib/types";

import { DealDetailModal } from "./deal-detail-modal";
import { FiltersBar } from "./filters-bar";
import { KpiCards } from "./kpi-cards";
import { ListingsCards } from "./listings-cards";
import { ListingsTable } from "./listings-table";
import { ScanMarketButton } from "./scan-market-button";
import { SimpleDealList } from "./simple-deal-list";
import { SplitView } from "./split-view";
import { TopBar } from "./top-bar";

export function Dashboard() {
  const fx = useFxRate();
  const { stats, deals, total, setDeals, filters, setFilters, isLoading, isLoadingMore, isSlow, error, refresh, loadMore } =
    useDashboardData(fx.rate);
  const scraperSync = useScraperSync(refresh);
  const t = useFlipText();
  const [view, setView] = useState<ViewMode>("simple");
  const [showFilters, setShowFilters] = useState(false);
  const [currency, setCurrency] = useState<Currency>("HUF");
  const [selectedDeal, setSelectedDeal] = useState<Deal | null>(null);
  const [selectedDealId, setSelectedDealId] = useState<number | null>(null);

  const handleDealUpdated = (updated: Deal) => {
    setDeals((prev) => updateDealInList(prev, updated));
    setSelectedDeal((prev) => (prev && prev.id === updated.id ? { ...prev, ...updated } : prev));
  };

  return (
    <div className="mx-auto flex max-w-7xl flex-col gap-6 p-4 sm:p-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Budapest Apartments</h1>
          <p className="text-sm text-muted-foreground">Deal analysis &amp; underwriting platform</p>
          <ScanFreshness lastScanAt={stats?.last_scan_at ?? null} />
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

      {view !== "simple" && <KpiCards stats={stats} isLoading={isLoading} />}

      <div className="flex flex-wrap items-center justify-between gap-3">
        <VerdictTabs filters={filters} onChange={setFilters} counts={stats?.verdict_counts} />
        <div className="flex items-center gap-2">
          <Button
            variant={showFilters ? "default" : "outline"}
            size="sm"
            onClick={() => setShowFilters((v) => !v)}
          >
            <SlidersHorizontal className="h-4 w-4" />
            {t("moreFilters")}
          </Button>
          <ViewSwitch view={view} onChange={setView} simpleLabel={t("simpleView")} />
        </div>
      </div>

      {(showFilters || view !== "simple") && (
        <FiltersBar
          filters={filters}
          onFiltersChange={setFilters}
          view={view}
          onViewChange={setView}
          currency={currency}
          eurHufRate={fx.rate}
        />
      )}

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
        <p className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" />
          {isSlow ? t("wakingUp") : t("loading")}
        </p>
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
          {filters.verdict === "buy" ? t("noDealsBuy") : t("noDeals")}
        </p>
      )}

      {!isLoading && !error && deals.length > 0 && (
        <>
          {view === "simple" && (
            <SimpleDealList
              deals={deals}
              onSelectDeal={setSelectedDeal}
              onDealUpdated={handleDealUpdated}
              currency={currency}
              eurHufRate={fx.rate}
            />
          )}
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
          <div className="flex flex-col items-center gap-2 py-2">
            <p className="text-xs text-muted-foreground">{t("countOf", { shown: deals.length, total })}</p>
            {deals.length < total && (
              <Button variant="outline" onClick={loadMore} disabled={isLoadingMore}>
                {isLoadingMore && <Loader2 className="h-4 w-4 animate-spin" />}
                {t("showMore", { n: total - deals.length })}
              </Button>
            )}
          </div>
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

function ScanFreshness({ lastScanAt }: { lastScanAt: string | null }) {
  const t = useFlipText();
  if (!lastScanAt) return null;
  const hours = (Date.now() - new Date(lastScanAt).getTime()) / 3_600_000;
  const label =
    hours < 1 ? t("justNow") : hours < 48 ? t("hoursAgo", { n: Math.round(hours) }) : t("daysAgo", { n: Math.round(hours / 24) });
  return (
    <p className={cn("mt-1 flex items-center gap-1 text-xs", hours > 48 ? "text-destructive" : "text-muted-foreground")}>
      <Clock className="h-3 w-3" />
      {t("lastScan")}: {label}
      {hours > 48 && <span>· {t("staleData")}</span>}
    </p>
  );
}

function VerdictTabs({
  filters,
  onChange,
  counts,
}: {
  filters: DealFilters;
  onChange: (f: DealFilters) => void;
  counts?: { buy: number; consider: number; skip: number };
}) {
  const t = useFlipText();
  const tabs: { key: DealFilters["verdict"]; label: string; count?: number; tone: string }[] = [
    { key: "buy", label: t("tabBuy"), count: counts?.buy, tone: "data-[active=true]:bg-emerald-600" },
    {
      key: "consider",
      label: t("tabConsider"),
      count: counts ? counts.buy + counts.consider : undefined,
      tone: "data-[active=true]:bg-amber-500",
    },
    {
      key: "all",
      label: t("tabAll"),
      count: counts ? counts.buy + counts.consider + counts.skip : undefined,
      tone: "data-[active=true]:bg-zinc-800",
    },
  ];
  return (
    <div className="flex flex-wrap gap-2" role="tablist">
      {tabs.map((tab) => (
        <button
          key={tab.key}
          type="button"
          role="tab"
          aria-selected={filters.verdict === tab.key}
          data-active={filters.verdict === tab.key}
          onClick={() => onChange({ ...filters, verdict: tab.key })}
          className={cn(
            "rounded-full border px-4 py-2 text-sm font-medium transition data-[active=true]:border-transparent data-[active=true]:text-white",
            tab.tone
          )}
        >
          {tab.label}
          {tab.count !== undefined && <span className="ml-1.5 opacity-80">{tab.count}</span>}
        </button>
      ))}
    </div>
  );
}

function ViewSwitch({
  view,
  onChange,
  simpleLabel,
}: {
  view: ViewMode;
  onChange: (v: ViewMode) => void;
  simpleLabel: string;
}) {
  const options: { key: ViewMode; label: string; icon: React.ReactNode }[] = [
    { key: "simple", label: simpleLabel, icon: <LayoutList className="h-4 w-4" /> },
    { key: "table", label: "Table", icon: <TableIcon className="h-4 w-4" /> },
    { key: "card", label: "Cards", icon: <LayoutGrid className="h-4 w-4" /> },
    { key: "split", label: "Map", icon: <MapPinned className="h-4 w-4" /> },
  ];
  return (
    <div className="inline-flex rounded-lg border p-0.5">
      {options.map((o) => (
        <button
          key={o.key}
          type="button"
          onClick={() => onChange(o.key)}
          title={o.label}
          className={cn(
            "flex items-center gap-1 rounded-md px-2.5 py-1.5 text-sm",
            view === o.key ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:text-foreground"
          )}
        >
          {o.icon}
          <span className="hidden sm:inline">{o.label}</span>
        </button>
      ))}
    </div>
  );
}
