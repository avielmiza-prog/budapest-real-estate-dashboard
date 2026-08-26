import { ExternalLink, FileText } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { getSpecSheetUrl } from "@/lib/api";
import { getSourceListingUrl, isMockListingUrl } from "@/lib/deal-links";
import { formatCurrency, formatRooms, formatSqm } from "@/lib/format";
import type { Currency, Deal } from "@/lib/types";

import { DealScoreBadge } from "./deal-score-badge";
import { FavoriteToggle, PipelineStatusSelect } from "./deal-actions";
import { RoiBadge } from "./roi-badge";

interface ListingsTableProps {
  deals: Deal[];
  onSelectDeal: (deal: Deal) => void;
  onDealUpdated: (deal: Deal) => void;
  currency: Currency;
  eurHufRate: number;
}

export function ListingsTable({ deals, onSelectDeal, onDealUpdated, currency, eurHufRate }: ListingsTableProps) {
  return (
    <div className="rounded-lg border bg-card">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead></TableHead>
            <TableHead>Title</TableHead>
            <TableHead>District</TableHead>
            <TableHead>Size</TableHead>
            <TableHead>Rooms</TableHead>
            <TableHead>Price</TableHead>
            <TableHead>Price/sqm</TableHead>
            <TableHead>Net profit</TableHead>
            <TableHead>Best ROI</TableHead>
            <TableHead>Deal Score</TableHead>
            <TableHead>Status</TableHead>
            <TableHead className="text-right">Details</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {deals.map((deal) => {
            const sourceUrl = getSourceListingUrl(deal);
            const isMock = isMockListingUrl(deal.source_url ?? deal.url);
            return (
            <TableRow key={deal.id}>
              <TableCell>
                <FavoriteToggle deal={deal} onUpdated={onDealUpdated} />
              </TableCell>
              <TableCell className="max-w-64 truncate font-medium">{deal.title}</TableCell>
              <TableCell>{deal.district}</TableCell>
              <TableCell>{formatSqm(deal.size_sqm)}</TableCell>
              <TableCell>{formatRooms(deal.rooms)}</TableCell>
              <TableCell>{formatCurrency(deal.price_huf, currency, eurHufRate)}</TableCell>
              <TableCell>{formatCurrency(deal.price_per_sqm, currency, eurHufRate)}</TableCell>
              <TableCell
                className={
                  deal.best_tier?.net_profit_huf != null
                    ? deal.best_tier.net_profit_huf >= 0
                      ? "text-emerald-600"
                      : "text-red-600"
                    : undefined
                }
              >
                {formatCurrency(deal.best_tier?.net_profit_huf, currency, eurHufRate)}
              </TableCell>
              <TableCell>
                <RoiBadge roiPercent={deal.best_tier?.roi_percent} />
              </TableCell>
              <TableCell>
                <DealScoreBadge score={deal.deal_score} band={deal.deal_score_band} />
              </TableCell>
              <TableCell>
                <PipelineStatusSelect deal={deal} onUpdated={onDealUpdated} />
              </TableCell>
              <TableCell className="text-right">
                <div className="flex justify-end gap-2">
                  <Button size="sm" variant="outline" onClick={() => onSelectDeal(deal)}>
                    View
                  </Button>
                  <Button size="sm" variant="ghost" title="Download Contractor Spec Sheet" asChild>
                    <a href={getSpecSheetUrl(deal.id, eurHufRate)} target="_blank" rel="noreferrer">
                      <FileText />
                    </a>
                  </Button>
                  {sourceUrl ? (
                    <Button size="sm" variant="ghost" title="View Original Listing" asChild>
                      <a href={sourceUrl} target="_blank" rel="noopener noreferrer">
                        <ExternalLink />
                      </a>
                    </Button>
                  ) : (
                    isMock && (
                      <Button
                        size="sm"
                        variant="ghost"
                        disabled
                        title="Demo listing — no live source to open"
                      >
                        <ExternalLink />
                      </Button>
                    )
                  )}
                </div>
              </TableCell>
            </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </div>
  );
}
