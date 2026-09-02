"use client";

import { Check, Star } from "lucide-react";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { updateProperty } from "@/lib/api";
import { cn } from "@/lib/utils";
import { PIPELINE_STATUSES, PIPELINE_STATUS_LABELS, type Deal, type PipelineStatus } from "@/lib/types";

interface FavoriteToggleProps {
  deal: Deal;
  onUpdated: (updated: Deal) => void;
  className?: string;
}

/** Star toggle for a deal's `is_favorite` flag — optimistic update, reverts on failure. */
export function FavoriteToggle({ deal, onUpdated, className }: FavoriteToggleProps) {
  const [isSaving, setIsSaving] = useState(false);

  const toggle = async (e: React.MouseEvent) => {
    e.stopPropagation();
    if (isSaving) return;
    const next = !deal.is_favorite;
    setIsSaving(true);
    onUpdated({ ...deal, is_favorite: next }); // optimistic
    try {
      const confirmed = await updateProperty(deal.id, { is_favorite: next });
      onUpdated({ ...deal, is_favorite: confirmed.is_favorite });
    } catch {
      onUpdated(deal); // revert
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <Button
      variant="ghost"
      size="icon"
      onClick={toggle}
      disabled={isSaving}
      title={deal.is_favorite ? "Remove from saved deals" : "Save this deal"}
      className={className}
    >
      <Star className={cn("h-4 w-4", deal.is_favorite && "fill-amber-400 text-amber-400")} />
    </Button>
  );
}

interface PipelineStatusSelectProps {
  deal: Deal;
  onUpdated: (updated: Deal) => void;
  className?: string;
}

/** Pipeline status dropdown ("New" -> "Archived") — persists via PATCH on change. */
export function PipelineStatusSelect({ deal, onUpdated, className }: PipelineStatusSelectProps) {
  const [isSaving, setIsSaving] = useState(false);

  const handleChange = async (value: string) => {
    const status = value as PipelineStatus;
    if (isSaving || status === deal.pipeline_status) return;
    setIsSaving(true);
    const previous = deal.pipeline_status;
    onUpdated({ ...deal, pipeline_status: status }); // optimistic
    try {
      const confirmed = await updateProperty(deal.id, { pipeline_status: status });
      onUpdated({ ...deal, pipeline_status: confirmed.pipeline_status });
    } catch {
      onUpdated({ ...deal, pipeline_status: previous });
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <Select value={deal.pipeline_status} onValueChange={handleChange} disabled={isSaving}>
      <SelectTrigger className={cn("h-7 text-xs", className)} onClick={(e) => e.stopPropagation()}>
        <SelectValue />
      </SelectTrigger>
      <SelectContent onClick={(e) => e.stopPropagation()}>
        {PIPELINE_STATUSES.map((status) => (
          <SelectItem key={status} value={status}>
            {PIPELINE_STATUS_LABELS[status]}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}

interface NotesEditorProps {
  deal: Deal;
  onUpdated: (updated: Deal) => void;
}

// Debounce (ms) between the last keystroke and the PATCH — avoids firing a
// request on every character while the investor is still typing a note.
const NOTES_SAVE_DEBOUNCE_MS = 800;

/** Free-text notes field for a shortlisted deal — backend-persisted (Property.notes) via PATCH, debounced on change. */
export function NotesEditor({ deal, onUpdated }: NotesEditorProps) {
  const [value, setValue] = useState(deal.notes ?? "");
  const [justSaved, setJustSaved] = useState(false);

  // A different deal was opened in the same modal instance — reset to its own notes.
  useEffect(() => {
    setValue(deal.notes ?? "");
  }, [deal.id]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (value === (deal.notes ?? "")) return;
    const timeout = setTimeout(async () => {
      try {
        const confirmed = await updateProperty(deal.id, { notes: value });
        onUpdated({ ...deal, notes: confirmed.notes });
        setJustSaved(true);
        setTimeout(() => setJustSaved(false), 1500);
      } catch {
        // Leave the field as typed — the investor can retry by editing again (e.g. offline).
      }
    }, NOTES_SAVE_DEBOUNCE_MS);
    return () => clearTimeout(timeout);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value]);

  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between">
        <Label htmlFor={`notes-${deal.id}`}>Notes (broker status, observations, …)</Label>
        {justSaved && (
          <span className="flex items-center gap-1 text-xs text-emerald-600">
            <Check className="h-3 w-3" />
            Saved
          </span>
        )}
      </div>
      <Textarea
        id={`notes-${deal.id}`}
        value={value}
        onChange={(e) => setValue(e.target.value)}
        placeholder="e.g. Called broker 3/2 — flexible on price, wants offer by Friday."
        rows={3}
      />
    </div>
  );
}
