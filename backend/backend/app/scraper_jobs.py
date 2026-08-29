"""
In-process job tracker for the "Scan Market" button: POST /api/scraper/trigger
kicks the autonomous ingestion agent (scraper/agent/orchestrator.py) off via
FastAPI's BackgroundTasks, and GET /api/scraper/status reports on it so the
frontend can poll for completion and know when to refresh the deals list.

State lives in a single process-wide dict guarded by a lock — enough for a
single-instance dev/demo deployment. It intentionally does not persist across
restarts or coordinate across multiple backend processes; a real multi-worker
deployment would need a shared store (DB row, Redis, etc.) instead.
"""
import datetime
import logging
import threading
import traceback
from typing import Tuple

from app import analyzer
from app.database import SessionLocal
from app.services import stats_service

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_state: dict = {
    "is_running": False,
    "started_at": None,
    "finished_at": None,
    "last_result": None,  # {"stored": int, "total": int}
    "error": None,
}


def get_status() -> dict:
    with _lock:
        return dict(_state)


def _now_iso() -> str:
    return datetime.datetime.utcnow().isoformat() + "Z"


def try_start(max_listings: int = 150, eur_huf_rate: float = analyzer.DEFAULT_EUR_HUF_RATE) -> Tuple[dict, bool]:
    """
    Atomically claims the "running" slot if nothing is in flight. Returns
    (status_dict, claimed) — the route only hands `run_job` (below) to
    BackgroundTasks when `claimed` is True, so a double-click or a second
    browser tab observes the same in-flight run instead of kicking off a
    duplicate one.
    """
    with _lock:
        if _state["is_running"]:
            return dict(_state), False
        _state["is_running"] = True
        _state["started_at"] = _now_iso()
        _state["finished_at"] = None
        _state["last_result"] = None
        _state["error"] = None
        return dict(_state), True


def run_job(max_listings: int, eur_huf_rate: float) -> None:
    """
    The actual scan — meant to be handed to BackgroundTasks, only after
    try_start() returned claimed=True. Everything, including the scraper
    import itself, is inside the try block: this runs in a background
    thread with no caller left to see a raised exception, so an import
    blowing up must still flip is_running back to False (via `finally`)
    rather than leaving the job stuck "running" forever.
    """
    try:
        from scraper.agent.orchestrator import run_agent

        results = run_agent(max_listings=max_listings, eur_huf_rate=eur_huf_rate)
        stored = sum(1 for r in results if r.stored)

        # Refresh district benchmarks from the now-freshly-scraped listings —
        # see app/services/stats_service.py. Best-effort: a bad recompute
        # must never make an otherwise-successful scan report as failed.
        db = SessionLocal()
        try:
            stats_service.update_district_benchmarks(db)
        except Exception:  # noqa: BLE001
            logger.exception("update_district_benchmarks failed after scan")
        finally:
            db.close()

        with _lock:
            _state["last_result"] = {"stored": stored, "total": len(results)}
            _state["error"] = None
    except Exception as e:  # noqa: BLE001 - reported via status, not raised (runs in a background thread)
        logger.exception("Scraper agent job failed")
        detail = traceback.format_exc(limit=3)
        with _lock:
            _state["error"] = f"{type(e).__name__}: {e}" if str(e) else f"{type(e).__name__} — {detail.strip().splitlines()[-1]}"
    finally:
        with _lock:
            _state["is_running"] = False
            _state["finished_at"] = _now_iso()
