"use client";

import { useEffect, useState } from "react";

/** Returns `value`, but delayed by `delayMs` after its last change — used to keep
 * slider-driven filters visually instant while coalescing the network calls they trigger. */
export function useDebouncedValue<T>(value: T, delayMs: number): T {
  const [debounced, setDebounced] = useState(value);

  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delayMs);
    return () => clearTimeout(timer);
  }, [value, delayMs]);

  return debounced;
}
