"""Character generation routes — fast synchronous BFF over cheap_model.

Endpoints
---------
- ``POST /api/characters/generate`` — sync; returns ForgeCharacter JSON.

Behavior:
- Returns 404 when ``PipelineConfig.enable_character_traits`` is False.
- Rate-limited 10 req/min/IP (in-memory or Redis), separate bucket from forge.
- Mocked-LLM-testable via ``_get_llm`` indirection (same pattern as forge_routes).
"""

from __future__ import annotations

import asyncio
import logging
import os
import threading
import time

from fastapi import APIRouter, Depends, HTTPException, Request

from config import ConfigManager
from models.schemas import CharacterGenerateRequest, ForgeCharacter
from pydantic import Field, BaseModel
from services.character_service import generate_character

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/characters", tags=["characters"])


CHARACTER_LIMIT_PER_MIN = int(os.environ.get("STORYFORGE_CHARACTER_RATE_LIMIT", "10"))
_CHARACTER_WINDOW = 60.0

_character_lock = threading.Lock()
_character_state: dict[str, list[float]] = {}


def _client_ip(request: Request) -> str:
    """Resolve client IP, honoring X-Forwarded-For only from trusted proxies."""
    try:
        from middleware.rate_limiter import _get_ip  # type: ignore

        return _get_ip(request)
    except Exception:  # noqa: BLE001
        return request.client.host if request.client else "unknown"


def _check_character_rate(ip: str) -> bool:
    """True if request is allowed under N/min/IP. Sliding window per IP."""
    if os.environ.get("REDIS_URL"):
        try:
            from middleware.rate_limiter import _get_redis  # type: ignore
            r = _get_redis()
            if r is not None:
                key = f"sf:ratelimit:character:{ip}"
                count = r.incr(key)
                if count == 1:
                    r.expire(key, int(_CHARACTER_WINDOW))
                return int(count) <= CHARACTER_LIMIT_PER_MIN
        except Exception as e:  # noqa: BLE001
            logger.debug("character rate redis path failed: %s", e)

    now = time.monotonic()
    with _character_lock:
        bucket = _character_state.setdefault(ip, [])
        cutoff = now - _CHARACTER_WINDOW
        i = 0
        while i < len(bucket) and bucket[i] < cutoff:
            i += 1
        if i:
            del bucket[:i]
        if len(bucket) >= CHARACTER_LIMIT_PER_MIN:
            return False
        bucket.append(now)
        return True


def _ensure_enabled() -> None:
    cfg = ConfigManager()
    if not getattr(cfg.pipeline, "enable_character_traits", False):
        raise HTTPException(status_code=404, detail="character endpoint disabled")


def _rate_limit_dep(request: Request) -> None:
    ip = _client_ip(request)
    if not _check_character_rate(ip):
        raise HTTPException(
            status_code=429,
            detail=f"character rate limit exceeded ({CHARACTER_LIMIT_PER_MIN}/min)",
        )


def _get_llm():
    """Lazy import + return the LLMClient singleton. Tests monkey-patch this."""
    from services.llm_client import LLMClient
    return LLMClient()


def _resolve_model() -> str | None:
    cfg = ConfigManager()
    override = (getattr(cfg.pipeline, "character_traits_cheap_model_override", "") or "").strip()
    if override:
        return override
    cheap = (getattr(cfg.llm, "cheap_model", "") or "").strip()
    return cheap or None


@router.post(
    "/generate",
    response_model=ForgeCharacter,
    dependencies=[Depends(_rate_limit_dep)],
)
async def generate_character_route(
    req: CharacterGenerateRequest,
    _enabled: None = Depends(_ensure_enabled),
) -> ForgeCharacter:
    """Synchronous character generation. Runs the (sync) LLM call in a threadpool."""
    llm = _get_llm()
    model = _resolve_model()
    try:
        result = await asyncio.wait_for(
            asyncio.to_thread(
                generate_character,
                llm,
                req.name,
                req.role,
                req.genre,
                req.extraContext,
                model,
                req.language or "vi",
            ),
            timeout=30.0,
        )
        return result
    except asyncio.TimeoutError:
        logger.warning("character generation timeout for name=%s", req.name)
        raise HTTPException(status_code=504, detail="character generation timeout")
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        logger.exception("generate_character_route failed")
        raise HTTPException(
            status_code=502,
            detail=f"character generation failed: {type(e).__name__}",
        )



class CharacterExtractRequest(BaseModel):
    title: str = Field(..., max_length=200)
    description: str = Field("", max_length=2000)
    setting: str = Field("", max_length=2000)
    text_context: str = Field(..., min_length=50, max_length=50000)
    # Source story language (e.g. "vi", "en"). Drives the language of every
    # text field on extracted characters. Defaults to Vietnamese.
    language: str = Field(default="vi", max_length=16)

@router.post("/extract-story", response_model=list[ForgeCharacter])
async def extract_story_characters_route(req: CharacterExtractRequest) -> list[ForgeCharacter]:
    llm = _get_llm()
    model = _resolve_model()

    # Pin output language: the source story's language must drive every text
    # field on the extracted characters (description, backstory, secret,
    # conflict). Without this, English-leaning base models can drift to
    # English even when the input is Vietnamese.
    from services.character_service import _language_label
    language_label = _language_label(req.language)

    prompt = f"""
LANGUAGE (CRITICAL): Respond ENTIRELY in {language_label}. Every string value
in the JSON output — name (when not a proper noun already in the source),
description, backstory, secret, conflict — MUST be written in {language_label}.
Do NOT mix languages. Character names follow project conventions: Vietnamese
names by default; Han-Viet / Chinese romanization ONLY for Tiên Hiệp (xianxia)
/ Wuxia genres.

Trích xuất danh sách nhân vật từ nội dung truyện dưới đây.
Trả về danh sách 1-6 nhân vật chính và phụ quan trọng nhất. KHÔNG bịa tên nhân vật nếu không có trong văn bản.

Thông tin truyện:
- Tên truyện: {req.title}
- Tóm tắt: {req.description}
- Bối cảnh: {req.setting}

Nội dung các chương:
{req.text_context[:10000]}

Định dạng trả về là JSON hợp lệ, tuân thủ CẤU TRÚC CHÍNH XÁC SAU ĐÂY:
[
  {{
    "name": "Tên nhân vật",
    "role": "protagonist",
    "traits": {{
      "strength": 50,
      "wisdom": 50,
      "agility": 50,
      "scheme": 50
    }},
    "description": "Mô tả ngắn gọn về nhân vật",
    "backstory": "Tiểu sử nhân vật",
    "secret": "Bí mật hoặc ẩn ý của nhân vật",
    "conflict": "Mâu thuẫn chính của nhân vật"
  }}
]
Vai trò (role) phải là một trong: protagonist, antagonist, rival, supporting.

REMINDER: All description / backstory / secret / conflict text MUST be in {language_label}.
"""
    system_prompt = (
        f"You are an assistant that extracts character information from a story. "
        f"Return ONLY valid JSON. LANGUAGE: every text field in the output must "
        f"be written in {language_label}. Do not mix languages."
    )
    try:
        raw_json = await asyncio.wait_for(
            asyncio.to_thread(llm.generate, system_prompt=system_prompt, user_prompt=prompt, model=model, temperature=0.7),
            timeout=45.0
        )
        if "```json" in raw_json:
            raw_json = raw_json.split("```json")[1].split("```")[0].strip()
        elif "```" in raw_json:
            raw_json = raw_json.split("```")[1].strip()

        import json
        data = json.loads(raw_json)
        if not isinstance(data, list):
            data = [data]

        characters = []
        for item in data[:6]:
            char = ForgeCharacter(**item)
            characters.append(char)

        return characters
    except asyncio.TimeoutError:
        logger.warning("character extraction timeout")
        raise HTTPException(status_code=504, detail="character extraction timeout")
    except Exception as e:
        logger.exception("Failed to extract characters")
        raise HTTPException(status_code=500, detail=f"Failed to extract characters: {str(e)}")

__all__ = ["router"]
