"""
Lightweight shared-passcode gate for sharing this dashboard's URL with a
partner/investor without standing up real user accounts.

Off by default — only activates when ACCESS_PASSCODE is set in the
environment, so local dev and a first deploy without it configured both
work with zero friction. Not a security boundary against a determined
attacker (one shared secret over a plain header, no rate limiting, no
rotation, no per-user audit trail) — it's a "don't leave a public URL wide
open" curtain, matching what was actually asked for (a lightweight investor
passcode), not a real auth system.
"""
import os
import secrets

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

ACCESS_PASSCODE = os.getenv("ACCESS_PASSCODE", "").strip()
HEADER_NAME = "x-access-passcode"

# Always reachable without the passcode: the root health check (so platform
# health probes don't need to know the secret), and the two auth endpoints
# themselves — you can't verify a passcode from behind the same gate that
# requires one.
_OPEN_PATHS = {"/", "/api/auth/status", "/api/auth/verify"}


def is_enabled() -> bool:
    return bool(ACCESS_PASSCODE)


def check(supplied: str) -> bool:
    """Constant-time compare so response timing can't leak the passcode."""
    return secrets.compare_digest(supplied or "", ACCESS_PASSCODE)


class PasscodeGateMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if not is_enabled() or request.method == "OPTIONS" or request.url.path in _OPEN_PATHS:
            return await call_next(request)
        # Header for normal fetch() calls; `?passcode=` as a fallback for the
        # spec-sheet/investment-memo PDF links, which the frontend opens as
        # plain <a href> navigations (a browser navigation can't attach a
        # custom header) — see lib/api.ts's getSpecSheetUrl/getInvestmentMemoUrl.
        supplied = request.headers.get(HEADER_NAME) or request.query_params.get("passcode", "")
        if not check(supplied):
            return JSONResponse({"detail": "Missing or incorrect access passcode."}, status_code=401)
        return await call_next(request)
