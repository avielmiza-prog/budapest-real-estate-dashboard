"""
Loading .env here — not in database.py or access_control.py — guarantees it
runs before any app.* submodule's own module-level `os.getenv(...)` calls
(DATABASE_URL, ACCESS_PASSCODE, FRONTEND_ORIGINS, ...), since Python always
executes a package's __init__.py before importing any of its submodules,
regardless of which submodule a caller imports first.
"""
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")
