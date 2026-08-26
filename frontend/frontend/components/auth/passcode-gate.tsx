"use client";

import { Lock } from "lucide-react";
import { type ReactNode, useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { clearStoredPasscode, getStoredPasscode, setStoredPasscode } from "@/lib/access";
import { ApiError } from "@/lib/api";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

type GateState = "checking" | "open" | "locked";

async function verifyPasscode(passcode: string): Promise<boolean> {
  const response = await fetch(new URL("/api/auth/verify", API_BASE_URL).toString(), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ passcode }),
  });
  return response.ok;
}

/**
 * Lightweight investor-sharing gate (see backend/app/access_control.py) — a
 * shared-secret curtain, not real auth. Skips straight to "open" when the
 * backend doesn't have ACCESS_PASSCODE configured, so local dev stays
 * frictionless; only prompts when a deploy has actually turned it on.
 */
export function PasscodeGate({ children }: { children: ReactNode }) {
  const [state, setState] = useState<GateState>("checking");
  const [input, setInput] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  useEffect(() => {
    let cancelled = false;

    async function check() {
      let required = false;
      try {
        const response = await fetch(new URL("/api/auth/status", API_BASE_URL).toString(), { cache: "no-store" });
        const data = (await response.json()) as { passcode_required: boolean };
        required = data.passcode_required;
      } catch {
        // API unreachable — let the dashboard's own error banner explain that; don't block on the gate too.
        if (!cancelled) setState("open");
        return;
      }
      if (!required) {
        if (!cancelled) setState("open");
        return;
      }

      const stored = getStoredPasscode();
      if (stored && (await verifyPasscode(stored).catch(() => false))) {
        if (!cancelled) setState("open");
      } else {
        clearStoredPasscode();
        if (!cancelled) setState("locked");
      }
    }

    check();
    return () => {
      cancelled = true;
    };
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (isSubmitting || !input.trim()) return;
    setIsSubmitting(true);
    setError(null);
    try {
      const ok = await verifyPasscode(input.trim());
      if (ok) {
        setStoredPasscode(input.trim());
        setState("open");
      } else {
        setError("Incorrect passcode.");
      }
    } catch (err: unknown) {
      setError(err instanceof ApiError ? err.message : "Could not reach the API to verify the passcode.");
    } finally {
      setIsSubmitting(false);
    }
  };

  if (state === "checking") {
    return <div className="flex min-h-screen items-center justify-center text-sm text-muted-foreground">Loading…</div>;
  }

  if (state === "locked") {
    return (
      <div className="flex min-h-screen items-center justify-center p-6">
        <form onSubmit={handleSubmit} className="w-full max-w-sm space-y-4 rounded-xl border bg-card p-6 shadow-sm">
          <div className="flex flex-col items-center gap-2 text-center">
            <div className="flex h-10 w-10 items-center justify-center rounded-full bg-muted">
              <Lock className="h-5 w-5" />
            </div>
            <h1 className="text-lg font-semibold">Investor access</h1>
            <p className="text-sm text-muted-foreground">Enter the passcode you were given to view this dashboard.</p>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="passcode">Passcode</Label>
            <Input
              id="passcode"
              type="password"
              autoFocus
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="••••••••"
            />
          </div>
          {error && <p className="text-sm text-destructive">{error}</p>}
          <Button type="submit" className="w-full" disabled={isSubmitting || !input.trim()}>
            {isSubmitting ? "Checking…" : "Enter"}
          </Button>
        </form>
      </div>
    );
  }

  return <>{children}</>;
}
