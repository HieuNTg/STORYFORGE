"""Tests for ReplicateIPAdapter client."""
import os
import base64
import pytest
from unittest.mock import patch, MagicMock, call
from services.replicate_ip_adapter import ReplicateIPAdapter


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def adapter(tmp_path):
    """Adapter with dummy api_key and output_dir pointing to tmp_path."""
    with patch("services.replicate_ip_adapter.ConfigManager") as mock_cm:
        mock_cm.return_value.pipeline.replicate_api_key = ""
        a = ReplicateIPAdapter(api_key="test-key")
    a.output_dir = str(tmp_path)
    return a


@pytest.fixture()
def ref_image(tmp_path):
    """Create a minimal PNG reference image file."""
    path = tmp_path / "reference.png"
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 20)
    return str(path)


def _make_prediction_response(poll_url="https://api.replicate.com/v1/predictions/abc"):
    resp = MagicMock()
    resp.json.return_value = {
        "id": "abc",
        "status": "starting",
        "urls": {"get": poll_url},
    }
    resp.raise_for_status = MagicMock()
    return resp


def _make_poll_response(status="succeeded", output=None, error=None):
    resp = MagicMock()
    data = {"status": status}
    if output is not None:
        data["output"] = output
    if error is not None:
        data["error"] = error
    resp.json.return_value = data
    resp.raise_for_status = MagicMock()
    return resp


def _make_image_download_response(content=b"IMGDATA"):
    resp = MagicMock()
    resp.content = content
    resp.raise_for_status = MagicMock()
    return resp


# ---------------------------------------------------------------------------
# is_configured
# ---------------------------------------------------------------------------

def test_is_configured_with_key():
    with patch("services.replicate_ip_adapter.ConfigManager") as mock_cm:
        mock_cm.return_value.pipeline.replicate_api_key = ""
        a = ReplicateIPAdapter(api_key="somekey")
    assert a.is_configured() is True


def test_is_configured_without_key():
    a = ReplicateIPAdapter(api_key="test")
    a.api_key = ""
    assert a.is_configured() is False


# ---------------------------------------------------------------------------
# generate — missing reference image
# ---------------------------------------------------------------------------

def test_generate_missing_reference_image(adapter, tmp_path):
    result = adapter.generate("a scene", "/nonexistent/path/ref.png")
    assert result is None


# ---------------------------------------------------------------------------
# generate — not configured (no api_key)
# ---------------------------------------------------------------------------

def test_generate_not_configured(tmp_path, ref_image):
    with patch("services.replicate_ip_adapter.ConfigManager") as mock_cm:
        mock_cm.return_value.pipeline.replicate_api_key = ""
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("REPLICATE_API_KEY", None)
            a = ReplicateIPAdapter(api_key="")
    a.output_dir = str(tmp_path)
    result = a.generate("prompt", ref_image)
    assert result is None


# ---------------------------------------------------------------------------
# generate — successful flow (list output)
# ---------------------------------------------------------------------------

def test_generate_success_list_output(adapter, ref_image, tmp_path):
    pred_resp = _make_prediction_response()
    poll_resp = _make_poll_response(status="succeeded", output=["https://cdn.replicate.com/img.png"])
    img_resp = _make_image_download_response(b"IMAGEDATA")

    with patch("services.replicate_ip_adapter.requests.post", return_value=pred_resp), \
         patch("services.replicate_ip_adapter.requests.get", side_effect=[poll_resp, img_resp]), \
         patch("services.replicate_ip_adapter.time.sleep"):
        result = adapter.generate("a scene", ref_image, filename="out.png")

    assert result is not None
    assert result.endswith("out.png")
    assert os.path.exists(result)
    assert open(result, "rb").read() == b"IMAGEDATA"


# ---------------------------------------------------------------------------
# generate — successful flow (string output)
# ---------------------------------------------------------------------------

def test_generate_success_string_output(adapter, ref_image, tmp_path):
    pred_resp = _make_prediction_response()
    poll_resp = _make_poll_response(status="succeeded", output="https://cdn.replicate.com/img.png")
    img_resp = _make_image_download_response(b"STRDATA")

    with patch("services.replicate_ip_adapter.requests.post", return_value=pred_resp), \
         patch("services.replicate_ip_adapter.requests.get", side_effect=[poll_resp, img_resp]), \
         patch("services.replicate_ip_adapter.time.sleep"):
        result = adapter.generate("prompt", ref_image, filename="str_out.png")

    assert result is not None
    assert os.path.exists(result)


# ---------------------------------------------------------------------------
# generate — Replicate failure status
# ---------------------------------------------------------------------------

def test_generate_failed_status(adapter, ref_image):
    pred_resp = _make_prediction_response()
    poll_resp = _make_poll_response(status="failed", error="out of memory")

    with patch("services.replicate_ip_adapter.requests.post", return_value=pred_resp), \
         patch("services.replicate_ip_adapter.requests.get", return_value=poll_resp), \
         patch("services.replicate_ip_adapter.time.sleep"):
        result = adapter.generate("prompt", ref_image)

    assert result is None


# ---------------------------------------------------------------------------
# generate — no poll URL in response
# ---------------------------------------------------------------------------

def test_generate_no_poll_url(adapter, ref_image):
    pred_resp = MagicMock()
    pred_resp.json.return_value = {"id": "abc", "status": "starting", "urls": {}}
    pred_resp.raise_for_status = MagicMock()

    with patch("services.replicate_ip_adapter.requests.post", return_value=pred_resp):
        result = adapter.generate("prompt", ref_image)

    assert result is None


# ---------------------------------------------------------------------------
# generate — timeout
# ---------------------------------------------------------------------------

def test_generate_timeout(adapter, ref_image):
    pred_resp = _make_prediction_response()
    # Always return "processing" to force timeout
    poll_resp = _make_poll_response(status="processing")

    # Patch time so loop expires immediately
    with patch("services.replicate_ip_adapter.requests.post", return_value=pred_resp), \
         patch("services.replicate_ip_adapter.requests.get", return_value=poll_resp), \
         patch("services.replicate_ip_adapter.time.sleep"), \
         patch("services.replicate_ip_adapter.time.time", side_effect=[0, 200, 200]):
        result = adapter.generate("prompt", ref_image, timeout=120)

    assert result is None


# ---------------------------------------------------------------------------
# generate — unexpected output format (not list/str)
# ---------------------------------------------------------------------------

def test_generate_unexpected_output_format(adapter, ref_image):
    pred_resp = _make_prediction_response()
    poll_resp = _make_poll_response(status="succeeded", output={"url": "..."})

    with patch("services.replicate_ip_adapter.requests.post", return_value=pred_resp), \
         patch("services.replicate_ip_adapter.requests.get", return_value=poll_resp), \
         patch("services.replicate_ip_adapter.time.sleep"):
        result = adapter.generate("prompt", ref_image)

    assert result is None


# ---------------------------------------------------------------------------
# generate — requests exception
# ---------------------------------------------------------------------------

def test_generate_request_exception(adapter, ref_image):
    with patch("services.replicate_ip_adapter.requests.post", side_effect=Exception("network error")):
        result = adapter.generate("prompt", ref_image)

    assert result is None
