import type { Currency } from "@/lib/types";

export function formatHuf(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  return new Intl.NumberFormat("hu-HU", {
    style: "currency",
    currency: "HUF",
    maximumFractionDigits: 0,
  }).format(value);
}

export function formatEur(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  return new Intl.NumberFormat("en-IE", {
    style: "currency",
    currency: "EUR",
    maximumFractionDigits: 0,
  }).format(value);
}

/** Formats a HUF amount in whichever currency the user has toggled to. */
export function formatCurrency(hufValue: number | null | undefined, currency: Currency, eurHufRate: number): string {
  if (hufValue === null || hufValue === undefined) return "—";
  return currency === "EUR" ? formatEur(hufValue / eurHufRate) : formatHuf(hufValue);
}

export function formatSqm(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  return `${new Intl.NumberFormat("en-US", { maximumFractionDigits: 1 }).format(value)} m²`;
}

export function formatRooms(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  if (Number.isInteger(value)) return String(value);
  const whole = Math.floor(value);
  const half = value - whole >= 0.5 ? 1 : 0;
  return half ? `${whole}+${half}` : String(value);
}

export function formatPercent(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined) return "—";
  return `${value.toFixed(digits)}%`;
}

export function formatDate(value: string | null | undefined): string {
  if (!value) return "—";
  try {
    return new Intl.DateTimeFormat("en-GB", { dateStyle: "medium" }).format(new Date(value));
  } catch {
    return value;
  }
}
