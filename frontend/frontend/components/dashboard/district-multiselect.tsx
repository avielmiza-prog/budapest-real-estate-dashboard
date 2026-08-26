"use client";

import { ChevronDown } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { BUDAPEST_DISTRICTS } from "@/lib/constants";
import { cn } from "@/lib/utils";

interface DistrictMultiSelectProps {
  selected: string[];
  onChange: (districts: string[]) => void;
}

export function DistrictMultiSelect({ selected, onChange }: DistrictMultiSelectProps) {
  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const handleClickOutside = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [open]);

  const toggle = (district: string) => {
    if (selected.includes(district)) {
      onChange(selected.filter((d) => d !== district));
    } else {
      onChange([...selected, district]);
    }
  };

  const label =
    selected.length === 0
      ? "All districts"
      : selected.length === 1
        ? `District ${selected[0]}`
        : `${selected.length} districts`;

  return (
    <div className="relative" ref={containerRef}>
      <Button
        type="button"
        variant="outline"
        className="w-full justify-between font-normal"
        onClick={() => setOpen((o) => !o)}
      >
        <span className="truncate">{label}</span>
        <ChevronDown className="h-4 w-4 shrink-0 opacity-50" />
      </Button>

      {open && (
        <div className="absolute z-50 mt-1 w-64 rounded-md border bg-popover p-3 text-popover-foreground shadow-md">
          <div className="mb-2 flex items-center justify-between">
            <span className="text-xs font-medium text-muted-foreground">Districts I–XXIII</span>
            <div className="flex gap-2">
              <button
                type="button"
                className="text-xs text-primary underline-offset-2 hover:underline"
                onClick={() => onChange([...BUDAPEST_DISTRICTS])}
              >
                All
              </button>
              <button
                type="button"
                className="text-xs text-primary underline-offset-2 hover:underline"
                onClick={() => onChange([])}
              >
                Clear
              </button>
            </div>
          </div>
          <div className="grid grid-cols-5 gap-1.5">
            {BUDAPEST_DISTRICTS.map((district) => {
              const active = selected.includes(district);
              return (
                <button
                  key={district}
                  type="button"
                  onClick={() => toggle(district)}
                  className={cn(
                    "rounded-md border px-1.5 py-1 text-xs font-medium transition-colors",
                    active
                      ? "border-primary bg-primary text-primary-foreground"
                      : "border-input bg-background hover:bg-accent"
                  )}
                >
                  {district}
                </button>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
