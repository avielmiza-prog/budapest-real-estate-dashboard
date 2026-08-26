"use client";

import * as React from "react";

import { cn } from "@/lib/utils";

const THUMB_CLASSES = cn(
  "pointer-events-none absolute inset-0 h-5 w-full cursor-pointer appearance-none bg-transparent",
  "[&::-webkit-slider-thumb]:pointer-events-auto [&::-webkit-slider-thumb]:h-4 [&::-webkit-slider-thumb]:w-4",
  "[&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:rounded-full",
  "[&::-webkit-slider-thumb]:border-2 [&::-webkit-slider-thumb]:border-primary [&::-webkit-slider-thumb]:bg-background",
  "[&::-webkit-slider-thumb]:shadow [&::-webkit-slider-thumb]:cursor-pointer",
  "[&::-moz-range-thumb]:pointer-events-auto [&::-moz-range-thumb]:h-4 [&::-moz-range-thumb]:w-4",
  "[&::-moz-range-thumb]:rounded-full [&::-moz-range-thumb]:border-2 [&::-moz-range-thumb]:border-primary",
  "[&::-moz-range-thumb]:bg-background [&::-moz-range-thumb]:shadow [&::-moz-range-thumb]:cursor-pointer",
  "[&::-moz-range-track]:bg-transparent"
);

interface RangeSliderProps {
  min: number;
  max: number;
  step?: number;
  value: [number, number];
  onValueChange: (value: [number, number]) => void;
  formatLabel?: (value: number) => string;
  className?: string;
}

/** Dual-thumb range slider built from two overlaid native range inputs (no extra dependency). */
export function RangeSlider({ min, max, step = 1, value, onValueChange, formatLabel, className }: RangeSliderProps) {
  const [lo, hi] = value;
  const pct = (v: number) => (max === min ? 0 : ((v - min) / (max - min)) * 100);

  return (
    <div className={cn("w-full", className)}>
      <div className="relative h-5 w-full">
        <div className="absolute top-1/2 h-1.5 w-full -translate-y-1/2 rounded-full bg-muted" />
        <div
          className="absolute top-1/2 h-1.5 -translate-y-1/2 rounded-full bg-primary"
          style={{ left: `${pct(lo)}%`, right: `${100 - pct(hi)}%` }}
        />
        <input
          type="range"
          min={min}
          max={max}
          step={step}
          value={lo}
          onChange={(e) => onValueChange([Math.min(Number(e.target.value), hi), hi])}
          className={THUMB_CLASSES}
          aria-label="Minimum value"
        />
        <input
          type="range"
          min={min}
          max={max}
          step={step}
          value={hi}
          onChange={(e) => onValueChange([lo, Math.max(Number(e.target.value), lo)])}
          className={THUMB_CLASSES}
          aria-label="Maximum value"
        />
      </div>
      {formatLabel && (
        <div className="mt-1 flex justify-between text-xs text-muted-foreground">
          <span>{formatLabel(lo)}</span>
          <span>{formatLabel(hi)}</span>
        </div>
      )}
    </div>
  );
}

interface SingleSliderProps {
  min: number;
  max: number;
  step?: number;
  value: number;
  onValueChange: (value: number) => void;
  formatLabel?: (value: number) => string;
  className?: string;
}

/** Single-thumb slider, e.g. for a minimum-ROI threshold. */
export function Slider({ min, max, step = 1, value, onValueChange, formatLabel, className }: SingleSliderProps) {
  const pct = max === min ? 0 : ((value - min) / (max - min)) * 100;

  return (
    <div className={cn("w-full", className)}>
      <div className="relative h-5 w-full">
        <div className="absolute top-1/2 h-1.5 w-full -translate-y-1/2 rounded-full bg-muted" />
        <div
          className="absolute top-1/2 h-1.5 -translate-y-1/2 rounded-full bg-primary"
          style={{ width: `${pct}%` }}
        />
        <input
          type="range"
          min={min}
          max={max}
          step={step}
          value={value}
          onChange={(e) => onValueChange(Number(e.target.value))}
          className={THUMB_CLASSES}
        />
      </div>
      {formatLabel && <div className="mt-1 text-xs text-muted-foreground">{formatLabel(value)}</div>}
    </div>
  );
}
