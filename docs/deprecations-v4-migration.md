# Deprecations & v4.0 Migration Guide

## Overview

StoryForge v4.0 removed browser-based authentication. Only API key auth is supported.

## REMOVED in v4.0: Browser-Based Authentication

**Status**: REMOVED as of v4.0

### What Was Removed

- `services.browser_auth` package (entire directory)
- `services.browser_auth.BrowserAuth` class
- `services.deepseek_web_client.DeepSeekWebClient` class
- `LLMConfig.backend_type` field
- `LLMConfig.web_auth_provider` field
- `LLMClient._is_web_backend()` method
- `LLMClient._get_web_client()` method
- `LLMClient._generate_web()` method
- Web UI tabs for browser login (Chrome automation)
- DeepSeek web API credential capture

### Migration Path

Use standard API key authentication:

**Before (removed)**:
```python
from services.browser_auth import BrowserAuth

auth = BrowserAuth()
auth.launch_chrome()
auth.capture_deepseek_credentials()
creds = auth.get_credentials()
```

**After (v4.0)**:
```python
import os

# Use environment variable
api_key = os.environ.get("STORYFORGE_API_KEY")

# Or store in config
from config import ConfigManager
cfg = ConfigManager()
api_key = cfg.llm.api_key
```

### How to Update Your Code

1. **Environment Setup**:
   ```bash
   export STORYFORGE_API_KEY="sk-your-api-key"
   export STORYFORGE_BASE_URL="https://api.openai.com/v1"
   export STORYFORGE_MODEL="gpt-4o"
   ```

2. **Remove BrowserAuth Calls**:
   - Delete calls to `BrowserAuth().launch_chrome()`
   - Delete calls to `BrowserAuth().capture_deepseek_credentials()`
   - Remove `backend_type = "web"` config entries
   - Remove browser login UI tabs

3. **Test API Key Auth**:
   ```bash
   curl -X POST https://api.openai.com/v1/chat/completions \
     -H "Authorization: Bearer $STORYFORGE_API_KEY" \
     -H "Content-Type: application/json" \
     -d '{"model":"gpt-4o","messages":[{"role":"user","content":"test"}]}'
   ```

## Supported Auth Methods (v4.0+)

- **API Key Auth** (required) — OpenAI, Gemini, Anthropic, OpenRouter, Ollama, custom endpoints

## FAQ

**Q: Can I keep using browser auth?**
No. The code has been removed. Migrate to API key auth.

**Q: What if I don't have an API key?**
- Use free APIs: Ollama (local), LM Studio
- Use free tiers: Google Gemini, OpenRouter, Anthropic
- Or request a cloud API key from your provider

## Timeline

| Version | Status | Details |
|---------|--------|---------|
| v3.0-3.x | Deprecated | Browser auth worked but emitted DeprecationWarning |
| v4.0 | **REMOVED** | Browser auth code completely removed |
