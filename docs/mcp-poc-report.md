# MCP Server POC Report — StoryForge

**Date:** 2026-04-02
**Status:** Proof-of-concept implemented

## What Was Implemented

`mcp_server.py` at project root exposes StoryForge via the Model Context Protocol using stdin/stdout JSON-RPC transport (MCP 2024-11-05 spec).

### Tools Exposed

| Tool | Inputs | Output |
|------|--------|--------|
| `generate_story` | genre, num_chapters, language, idea, title | story_id + queued status |
| `get_story_status` | story_id | progress (0-1), status, last 10 log lines |
| `list_genres` | — | all 20 genres from pipeline_routes |

### Architecture

- Pure stdin/stdout — no HTTP server, no dependencies beyond Python stdlib + optional pipeline
- Background threading: pipeline runs in daemon thread; MCP call returns immediately with `story_id`
- In-memory job store (`_jobs` dict) — sufficient for POC, single-process only

## How to Test

**With Claude Desktop:**
```json
{
  "mcpServers": {
    "storyforge": {
      "command": "python",
      "args": ["/path/to/mcp_server.py"],
      "env": {"STORYFORGE_API_KEY": "your-key"}
    }
  }
}
```
Then ask Claude: "List StoryForge genres" or "Generate a 3-chapter romance story."

**Manual (command line):**
```bash
echo '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"0.1"}}}' | python mcp_server.py
echo '{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}' | python mcp_server.py
```

## Limitations

1. **Job persistence** — `_jobs` dict is lost on restart; needs Redis or SQLite for production
2. **No cancellation** — background thread runs to completion; no kill mechanism
3. **Blocking pipeline** — `run_full_pipeline` is CPU/IO heavy; worker queue (Celery/RQ) needed at scale
4. **No auth** — any MCP client can trigger generation; add token check before production use
5. **Single process** — multi-worker deploys (Gunicorn) will have separate job dicts

## Next Steps

- Replace `_jobs` dict with SQLite-backed job store (`services/job_store.py`)
- Add `/mcp` HTTP endpoint alternative (for remote MCP clients over SSE)
- Expose `export_story` tool (PDF/EPUB download URL)
- Add streaming progress via MCP notifications (server-sent events over stdio)
- Package as `storyforge-mcp` PyPI entry point for one-command install
