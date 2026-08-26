# Scraper (Step 4)

Modular scraper that crawls a Budapest real-estate portal, extracts title /
district / size / rooms / price (HUF+EUR) / description, stores each listing
in the database (upsert by URL), and automatically runs every stored
listing through `app/analyzer.py` for a renovation ROI readout.

Two collection paths, tried in order (see `scraper/pipeline.py` and
`scraper/agent/orchestrator.py`):

1. **Plain HTTP** (`scraper/http_client.py`) — no browser at all. Works for
   any portal whose listing data is present in the server-rendered HTML;
   verified true for jofogas.hu (its Next.js hydration JSON is already in
   the raw response). httpx first, retried once via `curl_cffi` (real
   Chrome TLS fingerprint) if that gets bot-blocked (403/429).
2. **Playwright**, only as a fallback when a portal doesn't support the
   HTTP path or it fails — launched lazily, at most once per multi-portal
   agent run, and never crashes the run if the launch itself fails (missing
   browser binary, etc.) — see `_LazyBrowser` in `scraper/agent/orchestrator.py`.

In practice this means a full agent run against jofogas.hu alone needs no
browser process at all, which is both much faster and removes Playwright's
Chromium binary as a hard requirement for a deploy to *work*, even though
it's still recommended for the other two portals' fallback path.

## Before you run this against a real site — read this

I checked `robots.txt` for a couple of major Hungarian portals while building this:

- **ingatlan.com** — its `robots.txt` explicitly disallows `/lista` and `/szukites`
  (the search-results paths) for *every* user-agent, and it references
  `/distil-captcha.html` — meaning it runs Distil/Imperva, a commercial
  anti-bot service, specifically to detect and block this kind of automated
  access. Scraping it with a stealth plugin would mean deliberately defeating
  a protection they've put up and explicitly said "don't crawl this" about.
  I didn't build the concrete scraper against it for that reason, and I'd
  suggest not pointing this at it either — if you specifically need
  ingatlan.com data, it's worth asking whether they offer a commercial/API
  data feed (some portals do, for aggregators).
- **ingatlanbazar.hu** — its `robots.txt` only disallows `/hitel-kereses`,
  `/fiokom`, `/admin`, `/magazin/kereses`, `/magazin/hirdetesek`, and
  `/magazin/publicapi/`. It does not disallow listing search or detail pages.
  This is the portal `scraper/portals/ingatlanbazar.py` targets.

`scraper/robots.py` checks robots.txt before every request by default and
raises `PermissionError` if it's disallowed — `--ignore-robots` turns that
off, but it's opt-in specifically so overriding a site's stated wishes is a
conscious choice, not a silent default.

## Setup

```bash
cd backend
pip install -r requirements.txt
playwright install chromium   # optional locally — only needed for the Playwright fallback path
```

The Chromium install step above is skippable if you only care about
jofogas.hu (its HTTP path never touches Playwright) — but do it anyway
unless you've confirmed you don't need the other two portals' fallback,
since a missing browser just means those portals silently get skipped
rather than erroring loudly. On Render, this is the build command instead —
see `../../render.yaml` and `../README.md`'s Deploying section.

## Run

```bash
python -m scraper.run --portal ingatlanbazar --max-listings 20 --eur-huf-rate 400
```

Output is a JSON array of `{url, stored, property_id, analysis, error}` — one
entry per listing. `analysis` is the same shape `GET /properties/{id}/analysis`
returns; it's `null` when no `DistrictBenchmarks` row exists yet for that
listing's district (seed those separately — the scraper doesn't invent
benchmark numbers).

Useful flags: `--max-pages`, `--min-delay`/`--max-delay` (politeness delay
between requests, randomized), `--headed` (watch it work instead of
headless), `-v` (debug logging).

## IMPORTANT — the selectors are placeholders, not verified

This was built in a sandboxed environment with no general internet access —
even a plain `page.goto()` to an external site fails here (only a short
allowlist of package registries is reachable). So the CSS selectors in
`scraper/portals/ingatlanbazar.py`'s `SELECTORS` dict are informed guesses
based on common Hungarian listing-portal markup, **not** confirmed against
the live, JS-rendered site.

What I *could* verify without network access, and did:
- `scraper/text_parsing.py` (price/size/rooms/district regex parsing) — fully
  unit tested against realistic Hungarian listing text, see `tests/test_text_parsing.py`.
- The actual Playwright traversal code (`extract_listing_urls`,
  `parse_listing_page`, `normalize_listing`) — run for real (not mocked)
  against local HTML fixtures via `file://` URLs, see
  `tests/test_scraper_offline.py`. This proves the code is wired correctly;
  it doesn't prove the selectors match the live site, since the fixtures
  were built to match the current placeholder selectors.
- `scraper/stealth.py`'s manual fallback patches — actually applied to a real
  Playwright page and checked (`navigator.webdriver` hidden, `plugins`/`languages`
  populated).
- `scraper/robots.py` — unit tested (mocked network + a fail-fast bad-URL case).

What still needs live verification, by you, once you have real internet access:

```bash
playwright codegen https://ingatlanbazar.hu
```

Click around a search page and a listing page; the codegen inspector shows
you the real selector for whatever you click. Update the `SELECTORS` dict
and `SEARCH_URL_TEMPLATE` at the top of `scraper/portals/ingatlanbazar.py` —
everything else (pagination, stealth, rate limiting, DB upsert, analyzer
hookup) doesn't need to change.

## Adding another portal

1. Check its `robots.txt` first — don't build against a portal that's said no.
2. Create `scraper/portals/<name>.py`, subclass `BaseScraper`
   (`scraper/base.py`) and implement `build_search_url`, `extract_listing_urls`,
   `parse_listing_page` — `scraper/portals/ingatlanbazar.py` is the template.
3. Register it in `scraper/registry.py`'s `PORTALS` dict.
4. It automatically gets stealth, rate limiting, robots.txt checking, DB
   upsert-by-url, and the analyzer hookup for free from `scraper/pipeline.py`.

## How a listing becomes a stored, analyzed Property

```
search results page  →  extract_listing_urls()        [portal-specific]
        ↓
listing detail page   →  parse_listing_page()          [portal-specific] → RawListing
        ↓
RawListing             →  normalize_listing()           [shared] → dict matching PropertyCreate
        ↓
dict                   →  crud.upsert_property_by_url() [shared] → Property row (create or update by url)
        ↓
Property.id            →  analyzer.analyze_property_by_id() [shared] → renovation ROI per tier, or
                                                                        a logged "no benchmark yet" skip
```

## Data hygiene notes

- Re-running the scraper updates existing rows (matched by `url`) rather than
  creating duplicates or erroring on the unique constraint.
- A listing missing a title or any parseable price is dropped rather than
  stored half-empty (`normalize_listing` returns `None`).
- District is parsed from the address text (Roman numeral, arabic + "kerület",
  or Budapest postal-code convention as a fallback) — if none of those match,
  the listing is still stored with `district="unknown"` rather than dropped,
  but it won't get an analyzer readout since `DistrictBenchmarks` is keyed by
  a real district number.
