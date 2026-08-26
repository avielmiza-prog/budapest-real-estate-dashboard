"""
Windows-only fixup for a real, reproducible bug: launching Playwright's sync
API from a background thread while the process-wide asyncio event loop
policy is `SelectorEventLoop` fails instantly with a bare `NotImplementedError`
(from asyncio.base_events._make_subprocess_transport — SelectorEventLoop
doesn't implement subprocess support on Windows, and Playwright's driver
needs to spawn a Node.js subprocess to talk to the browser).

`uvicorn app.main:app --reload` — the exact command this project's own docs
recommend for local dev — switches the process to SelectorEventLoopPolicy
for reload/signal-handling compatibility. That means every "Scan Market"
click (POST /api/scraper/trigger -> a FastAPI BackgroundTask -> this
scraper) hits the bug the moment Playwright tries to start, under --reload.
A plain `uvicorn app.main:app` (no --reload) never hits it, which is why it
can look like it "only sometimes" fails.

Call ensure_subprocess_capable_event_loop() once before the first
`sync_playwright()` in any code path that might run inside a background
thread (scraper/pipeline.py and scraper/agent/orchestrator.py both do).
"""
import asyncio
import logging
import sys

logger = logging.getLogger(__name__)

_fixed = False


def ensure_subprocess_capable_event_loop() -> None:
    """
    Idempotent, cheap to call on every scrape. No-op on non-Windows (this
    bug is Windows-specific — SelectorEventLoop supports subprocesses fine
    on Linux/macOS) and once the policy is already Proactor.
    """
    global _fixed
    if _fixed or sys.platform != "win32":
        return
    policy = asyncio.get_event_loop_policy()
    if not isinstance(policy, asyncio.WindowsProactorEventLoopPolicy):
        logger.info(
            "Switching process-wide asyncio event loop policy to WindowsProactorEventLoopPolicy "
            "(was %s) so Playwright's subprocess-based driver can start.",
            type(policy).__name__,
        )
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    _fixed = True
