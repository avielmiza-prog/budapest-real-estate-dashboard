// Client-side half of the lightweight investor passcode gate (see
// backend/app/access_control.py). Once verified, the passcode is kept in
// localStorage (so a refresh doesn't re-prompt) and attached to every API
// call — as a header for fetch() calls, and as a `?passcode=` query param
// for the PDF export links, which the browser opens as plain navigations
// that can't carry a custom header.
const STORAGE_KEY = "budapest-apartments-access-passcode";
const HEADER_NAME = "X-Access-Passcode";

export function getStoredPasscode(): string | null {
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage.getItem(STORAGE_KEY);
  } catch {
    return null; // private browsing / storage blocked — treat as "not verified yet"
  }
}

export function setStoredPasscode(passcode: string): void {
  try {
    window.localStorage.setItem(STORAGE_KEY, passcode);
  } catch {
    // Storage blocked — the gate will just re-prompt next load, not fatal.
  }
}

export function clearStoredPasscode(): void {
  try {
    window.localStorage.removeItem(STORAGE_KEY);
  } catch {
    // no-op
  }
}

/** Spread into a fetch() `headers` object — empty object when no passcode is stored. */
export function passcodeHeaders(): Record<string, string> {
  const passcode = getStoredPasscode();
  return passcode ? { [HEADER_NAME]: passcode } : {};
}
