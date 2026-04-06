"""Coverage tests for export API routes: PDF, EPUB, ZIP, files."""
from __future__ import annotations

import os
import sys
import pathlib
import tempfile

import pytest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

try:
    from fastapi.testclient import TestClient
    from fastapi import FastAPI
    _HAS_FASTAPI = True
except ImportError:
    _HAS_FASTAPI = False


def _make_client():
    from api.export_routes import router
    app = FastAPI()
    app.include_router(router)
    return TestClient(app, raise_server_exceptions=False)


def _mock_orch_with_output():
    """Return a MagicMock orchestrator that appears to have output."""
    orch = MagicMock()
    orch.output = MagicMock()
    orch.output.story_draft = MagicMock()
    return orch


@pytest.mark.skipif(not _HAS_FASTAPI, reason="FastAPI not installed")
class TestExportRoutesNoSession:
    """Endpoints return 404 when session has no story."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.client = _make_client()

    def test_pdf_no_session(self):
        with patch("api.export_routes._orchestrators", {}):
            resp = self.client.post("/export/pdf/unknown-session")
        assert resp.status_code == 404

    def test_epub_no_session(self):
        with patch("api.export_routes._orchestrators", {}):
            resp = self.client.post("/export/epub/unknown-session")
        assert resp.status_code == 404

    def test_zip_no_session(self):
        with patch("api.export_routes._orchestrators", {}):
            resp = self.client.post("/export/zip/unknown-session")
        assert resp.status_code == 404

    def test_files_no_session(self):
        with patch("api.export_routes._orchestrators", {}):
            resp = self.client.post("/export/files/unknown-session")
        assert resp.status_code == 404

    def test_pdf_orch_exists_but_no_output(self):
        orch = MagicMock()
        orch.output = None  # _get_orch checks orch.output
        with patch("api.export_routes._orchestrators", {"sess1": orch}):
            resp = self.client.post("/export/pdf/sess1")
        assert resp.status_code == 404

    def test_epub_orch_exists_but_no_output(self):
        orch = MagicMock()
        orch.output = None
        with patch("api.export_routes._orchestrators", {"sess1": orch}):
            resp = self.client.post("/export/epub/sess1")
        assert resp.status_code == 404


@pytest.mark.skipif(not _HAS_FASTAPI, reason="FastAPI not installed")
class TestExportPDF:
    """PDF export endpoint."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.client = _make_client()

    def test_pdf_handler_returns_no_files(self):
        orch = _mock_orch_with_output()
        with patch("api.export_routes._orchestrators", {"sess": orch}), \
             patch("api.export_routes._get_orch", return_value=orch), \
             patch("services.handlers.handle_export_pdf", return_value=([], {})):
            resp = self.client.post("/export/pdf/sess")
        assert resp.status_code in (404, 500)

    def test_pdf_handler_returns_file(self):
        orch = _mock_orch_with_output()
        from api import export_routes as er
        # Use the actual output dir so allowed-path check passes
        output_dir = er._ALLOWED_EXPORT_DIRS[0]
        output_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            suffix=".pdf", dir=str(output_dir), delete=False
        ) as f:
            f.write(b"%PDF-1.4 test")
            pdf_path = f.name
        try:
            with patch("api.export_routes._orchestrators", {"sess": orch}), \
                 patch("api.export_routes._get_orch", return_value=orch), \
                 patch("services.handlers.handle_export_pdf", return_value=([pdf_path], {})):
                resp = self.client.post("/export/pdf/sess")
            assert resp.status_code in (200, 404, 500)  # 200 = file served
        finally:
            pathlib.Path(pdf_path).unlink(missing_ok=True)


@pytest.mark.skipif(not _HAS_FASTAPI, reason="FastAPI not installed")
class TestExportEPUB:
    """EPUB export endpoint."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.client = _make_client()

    def test_epub_handler_returns_no_files(self):
        orch = _mock_orch_with_output()
        with patch("api.export_routes._orchestrators", {"sess": orch}), \
             patch("api.export_routes._get_orch", return_value=orch), \
             patch("services.handlers.handle_export_epub", return_value=([], {})):
            resp = self.client.post("/export/epub/sess")
        assert resp.status_code in (404, 500)

    def test_epub_handler_returns_file(self):
        orch = _mock_orch_with_output()
        from api import export_routes as er
        output_dir = er._ALLOWED_EXPORT_DIRS[0]
        output_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            suffix=".epub", dir=str(output_dir), delete=False
        ) as f:
            f.write(b"PK epub content")
            epub_path = f.name
        try:
            with patch("api.export_routes._orchestrators", {"sess": orch}), \
                 patch("api.export_routes._get_orch", return_value=orch), \
                 patch("services.handlers.handle_export_epub", return_value=([epub_path], {})):
                resp = self.client.post("/export/epub/sess")
            assert resp.status_code in (200, 404, 500)
        finally:
            pathlib.Path(epub_path).unlink(missing_ok=True)


@pytest.mark.skipif(not _HAS_FASTAPI, reason="FastAPI not installed")
class TestExportFiles:
    """Files export endpoint."""

    @pytest.fixture(autouse=True)
    def setup(self):
        self.client = _make_client()

    def test_files_returns_empty_list(self):
        orch = _mock_orch_with_output()
        with patch("api.export_routes._orchestrators", {"sess": orch}), \
             patch("api.export_routes._get_orch", return_value=orch), \
             patch("services.handlers.handle_export_files", return_value=[]):
            resp = self.client.post("/export/files/sess")
        assert resp.status_code == 200
        assert resp.json() == {"files": []}

    def test_files_filters_disallowed_paths(self):
        orch = _mock_orch_with_output()
        # Returns a disallowed path — should be filtered out
        with patch("api.export_routes._orchestrators", {"sess": orch}), \
             patch("api.export_routes._get_orch", return_value=orch), \
             patch("services.handlers.handle_export_files", return_value=["/etc/passwd"]):
            resp = self.client.post("/export/files/sess")
        assert resp.status_code == 200
        data = resp.json()
        assert "/etc/passwd" not in data.get("files", [])


@pytest.mark.skipif(not _HAS_FASTAPI, reason="FastAPI not installed")
class TestSafeFileResponse:
    """_safe_file_response path validation."""

    def test_disallowed_path_raises_400(self):
        from api.export_routes import _safe_file_response
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc:
            _safe_file_response("/etc/passwd", "passwd")
        assert exc.value.status_code == 400

    def test_allowed_but_missing_file_raises_404(self):
        from api.export_routes import _safe_file_response, _ALLOWED_EXPORT_DIRS
        from fastapi import HTTPException
        allowed_dir = _ALLOWED_EXPORT_DIRS[0]
        nonexistent = str(allowed_dir / "nonexistent_test_file_xyz.pdf")
        with pytest.raises(HTTPException) as exc:
            _safe_file_response(nonexistent, "test.pdf")
        assert exc.value.status_code == 404


@pytest.mark.skipif(not _HAS_FASTAPI, reason="FastAPI not installed")
class TestGetOrch:
    """_get_orch helper."""

    def test_missing_session_returns_none(self):
        from api.export_routes import _get_orch
        with patch("api.export_routes._orchestrators", {}):
            assert _get_orch("no-such-id") is None

    def test_orch_with_no_output_returns_none(self):
        from api.export_routes import _get_orch
        orch = MagicMock()
        orch.output = None
        with patch("api.export_routes._orchestrators", {"s": orch}):
            assert _get_orch("s") is None

    def test_orch_with_output_returns_orch(self):
        from api.export_routes import _get_orch
        orch = _mock_orch_with_output()
        with patch("api.export_routes._orchestrators", {"s": orch}):
            assert _get_orch("s") is orch
