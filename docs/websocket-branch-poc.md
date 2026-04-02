# WebSocket vs SSE — Branch Reader POC Analysis

**Date:** 2026-04-02

## Current SSE Implementation

`api/pipeline_routes.py` uses FastAPI `StreamingResponse` with `media_type="text/event-stream"` at three endpoints:
- `POST /pipeline/run` — streams Layer 1-3 progress logs and quality scores
- `POST /pipeline/resume` — same pattern for checkpoint-resumed runs
- Branch reader — streams chapter text chunks as SSE frames

Pattern:
```python
async def event_generator():
    while not done:
        msg = await queue.get()   # thread-safe queue fed by pipeline thread
        yield f"data: {json.dumps(msg)}\n\n"
return StreamingResponse(event_generator(), media_type="text/event-stream")
```

## Benchmark Comparison (Theoretical)

| Metric | SSE | WebSocket |
|--------|-----|-----------|
| Protocol overhead per frame | ~50 bytes (`data:…\n\n`) | ~2–10 bytes (WS header) |
| Client auto-reconnect | Yes (EventSource API) | Manual — client must reconnect |
| Proxy/CDN compatibility | Excellent (plain HTTP/1.1) | Varies — some proxies need config |
| Bidirectional | No | Yes |
| Interactive branch choice mid-stream | Not possible — new HTTP request | Native — send choice on open socket |
| Implementation complexity | Low | Medium |
| Memory per connection | Low | Low |

## Analysis

**Pipeline streaming:** SSE is optimal. Runs are fire-and-forget; no client input needed. Auto-reconnect is critical for 2–15 minute jobs. Nginx/Cloudflare work out of the box.

**Branch reader:** WebSocket wins. Each branch choice with SSE costs ~200ms handshake overhead. WebSocket clients send `{"action":"choose","branch":2}` on the open socket instantly.

## Recommendation

Keep SSE for all pipeline streaming. Add WebSocket **only** for the branch reader endpoint.

## Implementation Sketch

```python
# api/branch_ws.py
@router.websocket("/ws/branch/{story_id}")
async def branch_ws(ws: WebSocket, story_id: str):
    await ws.accept()
    narrator = BranchNarrator(load_story(story_id))
    await ws.send_json({"type": "chunk", "text": narrator.intro()})
    while True:
        msg = await ws.receive_json()
        if msg["action"] == "choose":
            async for chunk in narrator.stream_branch(msg["branch"]):
                await ws.send_json({"type": "chunk", "text": chunk})
            await ws.send_json({"type": "choices", "options": narrator.next_choices()})
        elif msg["action"] == "restart":
            narrator.reset()
```
