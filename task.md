# Tasks: FlowKit Integration for StoryForge

- `[/]` Create Chrome Extension Component
  - `[/]` `flowkit_extension/manifest.json`
  - `[/]` `flowkit_extension/background.js` (port updated to 7860, keep-alive, concurrent requests support)
  - `[/]` `flowkit_extension/content.js` (captcha resolver + active tab Toast alerts)
  - `[/]` `flowkit_extension/injected.js` (grecaptcha hooks)
  - `[/]` `flowkit_extension/popup.html`
  - `[/]` `flowkit_extension/popup.js`
- `[ ]` Create Backend API Component
  - `[ ]` `api/flowkit.py` (FastAPI router with WebSocket /ws/flowkit & Callback /api/ext/callback, background Veo polling task)
  - `[ ]` Register router in `app.py`
- `[ ]` Create Backend Service Component
  - `[ ]` `services/media/flow_service.py` (FlowService class + Job Queue SQLite3 + local image/video downloader saving under per-story path: `output/images/{story_slug}_{session_id}/`)
  - `[ ]` Modify `services/media/image_generator.py` (Support dynamic `output_dir` initialization, register provider, implement `_generate_flowkit`, map references to specific Style vs. Character roles, integrate Gemini Prompt Refiner)
  - `[ ]` Modify `services/media/image_provider.py` (Extend `is_configured` check)
- `[ ]` Verification
  - `[ ]` Create unit/mock tests in `tests/test_flowkit.py`
  - `[ ]` Perform manual integration check with local Chrome browser, confirming images and videos are grouped under `output/images/{story_slug}_{session_id}/`
