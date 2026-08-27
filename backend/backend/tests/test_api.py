"""
Integration tests for the actual FastAPI routes in app/main.py, driven end
-to-end through fastapi.testclient.TestClient (real SQLAlchemy, a real
throwaway SQLite file — never backend/budapest_apartments.db).

DATABASE_URL is pinned to a temp file *before* app.main (and therefore
app.database) is ever imported anywhere in the pytest session, since that
module reads it once at import time. Naming this file test_api.py — sorted
alphabetically right after test_analyzer.py and before test_dashboard.py —
also means the real `sqlalchemy` package lands in sys.modules before
test_dashboard.py's stub-if-absent shim runs, so that shim's `if
"sqlalchemy" in sys.modules: return` guard skips it for the whole session.

Run with: python -m pytest tests/test_api.py -q
(needs the real project dependencies installed — see requirements.txt)
"""
import os
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

_tmp_db_dir = tempfile.mkdtemp(prefix="budapest_apartments_test_")
os.environ["DATABASE_URL"] = f"sqlite:///{Path(_tmp_db_dir) / 'test.db'}"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import access_control, scraper_jobs  # noqa: E402
from app import main as app_main  # noqa: E402
from app.database import init_db  # noqa: E402
from app.main import app  # noqa: E402

# Force the gate off for most tests regardless of whether the machine
# running these tests happens to have a real .env with ACCESS_PASSCODE set
# (app/__init__.py's load_dotenv() would otherwise leak that in here) —
# setting the module attribute directly, not the env var, since it's
# already been read into this attribute by the time we get control back.
access_control.ACCESS_PASSCODE = ""

# A pytest run must never arm the real twice-daily background scanner (it'd
# hit live portals from a test process) — same "flip the already-imported
# module attribute" pattern as ACCESS_PASSCODE above.
app_main.SCHEDULER_ENABLED = False

init_db()
client = TestClient(app)


def _wait_for_scan_to_finish(timeout: float = 5.0) -> dict:
    """
    BackgroundTasks under TestClient run on a real worker thread rather than
    blocking the response (see scraper_jobs.run_job's anyio.to_thread
    dispatch) — poll GET /api/scraper/status instead of assuming the POST
    response already reflects completion.
    """
    deadline = time.monotonic() + timeout
    status = client.get("/api/scraper/status").json()
    while status["is_running"] and time.monotonic() < deadline:
        time.sleep(0.05)
        status = client.get("/api/scraper/status").json()
    return status


# ---------------------------------------------------------------------------
# meta / auth
# ---------------------------------------------------------------------------

def test_root_health_check():
    response = client.get("/")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_unhandled_exception_returns_clean_json_and_keeps_cors_headers():
    """
    Regression test: Starlette's ServerErrorMiddleware (which runs the
    bare-Exception handler in app/main.py) sits *outside* CORSMiddleware, so
    without main.py's _cors_headers_for_origin fix, this response would
    reach a cross-origin browser (Vercel -> Render) with no CORS headers at
    all and get silently blocked — surfacing as an opaque network failure
    instead of the actual error. raise_server_exceptions=False is required
    here: TestClient's default re-raises server exceptions into the test
    process for debugging convenience, which isn't what a real network
    client ever sees (it always gets the HTTP response on the wire).
    """
    from fastapi.testclient import TestClient

    @app.get("/__test_unhandled_error")
    def _boom():
        raise ValueError("deliberate test explosion")

    try:
        no_raise_client = TestClient(app, raise_server_exceptions=False)
        response = no_raise_client.get(
            "/__test_unhandled_error",
            headers={"Origin": "https://budapest-real-estate-dashboard.vercel.app"},
        )
        assert response.status_code == 500
        assert "ValueError" in response.json()["detail"]
        # Default CORS policy is allow-all (see app/main.py) — the origin is
        # always echoed back (never a literal "*", since that's invalid
        # alongside Allow-Credentials: true), whichever origin asked.
        assert response.headers.get("access-control-allow-origin") == "https://budapest-real-estate-dashboard.vercel.app"

        arbitrary_origin = no_raise_client.get("/__test_unhandled_error", headers={"Origin": "https://some-other-site.example.com"})
        assert arbitrary_origin.headers.get("access-control-allow-origin") == "https://some-other-site.example.com"
    finally:
        app.router.routes = [r for r in app.router.routes if getattr(r, "path", None) != "/__test_unhandled_error"]


def test_cors_headers_for_origin_respects_a_locked_down_allowlist(monkeypatch):
    """
    The default policy is allow-all (see test above), but the underlying
    _cors_headers_for_origin() must still correctly restrict when a
    deployer opts into a specific FRONTEND_ORIGINS allowlist instead —
    this exercises that path directly, since it's not exercised by default.
    """
    monkeypatch.setattr(app_main, "_allow_all_origins", False)
    monkeypatch.setattr(app_main, "_frontend_origins_set", {"https://budapest-real-estate-dashboard.vercel.app"})
    monkeypatch.setattr(app_main, "_frontend_origin_regex_compiled", None)

    trusted = app_main._cors_headers_for_origin("https://budapest-real-estate-dashboard.vercel.app")
    assert trusted.get("Access-Control-Allow-Origin") == "https://budapest-real-estate-dashboard.vercel.app"

    untrusted = app_main._cors_headers_for_origin("https://evil.example.com")
    assert untrusted == {}


def test_auth_status_disabled_by_default():
    assert client.get("/api/auth/status").json() == {"passcode_required": False}


def test_passcode_gate_enabled(monkeypatch):
    monkeypatch.setattr(access_control, "ACCESS_PASSCODE", "letmein")
    try:
        assert client.get("/api/auth/status").json() == {"passcode_required": True}
        assert client.get("/deals").status_code == 401
        assert client.post("/api/auth/verify", json={"passcode": "wrong"}).status_code == 401
        assert client.post("/api/auth/verify", json={"passcode": "letmein"}).status_code == 200
        assert client.get("/deals", headers={"x-access-passcode": "letmein"}).status_code == 200
        # query-param fallback, for the PDF download <a href> links
        assert client.get("/deals?passcode=letmein").status_code == 200
        # root and the auth endpoints themselves always stay open
        assert client.get("/").status_code == 200
    finally:
        monkeypatch.setattr(access_control, "ACCESS_PASSCODE", "")


# ---------------------------------------------------------------------------
# district benchmarks (created first — properties' analysis depends on one)
# ---------------------------------------------------------------------------

def test_district_benchmark_crud():
    response = client.post(
        "/district-benchmarks",
        json={
            "district_number": 7,
            "avg_price_sqm_raw": 900_000,
            "avg_price_sqm_renovated": 1_500_000,
            "avg_rent_huf_sqm": 4500,
            "centroid_lat": 47.4989,
            "centroid_lng": 19.0700,
        },
    )
    assert response.status_code == 201, response.text
    assert response.json()["district_number"] == 7

    # duplicate create -> 409
    assert client.post("/district-benchmarks", json={"district_number": 7}).status_code == 409

    listed = client.get("/district-benchmarks").json()
    assert any(b["district_number"] == 7 for b in listed)

    fetched = client.get("/district-benchmarks/7")
    assert fetched.status_code == 200

    patched = client.patch("/district-benchmarks/7", json={"avg_price_sqm_renovated": 1_600_000})
    assert patched.status_code == 200
    assert patched.json()["avg_price_sqm_renovated"] == 1_600_000

    assert client.get("/district-benchmarks/999").status_code == 404


# ---------------------------------------------------------------------------
# properties / deals / dashboard
# ---------------------------------------------------------------------------

_PROPERTY_PAYLOAD = {
    "title": "Test flat, District VII",
    "district": "VII",
    "address": "Budapest VII., Test utca 1.",
    "size_sqm": 55.0,
    "rooms": 2.0,
    "balcony_sqm": 4.0,
    "price_huf": 60_000_000.0,
    "url": "https://example.test/listing/1",
    "condition": "needs renovation",
    "images": ["https://example.test/photo1.jpg"],
    "portal": "jofogas",
}


def test_property_and_deal_lifecycle():
    created = client.post("/properties", json=_PROPERTY_PAYLOAD)
    assert created.status_code == 201, created.text
    prop = created.json()
    property_id = prop["id"]
    assert prop["district"] == "VII"
    assert prop["pipeline_status"] == "new"
    assert prop["is_favorite"] is False

    fetched = client.get(f"/properties/{property_id}")
    assert fetched.status_code == 200
    assert client.get("/properties/9999999").status_code == 404

    listed = client.get("/properties").json()
    assert any(p["id"] == property_id for p in listed)

    patched = client.patch(f"/properties/{property_id}", json={"is_favorite": True, "pipeline_status": "reviewing"})
    assert patched.status_code == 200
    assert patched.json()["is_favorite"] is True
    assert patched.json()["pipeline_status"] == "reviewing"

    # invalid pipeline_status rejected by the field_validator
    invalid = client.patch(f"/properties/{property_id}", json={"pipeline_status": "not_a_real_status"})
    assert invalid.status_code == 422

    analysis = client.get(f"/properties/{property_id}/analysis")
    assert analysis.status_code == 200
    assert "tiers" in analysis.json()

    # automated underwriting agent (app/services/valuation_agent.py) — not run
    # automatically on a manual POST /properties (only on a real scrape), so
    # trigger it explicitly here.
    underwritten = client.post(f"/properties/{property_id}/underwrite")
    assert underwritten.status_code == 200, underwritten.text
    underwriting_result = underwritten.json()
    assert underwriting_result["deal_score"] is not None
    assert underwriting_result["status"] is not None
    assert client.post("/properties/9999999/underwrite").status_code == 404

    fetched_after_underwrite = client.get(f"/properties/{property_id}").json()
    assert fetched_after_underwrite["underwriting_deal_score"] == underwriting_result["deal_score"]
    assert fetched_after_underwrite["underwriting_updated_at"] is not None

    deals = client.get("/deals").json()
    deal = next((d for d in deals if d["id"] == property_id), None)
    assert deal is not None
    assert deal["deal_score"] is not None
    assert deal["analysis"] is not None
    assert deal["underwriting"] is not None
    assert deal["underwriting"]["deal_score"] == underwriting_result["deal_score"]

    filtered = client.get("/deals", params={"district": "VII", "pipeline_status": "reviewing"}).json()
    assert any(d["id"] == property_id for d in filtered)

    archived = client.get("/deals", params={"pipeline_status": "archived"})
    assert archived.status_code == 200
    assert all(d["id"] != property_id for d in archived.json())  # this property is "reviewing", not "archived"

    stats = client.get("/dashboard/stats")
    assert stats.status_code == 200
    assert stats.json()["total_listings"] >= 1

    spec_sheet = client.get(f"/properties/{property_id}/spec-sheet")
    assert spec_sheet.status_code == 200
    assert spec_sheet.headers["content-type"] == "application/pdf"

    memo = client.get(f"/properties/{property_id}/investment-memo")
    assert memo.status_code == 200
    assert memo.headers["content-type"] == "application/pdf"

    deleted = client.delete(f"/properties/{property_id}")
    assert deleted.status_code == 204
    assert client.get(f"/properties/{property_id}").status_code == 404


def test_create_property_requires_title_and_district():
    response = client.post("/properties", json={"size_sqm": 40.0})  # missing required title/district
    assert response.status_code == 422


def test_deals_sorting_and_unlimited_listings():
    cheap = client.post(
        "/properties",
        json={
            **_PROPERTY_PAYLOAD,
            "title": "Cheap sort-test flat",
            "url": "https://example.test/listing/sort-cheap",
            "price_huf": 20_000_000,
            "size_sqm": 40.0,
        },
    ).json()
    expensive = client.post(
        "/properties",
        json={
            **_PROPERTY_PAYLOAD,
            "title": "Expensive sort-test flat",
            "url": "https://example.test/listing/sort-expensive",
            "price_huf": 90_000_000,
            "size_sqm": 40.0,
        },
    ).json()

    # min_flip_roi disabled (very low bar) — this test is about sort/paging,
    # not the strict Net ROI hurdle, and these fixtures' arbitrary prices
    # aren't meant to clear it.
    no_hurdle = {"min_flip_roi": -1000}

    price_desc_ids = [d["id"] for d in client.get("/deals", params={**no_hurdle, "sort": "price_desc"}).json()]
    assert price_desc_ids.index(expensive["id"]) < price_desc_ids.index(cheap["id"])

    price_asc_ids = [d["id"] for d in client.get("/deals", params={**no_hurdle, "sort": "price_asc"}).json()]
    assert price_asc_ids.index(cheap["id"]) < price_asc_ids.index(expensive["id"])

    # No `limit` -> every matching listing comes back, not a truncated default page.
    unlimited = client.get("/deals", params=no_hurdle).json()
    assert len(unlimited) >= 2
    assert cheap["id"] in [d["id"] for d in unlimited]
    assert expensive["id"] in [d["id"] for d in unlimited]

    limited = client.get("/deals", params={**no_hurdle, "limit": 1}).json()
    assert len(limited) == 1

    client.delete(f"/properties/{cheap['id']}")
    client.delete(f"/properties/{expensive['id']}")


def test_condition_tag_and_underwriting_never_null_when_benchmark_exists():
    """
    A property in a district with a benchmark on file (VII is auto-seeded —
    see backend/seed_data.json) should get a non-null underwriting.deal_score/
    flip_roi_percent/net_profit_huf even WITHOUT ever calling POST
    /properties/{id}/underwrite — backfilled from the live analyzer readout,
    per app/dashboard.py's has_underwriting fallback.
    """
    created = client.post(
        "/properties",
        json={
            **_PROPERTY_PAYLOAD,
            "title": "Fallback underwriting test flat",
            "url": "https://example.test/listing/fallback-underwriting",
            "condition": "Felújítandó, sürgős eladás",
        },
    )
    assert created.status_code == 201, created.text
    property_id = created.json()["id"]

    deals = client.get("/deals").json()
    deal = next(d for d in deals if d["id"] == property_id)

    assert deal["condition_tag"] == "Needs Renovation"
    assert deal["duplicate_source_urls"] == []
    assert deal["underwriting"] is not None
    assert deal["underwriting"]["deal_score"] is not None
    assert deal["underwriting"]["flip_roi_percent"] is not None
    assert deal["underwriting"]["net_profit_huf"] is not None
    # Not actually persisted yet (no scan/underwrite call happened) — status/
    # updated_at should honestly reflect that, even though the numbers above
    # are filled in live.
    assert deal["underwriting"]["updated_at"] is None

    client.delete(f"/properties/{property_id}")


def test_price_per_sqm_filter():
    created = client.post(
        "/properties",
        json={
            **_PROPERTY_PAYLOAD,
            "title": "Price/sqm filter test flat",
            "url": "https://example.test/listing/price-per-sqm-filter",
            "price_huf": 100_000_000.0,  # 100M / 55 sqm ~= 1,818,182 HUF/sqm
        },
    )
    assert created.status_code == 201, created.text
    property_id = created.json()["id"]

    matches = client.get(
        "/deals", params={"min_flip_roi": -1000, "min_price_per_sqm": 1_800_000, "max_price_per_sqm": 1_900_000}
    ).json()
    assert any(d["id"] == property_id for d in matches)

    excluded = client.get("/deals", params={"max_price_per_sqm": 1_000_000}).json()
    assert all(d["id"] != property_id for d in excluded)

    client.delete(f"/properties/{property_id}")


def test_deals_csv_export():
    created = client.post(
        "/properties",
        json={
            **_PROPERTY_PAYLOAD,
            "title": "CSV export test flat",
            "url": "https://example.test/listing/csv-export",
        },
    )
    assert created.status_code == 201, created.text
    property_id = created.json()["id"]

    response = client.get("/deals/export.csv")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "attachment" in response.headers["content-disposition"]

    body = response.text
    lines = body.strip().splitlines()
    header = lines[0].split(",")
    assert "underwriting_deal_score" in header
    assert "condition_tag" in header
    assert any("CSV export test flat" in line for line in lines[1:])

    client.delete(f"/properties/{property_id}")


# ---------------------------------------------------------------------------
# fx-rate (hits a real external API; falls back gracefully on failure — see
# app/fx_rate.py — so this only asserts the response shape, not the value)
# ---------------------------------------------------------------------------

def test_fx_rate_endpoint():
    response = client.get("/fx-rate")
    assert response.status_code == 200
    body = response.json()
    assert body["rate"] > 0
    assert "is_live" in body


# ---------------------------------------------------------------------------
# scraper trigger/status — run_agent is monkeypatched so this never launches
# a real Playwright browser or hits a live portal.
# ---------------------------------------------------------------------------

def test_scraper_trigger_and_status(monkeypatch):
    from scraper.pipeline import ScrapeResult

    def fake_run_agent(max_listings, eur_huf_rate):
        return [ScrapeResult(url="https://example.test/1", stored=True, property_id=1)]

    monkeypatch.setattr("scraper.agent.orchestrator.run_agent", fake_run_agent)

    response = client.post("/api/scraper/trigger", params={"max_listings": 5})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "running"
    assert body["message"] == "Scan started successfully"

    status = _wait_for_scan_to_finish()
    assert status["is_running"] is False
    assert status["last_result"] == {"stored": 1, "total": 1}


def test_scraper_trigger_reports_failure(monkeypatch):
    def failing_run_agent(max_listings, eur_huf_rate):
        raise RuntimeError("portal unreachable")

    monkeypatch.setattr("scraper.agent.orchestrator.run_agent", failing_run_agent)

    response = client.post("/api/scraper/trigger", params={"max_listings": 5})
    assert response.status_code == 200
    status = _wait_for_scan_to_finish()
    assert status["is_running"] is False
    assert "portal unreachable" in status["error"]


def test_scraper_trigger_does_not_duplicate_in_flight_run(monkeypatch):
    """try_start() returning claimed=False must not schedule a second run_job."""
    scheduled = []
    monkeypatch.setattr(scraper_jobs, "try_start", lambda **kw: ({"is_running": True, "started_at": "x", "finished_at": None, "last_result": None, "error": None}, False))
    monkeypatch.setattr(scraper_jobs, "run_job", lambda *a, **kw: scheduled.append(a))

    response = client.post("/api/scraper/trigger")
    assert response.status_code == 200
    assert response.json()["message"] == "A scan is already running"
    assert scheduled == []  # run_job must not have been scheduled


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
