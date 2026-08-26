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
from app.database import init_db  # noqa: E402
from app.main import app  # noqa: E402

# Force the gate off for most tests regardless of whether the machine
# running these tests happens to have a real .env with ACCESS_PASSCODE set
# (app/__init__.py's load_dotenv() would otherwise leak that in here) —
# setting the module attribute directly, not the env var, since it's
# already been read into this attribute by the time we get control back.
access_control.ACCESS_PASSCODE = ""

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

    deals = client.get("/deals").json()
    deal = next((d for d in deals if d["id"] == property_id), None)
    assert deal is not None
    assert deal["deal_score"] is not None
    assert deal["analysis"] is not None

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
