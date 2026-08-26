import { Building2, Percent, TrendingDown } from "lucide-react";
import type { ReactNode } from "react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { formatEur, formatHuf, formatPercent } from "@/lib/format";
import type { DashboardStats } from "@/lib/types";

interface KpiCardsProps {
  stats: DashboardStats | null;
  isLoading: boolean;
}

function KpiCard({
  icon,
  label,
  children,
}: {
  icon: ReactNode;
  label: string;
  children: ReactNode;
}) {
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-sm font-medium text-muted-foreground">{label}</CardTitle>
        <div className="text-muted-foreground">{icon}</div>
      </CardHeader>
      <CardContent>{children}</CardContent>
    </Card>
  );
}

export function KpiCards({ stats, isLoading }: KpiCardsProps) {
  if (isLoading || !stats) {
    return (
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {[0, 1, 2].map((i) => (
          <Card key={i}>
            <CardHeader className="pb-2">
              <Skeleton className="h-4 w-32" />
            </CardHeader>
            <CardContent>
              <Skeleton className="h-8 w-24" />
            </CardContent>
          </Card>
        ))}
      </div>
    );
  }

  const topDeal = stats.top_undervalued[0];

  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
      <KpiCard icon={<Building2 className="h-4 w-4" />} label="Total listings tracked">
        <div className="text-2xl font-bold tabular-nums">{stats.total_listings}</div>
        {!stats.is_today_only && (
          <p className="mt-1 text-xs text-muted-foreground">{stats.today_new_listings} new today</p>
        )}
        {stats.is_today_only && stats.today_new_listings > 0 && (
          <p className="mt-1 text-xs text-muted-foreground">{stats.today_new_listings} added today</p>
        )}
      </KpiCard>

      <KpiCard icon={<Percent className="h-4 w-4" />} label="Average Budapest €/sqm">
        <div className="text-2xl font-bold tabular-nums">{formatEur(stats.avg_price_sqm_eur)}</div>
        <p className="mt-1 text-xs text-muted-foreground">{formatHuf(stats.avg_price_sqm_huf)}/sqm</p>
      </KpiCard>

      <KpiCard icon={<TrendingDown className="h-4 w-4" />} label="Top undervalued deals">
        <div className="text-2xl font-bold tabular-nums">{stats.top_undervalued.length}</div>
        {topDeal ? (
          <p className="mt-1 truncate text-xs text-muted-foreground">
            Best: District {topDeal.district}, {formatPercent(topDeal.discount_percent)} below benchmark
          </p>
        ) : (
          <p className="mt-1 text-xs text-muted-foreground">No comparable listings yet</p>
        )}
        {!stats.is_today_only && (
          <Badge variant="outline" className="mt-2">
            No new listings today — showing best overall
          </Badge>
        )}
      </KpiCard>
    </div>
  );
}
