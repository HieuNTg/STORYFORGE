"""MCP (Model Context Protocol) Server for StoryForge — stdin/stdout JSON-RPC transport.

This server exposes StoryForge pipeline capabilities as MCP tools that can be
called by Claude Desktop or any MCP-compatible client.

HOW TO TEST WITH CLAUDE DESKTOP
--------------------------------
1. Install Claude Desktop: https://claude.ai/download
2. Open Claude Desktop config:
   - macOS: ~/Library/Application Support/Claude/claude_desktop_config.json
   - Windows: %APPDATA%/Claude/claude_desktop_config.json
3. Add this server entry:
   {
     "mcpServers": {
       "storyforge": {
         "command": "python",
         "args": ["/absolute/path/to/mcp_server.py"],
         "env": {"STORYFORGE_API_KEY": "your-key"}
       }
     }
   }
4. Restart Claude Desktop — "storyforge" tools will appear in the tool picker.
5. Try: "Use storyforge to generate a 3-chapter romance story about two rivals."

MANUAL TEST (no Claude Desktop needed)
----------------------------------------
echo '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"0.1"}}}' | python mcp_server.py
"""

import json
import os
import sys
import uuid
import logging
from typing import Any

logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s %(levelname)s %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Graceful redis import
# ---------------------------------------------------------------------------
try:
    import redis as _redis_lib
    _REDIS_AVAILABLE = True
except ImportError:
    _redis_lib = None  # type: ignore[assignment]
    _REDIS_AVAILABLE = False

# ---------------------------------------------------------------------------
# Job store — Redis-backed when REDIS_URL is set, else in-memory dict
# ---------------------------------------------------------------------------
_REDIS_URL = os.environ.get("REDIS_URL", "").strip()
_JOB_TTL = 86400  # 24 hours
_JOB_PREFIX = "mcp_job:"

_jobs: dict[str, dict] = {}  # fallback in-memory store
_redis_client = None

if _REDIS_URL and _REDIS_AVAILABLE:
    try:
        _redis_client = _redis_lib.from_url(_REDIS_URL, decode_responses=True)
        _redis_client.ping()
        logger.warning("MCP job store: Redis connected (%s)", _REDIS_URL.split("@")[-1])
    except Exception as _e:
        logger.warning("MCP job store: Redis unavailable (%s), using in-memory fallback.", _e)
        _redis_client = None


def _get_job(job_id: str) -> "dict | None":
    """Retrieve job data by id."""
    if _redis_client is not None:
        try:
            raw = _redis_client.get(f"{_JOB_PREFIX}{job_id}")
            if raw:
                return json.loads(raw)
            return None
        except Exception as e:
            logger.warning("Redis get_job error: %s", e)
            return _jobs.get(job_id)
    return _jobs.get(job_id)


def _set_job(job_id: str, data: dict) -> None:
    """Persist job data."""
    if _redis_client is not None:
        try:
            _redis_client.setex(
                f"{_JOB_PREFIX}{job_id}", _JOB_TTL, json.dumps(data, ensure_ascii=False)
            )
            return
        except Exception as e:
            logger.warning("Redis set_job error: %s", e)
    _jobs[job_id] = data

# ---------------------------------------------------------------------------
# Genre list (mirrors pipeline_routes._genre_keys without i18n dependency)
# ---------------------------------------------------------------------------
GENRES = [
    "Tiên Hiệp", "Huyền Huyễn", "Kiếm Hiệp", "Đô Thị",
    "Ngôn Tình", "Xuyên Không", "Trọng Sinh", "Hệ Thống",
    "Khoa Huyễn", "Đồng Nhân", "Lịch Sử", "Quân Sự",
    "Linh Dị", "Trinh Thám", "Hài Hước", "Vong Du",
    "Dị Giới", "Mạt Thế", "Điền Văn", "Cung Đấu",
]

# ---------------------------------------------------------------------------
# MCP tool definitions
# ---------------------------------------------------------------------------
TOOLS = [
    {
        "name": "generate_story",
        "description": (
            "Start an async StoryForge pipeline job. "
            "Returns a story_id to track progress with get_story_status."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "genre": {
                    "type": "string",
                    "description": f"Story genre. One of: {', '.join(GENRES[:8])}... (use list_genres for full list)",
                },
                "num_chapters": {
                    "type": "integer",
                    "description": "Number of chapters to generate (1-20 recommended for POC).",
                    "default": 5,
                },
                "language": {
                    "type": "string",
                    "description": "Output language: 'vi' for Vietnamese, 'en' for English.",
                    "default": "vi",
                },
                "idea": {
                    "type": "string",
                    "description": "One-sentence story premise.",
                    "default": "",
                },
                "title": {
                    "type": "string",
                    "description": "Story title (optional — auto-generated if empty).",
                    "default": "",
                },
            },
            "required": ["genre"],
        },
    },
    {
        "name": "get_story_status",
        "description": "Check the status and progress of a previously started story job.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "story_id": {
                    "type": "string",
                    "description": "The story_id returned by generate_story.",
                }
            },
            "required": ["story_id"],
        },
    },
    {
        "name": "list_genres",
        "description": "Return all available story genres supported by StoryForge.",
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
    },
]

# ---------------------------------------------------------------------------
# Tool handlers
# ---------------------------------------------------------------------------

def _handle_generate_story(args: dict) -> dict:
    """Queue a pipeline job and return a story_id."""
    genre = args.get("genre", "Tiên Hiệp")
    num_chapters = int(args.get("num_chapters", 5))
    language = args.get("language", "vi")
    idea = args.get("idea", "")
    title = args.get("title", "")

    story_id = str(uuid.uuid4())
    initial_data = {
        "story_id": story_id,
        "status": "queued",
        "progress": 0.0,
        "genre": genre,
        "num_chapters": num_chapters,
        "language": language,
        "logs": [],
    }
    _set_job(story_id, initial_data)

    # NOTE: Full pipeline runs are blocking and take minutes.
    # In production, spawn a background thread/worker here.
    # For this POC we return immediately with "queued" status.
    try:
        import threading
        from pipeline.orchestrator import PipelineOrchestrator
        from config import ConfigManager

        def _run():
            try:
                job = _get_job(story_id) or {}
                job["status"] = "running"
                _set_job(story_id, job)

                cfg = ConfigManager()
                cfg.pipeline.language = language
                orch = PipelineOrchestrator()

                def _progress(msg):
                    j = _get_job(story_id) or {}
                    j.setdefault("logs", []).append(msg)
                    if "Layer 1 hoan tat" in msg or "Layer 1 hoàn tất" in msg:
                        j["progress"] = 0.33
                    elif "Layer 2 hoan tat" in msg or "Layer 2 hoàn tất" in msg:
                        j["progress"] = 0.66
                    elif "PIPELINE HOAN TAT" in msg or "PIPELINE HOÀN TẤT" in msg:
                        j["progress"] = 1.0
                    _set_job(story_id, j)

                out = orch.run_full_pipeline(
                    title=title or f"{genre} Story",
                    genre=genre,
                    idea=idea or f"Một câu chuyện {genre} hấp dẫn",
                    num_chapters=num_chapters,
                    progress_callback=_progress,
                    enable_media=False,
                )
                job = _get_job(story_id) or {}
                job["status"] = out.status
                job["progress"] = 1.0
                if out.enhanced_story:
                    job["chapter_count"] = len(out.enhanced_story.chapters)
                _set_job(story_id, job)
            except Exception as e:
                job = _get_job(story_id) or {}
                job["status"] = "error"
                job["error"] = str(e)
                _set_job(story_id, job)
                logger.exception("Pipeline error in MCP job %s", story_id)

        t = threading.Thread(target=_run, daemon=True)
        t.start()
    except ImportError as e:
        job = _get_job(story_id) or {}
        job["status"] = "error"
        job["error"] = f"Pipeline unavailable: {e}"
        _set_job(story_id, job)

    current = _get_job(story_id) or initial_data
    return {
        "story_id": story_id,
        "status": current.get("status", "queued"),
        "message": "Job queued. Call get_story_status(story_id) to track progress.",
    }


def _handle_get_story_status(args: dict) -> dict:
    story_id = args.get("story_id", "")
    job = _get_job(story_id)
    if job is None:
        return {"error": f"Unknown story_id: {story_id}"}
    job = dict(job)
    job["logs"] = job.get("logs", [])[-10:]  # last 10 log lines
    return job


def _handle_list_genres(_args: dict) -> dict:
    return {"genres": GENRES, "count": len(GENRES)}


_TOOL_HANDLERS = {
    "generate_story": _handle_generate_story,
    "get_story_status": _handle_get_story_status,
    "list_genres": _handle_list_genres,
}

# ---------------------------------------------------------------------------
# JSON-RPC / MCP protocol
# ---------------------------------------------------------------------------

def _send(obj: Any) -> None:
    sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def _error(code: int, message: str, req_id=None) -> dict:
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}


def _handle_request(req: dict) -> dict | None:
    method = req.get("method", "")
    req_id = req.get("id")
    params = req.get("params", {})

    if method == "initialize":
        return {
            "jsonrpc": "2.0", "id": req_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "storyforge-mcp", "version": "0.1.0"},
            },
        }

    if method == "notifications/initialized":
        return None  # notification, no response

    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": req_id, "result": {"tools": TOOLS}}

    if method == "tools/call":
        tool_name = params.get("name", "")
        tool_args = params.get("arguments", {})
        handler = _TOOL_HANDLERS.get(tool_name)
        if not handler:
            return _error(-32601, f"Unknown tool: {tool_name}", req_id)
        try:
            result = handler(tool_args)
            return {
                "jsonrpc": "2.0", "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}],
                    "isError": "error" in result,
                },
            }
        except Exception as e:
            logger.exception("Tool %s error", tool_name)
            return _error(-32603, str(e), req_id)

    if method == "ping":
        return {"jsonrpc": "2.0", "id": req_id, "result": {}}

    return _error(-32601, f"Method not found: {method}", req_id)


def main() -> None:
    for raw_line in sys.stdin:
        raw_line = raw_line.strip()
        if not raw_line:
            continue
        try:
            req = json.loads(raw_line)
        except json.JSONDecodeError as e:
            _send(_error(-32700, f"Parse error: {e}"))
            continue
        try:
            response = _handle_request(req)
            if response is not None:
                _send(response)
        except Exception as e:
            logger.exception("Unhandled error")
            _send(_error(-32603, str(e), req.get("id")))


if __name__ == "__main__":
    main()
