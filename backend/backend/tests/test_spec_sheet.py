"""
Unit tests for app.spec_sheet — actually generates real PDFs with reportlab
(available in this environment, unlike sqlalchemy) and inspects them with
pypdf, rather than just asserting the code runs. Image downloads are tested
against a local HTTP server on 127.0.0.1 so this doesn't need external
network access (blocked in the sandbox this was written in).

Run with: python3 tests/test_spec_sheet.py
"""
import http.server
import io
import sys
import threading
import types
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _stub_sqlalchemy():
    if "sqlalchemy" in sys.modules:
        return
    fake_sa = types.ModuleType("sqlalchemy")
    for name in ["Column", "Integer", "Float", "String", "Text", "DateTime", "JSON", "Boolean", "create_engine", "inspect", "text"]:
        setattr(fake_sa, name, lambda *a, **k: None)
    fake_orm = types.ModuleType("sqlalchemy.orm")
    fake_orm.Session = object
    fake_orm.declarative_base = lambda *a, **k: type(
        "Base", (), {"metadata": SimpleNamespace(create_all=lambda **kw: None)}
    )
    fake_orm.sessionmaker = lambda *a, **k: (lambda: None)
    fake_sa.orm = fake_orm
    sys.modules["sqlalchemy"] = fake_sa
    sys.modules["sqlalchemy.orm"] = fake_orm


_stub_sqlalchemy()

from app import spec_sheet  # noqa: E402


def _make_jpeg_bytes(color) -> bytes:
    from PIL import Image as PILImage

    img = PILImage.new("RGB", (400, 300), color=color)
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


class _ImageServer:
    """Serves a couple of real JPEGs on 127.0.0.1 so image-download tests don't need external network."""

    def __init__(self, images: dict):
        self._images = images
        handler = self._make_handler()
        self.server = http.server.HTTPServer(("127.0.0.1", 0), handler)
        self.port = self.server.server_address[1]
        self._thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self._thread.start()

    def _make_handler(self):
        images = self._images

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                body = images.get(self.path)
                if body is not None:
                    self.send_response(200)
                    self.send_header("Content-Type", "image/jpeg")
                    self.end_headers()
                    self.wfile.write(body)
                else:
                    self.send_response(404)
                    self.end_headers()

            def log_message(self, *a):
                pass

        return Handler

    def url(self, path: str) -> str:
        return f"http://127.0.0.1:{self.port}{path}"

    def shutdown(self):
        self.server.shutdown()


def test_download_image_bytes_success_and_failure_cases():
    server = _ImageServer({"/ok.jpg": _make_jpeg_bytes((10, 20, 30))})
    try:
        data = spec_sheet._download_image_bytes(server.url("/ok.jpg"))
        assert data is not None and len(data) > 0

        assert spec_sheet._download_image_bytes(server.url("/missing.jpg")) is None
        assert spec_sheet._download_image_bytes("http://127.0.0.1:1/nope.jpg", timeout=2) is None
    finally:
        server.shutdown()


def test_build_photo_section_with_no_images():
    flowables = spec_sheet._build_photo_section([])
    assert len(flowables) == 1  # just the "no photos" paragraph


def test_build_photo_section_embeds_reachable_and_skips_broken():
    server = _ImageServer(
        {"/a.jpg": _make_jpeg_bytes((200, 0, 0)), "/b.jpg": _make_jpeg_bytes((0, 200, 0))}
    )
    try:
        urls = [server.url("/a.jpg"), server.url("/b.jpg"), server.url("/broken.jpg")]
        flowables = spec_sheet._build_photo_section(urls)
        # Should produce at least a photo table plus a "1 photo(s) could not be downloaded" note.
        assert len(flowables) >= 2
    finally:
        server.shutdown()


def test_format_rooms():
    assert spec_sheet._format_rooms(3.0) == "3"
    assert spec_sheet._format_rooms(2.5) == "2+1"
    assert spec_sheet._format_rooms(None) == "—"


def test_generate_spec_sheet_pdf_end_to_end():
    from pypdf import PdfReader

    server = _ImageServer({"/photo.jpg": _make_jpeg_bytes((120, 160, 200))})
    try:
        prop = SimpleNamespace(
            id=1,
            title="Test listing",
            address="1073 Budapest, VII. kerulet",
            district="VII",
            size_sqm=55.0,
            rooms=2.5,
            condition="felujitott",
            price_huf=89_900_000.0,
            price_per_sqm=1_634_545.45,
            url="https://example.com/listing/1",
            images=[server.url("/photo.jpg")],
        )
        benchmark = SimpleNamespace(avg_price_sqm_raw=950_000, avg_price_sqm_renovated=1_250_000)

        pdf_bytes = spec_sheet.generate_spec_sheet_pdf(prop, benchmark=benchmark, analysis=None)
        assert pdf_bytes[:4] == b"%PDF"

        reader = PdfReader(io.BytesIO(pdf_bytes))
        assert len(reader.pages) >= 2  # summary+photos page, plus at least one checklist page

        full_text = "".join(page.extract_text() for page in reader.pages)
        for expected in [
            "Contractor Spec Sheet",
            "Test listing",
            "55.0 sqm",
            "2+1",
            "89 900 000 HUF",
            "On-Site Quoting Checklist",
            "Structural & General Condition",
            "Electrical",
            "[ ]",
        ]:
            assert expected in full_text, f"missing {expected!r} in generated PDF text"

        image_count = sum(len(page.images) for page in reader.pages)
        assert image_count == 1
    finally:
        server.shutdown()


if __name__ == "__main__":
    tests = [v for k, v in globals().items() if k.startswith("test_") and callable(v)]
    failures = 0
    for t in tests:
        try:
            t()
            print(f"PASS: {t.__name__}")
        except AssertionError as e:
            failures += 1
            print(f"FAIL: {t.__name__}: {e}")
        except Exception as e:  # noqa: BLE001
            failures += 1
            print(f"ERROR: {t.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(tests) - failures}/{len(tests)} tests passed")
    sys.exit(1 if failures else 0)
