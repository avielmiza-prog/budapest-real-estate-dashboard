"""
=====================================================================
 TEST / DEMO DATA ONLY — DO NOT RUN THIS AGAINST A PRODUCTION DATABASE
=====================================================================
Seed the database with district benchmarks (I-XXIII) and a batch of
FICTIONAL mock apartment listings, so the dashboard has something to show
without needing a live scrape (the real scraper's CSS selectors are
unverified placeholders — see scraper/portals/ingatlanbazar.py).

Every property this script creates is entirely synthetic: titles, prices,
and addresses are all generated, not scraped. `images` is always an empty
list `[]` for every mock listing — this script does NOT generate, fetch, or
link to any placeholder/stock-photo service (no picsum, no Unsplash, no
`placehold.co`, nothing). A mock listing has no real photos, so it has no
photos, full stop; the frontend's "No photos available" state is what
renders for these. Real scraped Property rows (produced by
scraper/pipeline.py) only ever contain photo URLs pulled directly from a
listing's own page — see scraper/normalize.py, which likewise has no
placeholder-image fallback of any kind.

Run from backend/backend:
    python3 scripts/seed_data.py            # upsert benchmarks + add mock listings
    python3 scripts/seed_data.py --reset     # wipe properties + benchmarks first
    python3 scripts/seed_data.py --count 80  # generate 80 mock listings instead of 40

Re-running without --reset is safe: benchmarks are upserted by district
number and listings are upserted by their (deterministic, mock) url, so you
just get the same rows updated in place rather than duplicates.

Benchmark HUF/sqm figures below are illustrative placeholders reflecting the
*relative* ordering of Budapest's districts (inner districts like V/VI/VII
pricier than outer ones like XX/XXI/XXIII), not verified market data —
replace with real figures (or scraped/aggregated ones) before using this for
actual investment decisions.
"""
import argparse
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import crud, schemas  # noqa: E402
from app.analyzer import district_number_to_roman  # noqa: E402
from app.database import SessionLocal, init_db  # noqa: E402

# district_number (1-23) -> (avg HUF/sqm raw/unrenovated, avg HUF/sqm renovated)
DISTRICT_BENCHMARKS_HUF_SQM = {
    1: (950_000, 1_500_000),    # I. Várkerület
    2: (900_000, 1_450_000),    # II. Rózsadomb
    3: (650_000, 1_000_000),    # III. Óbuda
    4: (500_000, 800_000),      # IV. Újpest
    5: (1_100_000, 1_750_000),  # V. Belváros-Lipótváros
    6: (950_000, 1_550_000),    # VI. Terézváros
    7: (900_000, 1_500_000),    # VII. Erzsébetváros
    8: (650_000, 1_050_000),    # VIII. Józsefváros
    9: (750_000, 1_200_000),    # IX. Ferencváros
    10: (480_000, 780_000),     # X. Kőbánya
    11: (800_000, 1_300_000),   # XI. Újbuda
    12: (950_000, 1_550_000),   # XII. Hegyvidék
    13: (800_000, 1_300_000),   # XIII. Angyalföld
    14: (650_000, 1_050_000),   # XIV. Zugló
    15: (500_000, 800_000),     # XV. Rákospalota
    16: (520_000, 830_000),     # XVI. Mátyásföld
    17: (480_000, 770_000),     # XVII. Rákosmente
    18: (500_000, 800_000),     # XVIII. Pestszentlőrinc
    19: (480_000, 770_000),     # XIX. Kispest
    20: (460_000, 740_000),     # XX. Pesterzsébet
    21: (430_000, 690_000),     # XXI. Csepel
    22: (550_000, 880_000),     # XXII. Budafok-Tétény
    23: (420_000, 670_000),     # XXIII. Soroksár
}

# Approximate geographic centroid of each district (public-knowledge map
# coordinates, not surveyed/scraped data) — used only as a map-pin fallback
# for listings the scraper couldn't geocode a precise address for.
DISTRICT_CENTROIDS = {
    1: (47.4959, 19.0398), 2: (47.5262, 19.0201), 3: (47.5636, 19.0396),
    4: (47.5647, 19.0888), 5: (47.4979, 19.0537), 6: (47.5065, 19.0655),
    7: (47.4979, 19.0707), 8: (47.4886, 19.0713), 9: (47.4783, 19.0715),
    10: (47.4794, 19.1394), 11: (47.4675, 19.0432), 12: (47.5024, 18.9909),
    13: (47.5372, 19.0787), 14: (47.5171, 19.1032), 15: (47.5657, 19.1281),
    16: (47.5140, 19.1935), 17: (47.4881, 19.2601), 18: (47.4390, 19.1826),
    19: (47.4515, 19.1416), 20: (47.4362, 19.1013), 21: (47.4177, 19.0765),
    22: (47.4147, 18.9532), 23: (47.3888, 19.1361),
}

# Illustrative avg monthly HUF/sqm rent per district (~4.5% gross yield off
# the renovated benchmark above) — a placeholder ratio, not verified rental
# market data. Replace with real figures before using this for decisions.
_RENT_YIELD_RATIO = 0.0045

CONDITIONS = ["raw", "needs renovation", "partially renovated", "renovated", "new build"]
STREET_NAMES = [
    "Rákóczi út", "Andrássy út", "Váci utca", "Bartók Béla út", "Üllői út",
    "Baross utca", "Thököly út", "Kossuth Lajos utca", "Dózsa György út",
    "Petőfi Sándor utca", "Attila út", "Bajcsy-Zsilinszky út", "Soroksári út",
]
TITLE_TEMPLATES = [
    "{rooms} szoba, {sqm} m² lakás a {district}. kerületben",
    "Felújítandó lakás {district}. kerület, {sqm} m²",
    "Napfényes {rooms} szobás otthon a {district}. kerületben",
    "Panorámás lakás {district}. kerület, {sqm} m²",
    "Csendes utcában, {sqm} m², {district}. kerület",
]


def make_mock_properties(count: int, seed: int = 42) -> list[schemas.PropertyCreate]:
    rng = random.Random(seed)
    properties = []

    for i in range(count):
        district_number = rng.randint(1, 23)
        district_roman = district_number_to_roman(district_number)
        raw_benchmark, renovated_benchmark = DISTRICT_BENCHMARKS_HUF_SQM[district_number]
        centroid_lat, centroid_lng = DISTRICT_CENTROIDS[district_number]

        size_sqm = round(rng.uniform(28, 140), 1)
        rooms = rng.choice([1, 1.5, 2, 2, 2.5, 3, 3, 3.5, 4, 4.5, 5])
        condition = rng.choice(CONDITIONS)
        balcony_sqm = round(rng.uniform(3, 12), 1) if rng.random() < 0.5 else None
        # Small jitter around the district centroid so mock pins aren't all
        # stacked on the exact same point on the split-view map.
        latitude = round(centroid_lat + rng.uniform(-0.01, 0.01), 6)
        longitude = round(centroid_lng + rng.uniform(-0.01, 0.01), 6)

        # Price/sqm reference depends on condition, same rule the backend
        # uses to judge under/over-pricing (see app/dashboard.py).
        reference = renovated_benchmark if condition in ("renovated", "new build") else raw_benchmark
        # Spread listings from noticeably-underpriced to noticeably-overpriced
        # so filters/sorting (deals, min ROI) have something to bite on.
        price_multiplier = rng.uniform(0.75, 1.15)
        price_per_sqm = round(reference * price_multiplier, -3)  # round to nearest 1000 HUF
        price_huf = round(price_per_sqm * size_sqm, -3)

        street = rng.choice(STREET_NAMES)
        house_number = rng.randint(1, 180)
        title = rng.choice(TITLE_TEMPLATES).format(
            rooms=rooms if isinstance(rooms, int) else str(rooms).replace(".0", ""),
            sqm=size_sqm,
            district=district_roman,
        )
        properties.append(
            schemas.PropertyCreate(
                title=title,
                district=district_roman,
                address=f"{street} {house_number}., Budapest",
                size_sqm=size_sqm,
                rooms=rooms,
                balcony_sqm=balcony_sqm,
                price_huf=price_huf,
                price_eur=round(price_huf / 400, 2),
                url=f"https://mock.ingatlanbazar.hu/listing/bp-{district_roman.lower()}-{i:04d}",
                condition=condition,
                # Mock listings have no real photos to show — an empty list
                # is the honest result, same as a genuinely photo-less
                # scraped listing. No placeholder/stock-photo service is
                # used anywhere in this codebase.
                images=[],
                portal="mock",
                latitude=latitude,
                longitude=longitude,
                pipeline_status=rng.choice(["new", "new", "new", "reviewing", "tour_scheduled"]),
            )
        )

    return properties


def seed_district_benchmarks(db) -> int:
    count = 0
    for district_number, (raw, renovated) in DISTRICT_BENCHMARKS_HUF_SQM.items():
        lat, lng = DISTRICT_CENTROIDS[district_number]
        crud.upsert_district_benchmark(
            db,
            district_number,
            schemas.DistrictBenchmarkUpdate(
                avg_price_sqm_raw=raw,
                avg_price_sqm_renovated=renovated,
                avg_rent_huf_sqm=round(renovated * _RENT_YIELD_RATIO, -2),
                centroid_lat=lat,
                centroid_lng=lng,
            ),
        )
        count += 1
    return count


def seed_properties(db, count: int) -> int:
    stored = 0
    for payload in make_mock_properties(count):
        crud.upsert_property_by_url(db, payload)
        stored += 1
    return stored


def reset_data(db) -> None:
    from app import models

    db.query(models.Property).delete()
    db.query(models.DistrictBenchmark).delete()
    db.commit()


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed district benchmarks + mock apartment listings.")
    parser.add_argument("--count", type=int, default=40, help="How many mock listings to generate.")
    parser.add_argument("--reset", action="store_true", help="Delete existing properties/benchmarks first.")
    args = parser.parse_args()

    print(
        "WARNING: this generates FICTIONAL test/demo listings (no real photos — "
        "images=[] for every mock listing, no placeholder/stock-photo service "
        "used) — not real scraped data. Do not run against a production database.",
        file=sys.stderr,
    )

    init_db()
    db = SessionLocal()
    try:
        if args.reset:
            reset_data(db)
            print("Cleared existing properties and district benchmarks.")

        benchmark_count = seed_district_benchmarks(db)
        property_count = seed_properties(db, args.count)

        print(f"Seeded {benchmark_count} district benchmarks (I-XXIII).")
        print(f"Seeded {property_count} mock apartment listings.")
    finally:
        db.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
