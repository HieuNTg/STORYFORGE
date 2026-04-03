# Deprecations & v4.0 Migration Guide

## Overview

StoryForge v4.0 (planned) will remove browser-based authentication and focus on API key auth for simplicity and security.

## Deprecated: Browser-Based Authentication

**Status**: Deprecated in v3.x, **will be removed in v4.0**

### What's Deprecated

- `services.browser_auth.BrowserAuth` class
- `services.deepseek_web_client.DeepSeekWebClient` class
- Web UI tabs for browser login (Chrome automation)
- DeepSeek web API credential capture

### Migration Path

Replace browser auth with standard API key authentication:

**Before (deprecated)**:
```python
from services.browser_auth import BrowserAuth

auth = BrowserAuth()  # DeprecationWarning
auth.launch_chrome()
auth.capture_deepseek_credentials()
creds = auth.get_credentials()
```

**After (v4.0 compatible)**:
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
   - Remove browser login UI tabs

3. **Test API Key Auth**:
   ```bash
   curl -X POST https://api.openai.com/v1/chat/completions \
     -H "Authorization: Bearer $STORYFORGE_API_KEY" \
     -H "Content-Type: application/json" \
     -d '{"model":"gpt-4o","messages":[{"role":"user","content":"test"}]}'
   ```

## Deprecation Warnings

When using deprecated features, you'll see:

```
DeprecationWarning: BrowserAuth is deprecated and will be removed in v4.0.
Use API key authentication instead (STORYFORGE_API_KEY env var).
```

```
DeprecationWarning: DeepSeekWebClient is deprecated.
Use standard API key authentication instead.
```

### In Settings Tab (ui/tabs/settings_tab.py)

The settings UI still supports browser auth but emits a deprecation warning via the helper function `_get_browser_auth()`:

```python
def _get_browser_auth():
    """Import BrowserAuth with deprecation warning. Raises on failure."""
    _log.warning(_DEPRECATION_MSG)
    from services.browser_auth import BrowserAuth
    return BrowserAuth()
```

The warning appears in logs whenever users attempt to use browser login.

## Timeline

| Version | Status | Details |
|---------|--------|---------|
| v3.0-3.x | Available | Browser auth works but emits DeprecationWarning |
| v4.0 | **Removal** | Browser auth code completely removed |

## Supported Auth Methods

**Currently supported** (v3.0+):
1. **API Key Auth** (recommended) — OpenAI, Gemini, Anthropic, OpenRouter, Ollama, custom endpoints
2. **Browser Auth** (deprecated in v3.x, removed in v4.0)

**v4.0 onwards**:
- API Key Auth only

## FAQ

**Q: Can I keep using browser auth in v4.0?**
No. The code will be removed. Plan migration now.

**Q: What if I don't have an API key?**
- Use free APIs: Ollama (local), LM Studio
- Use free tiers: Google Gemini, OpenRouter, Anthropic
- Or request a cloud API key from your provider

**Q: How do I suppress the deprecation warning?**
Python warnings can be filtered (not recommended for production):
```python
import warnings
warnings.filterwarnings("ignore", category=DeprecationWarning)
```

But you should migrate instead.

**Q: When exactly is v4.0 released?**
Check [GitHub Releases](https://github.com/HieuNTg/STORYFORGE/releases) for the v4.0 release date.
