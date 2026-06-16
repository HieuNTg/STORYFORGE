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
    override = (
        getattr(cfg.pipeline, "character_traits_cheap_model_override", "") or ""
    ).strip()
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
    # Optional story scope. When provided, avatars are written under
    # output/<story-slug>/images/avatars/ so two unrelated stories with the
    # same character name don't collide. Falls back to the legacy unscoped
    # path when omitted, so this is a backward-compatible additive change.
    story_id: str | None = Field(default=None, max_length=200)
    # Optional Vietnamese genre label (e.g. "Tiên Hiệp", "Khoa Huyễn"). Drives
    # the avatar prompt's style anchor so a sci-fi character doesn't come
    # back in hanfu. Unknown / empty falls back to a generic anime baseline.
    genre: str | None = Field(default=None, max_length=64)


# Strong references to in-flight background avatar tasks. Without this the event
# loop can garbage-collect a task that nothing awaits, killing avatar generation
# mid-flight. Tasks remove themselves on completion via add_done_callback.
_avatar_tasks: set[asyncio.Task] = set()


async def _generate_avatars_bg(
    characters: list[ForgeCharacter],
    story_id: str | None,
    genre: str | None,
) -> None:
    """Generate character portraits off the request path (see extract route).

    Best-effort: ``generate_character_avatar`` already swallows per-character
    failures and returns None; ``return_exceptions=True`` plus the outer guard
    make sure one bad portrait can't take down the rest or surface anywhere.
    """
    try:
        from services.character_avatar import generate_character_avatar

        # No story-level "setting" is passed in — leaking the story setting into
        # the avatar prompt triggered calligraphy/landscape backgrounds in Nano
        # Banana for wuxia stories. Avatars must be studio portraits regardless.
        await asyncio.gather(
            *(
                generate_character_avatar(c, story_id=story_id, genre=genre)
                for c in characters
            ),
            return_exceptions=True,
        )
    except Exception:  # noqa: BLE001
        logger.exception("background avatar generation failed")


@router.post(
    "/extract-story",
    response_model=list[ForgeCharacter],
    dependencies=[Depends(_rate_limit_dep)],
)
async def extract_story_characters_route(
    req: CharacterExtractRequest,
) -> list[ForgeCharacter]:
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
            asyncio.to_thread(
                llm.generate,
                system_prompt=system_prompt,
                user_prompt=prompt,
                model=model,
                temperature=0.7,
            ),
            timeout=45.0,
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

        # Avatar generation is intentionally fire-and-forget. FlowKit serializes
        # portraits (~25-30s each), so a 6-character extract would otherwise run
        # 2-3 minutes inline — long enough for the dev proxy / any reverse proxy
        # to reset the connection ("socket hang up" -> 500 Internal Server Error)
        # even though the LLM extraction itself finished in seconds. The portraits
        # are NOT part of the response: the client's character schema has no
        # `avatar` field and strips it on arrival; they exist only on disk to seed
        # the downstream illustration pipeline via find_existing_avatar(). So kick
        # them off in the background and return immediately. A strong reference is
        # held in _avatar_tasks until the task finishes so the loop can't GC it.
        task = asyncio.create_task(
            _generate_avatars_bg(characters, req.story_id, req.genre)
        )
        _avatar_tasks.add(task)
        task.add_done_callback(_avatar_tasks.discard)

        return characters
    except asyncio.TimeoutError:
        logger.warning("character extraction timeout")
        raise HTTPException(status_code=504, detail="character extraction timeout")
    except Exception as e:
        logger.exception("Failed to extract characters")
        raise HTTPException(
            status_code=500, detail=f"Failed to extract characters: {str(e)}"
        )


# --- Story-scoped avatar lookup + regeneration -----------------------------
#
# These endpoints deliberately do NOT touch the backend orchestrator store.
# Library stories are localStorage-only by product design, so the
# store-dependent /api/images/{id}/profiles + /rebuild endpoints always 404 for
# them. Avatars, however, live on disk under output/<story-slug>/images/avatars/
# (written by the extract-story background task) and are addressable purely from
# (character name + story_id). These routes surface those files to the
# Characters page so portraits display and "Tạo lại ảnh" works for any story,
# stored or not.


class AvatarLookupRequest(BaseModel):
    story_id: str | None = Field(default=None, max_length=200)
    # Character names to look up. Posted (not query params) so Vietnamese names
    # with diacritics don't need URL encoding and a 6-character story fits one
    # request.
    names: list[str] = Field(default_factory=list, max_length=64)


class AvatarLookupResponse(BaseModel):
    # name -> /media URL. Names without an on-disk avatar are simply omitted, so
    # the client can treat a missing key as "no portrait yet".
    avatars: dict[str, str] = Field(default_factory=dict)


class AvatarRegenerateRequest(BaseModel):
    character: ForgeCharacter
    story_id: str | None = Field(default=None, max_length=200)
    genre: str | None = Field(default=None, max_length=64)


class AvatarRegenerateResponse(BaseModel):
    name: str
    avatar_url: str | None = None


class AvatarBulkGenerateRequest(BaseModel):
    characters: list[ForgeCharacter] = Field(default_factory=list, max_length=64)
    story_id: str | None = Field(default=None, max_length=200)
    genre: str | None = Field(default=None, max_length=64)


class AvatarBulkGenerateResponse(BaseModel):
    # How many portraits were queued. The client polls /avatars/lookup to learn
    # when each file actually lands; this is just an accept-acknowledgement.
    accepted: int = 0


@router.post("/avatars/lookup", response_model=AvatarLookupResponse)
async def lookup_character_avatars(req: AvatarLookupRequest) -> AvatarLookupResponse:
    """Map character names to existing on-disk avatar URLs for a story.

    Pure filesystem lookup — no orchestrator store required, so it works for
    localStorage-only library stories. Cheap (a couple of ``stat`` calls per
    name) and read-only, hence no rate-limit dependency.
    """
    from services.character_avatar import avatar_url_for

    avatars: dict[str, str] = {}
    for name in req.names[:64]:
        url = avatar_url_for(name, req.story_id)
        if url:
            avatars[name] = url
    return AvatarLookupResponse(avatars=avatars)


@router.post(
    "/avatar",
    response_model=AvatarRegenerateResponse,
    dependencies=[Depends(_rate_limit_dep)],
)
async def regenerate_character_avatar_route(
    req: AvatarRegenerateRequest,
) -> AvatarRegenerateResponse:
    """Regenerate a single character portrait via FlowKit.

    Awaits inline: one portrait is ~25-30s (well under any proxy reset window,
    unlike the 6-portrait extract that had to be backgrounded), the user clicked
    a button with a spinner, and they expect the new face when it returns. Rate
    limited because each call hits the image backend.
    """
    from services.character_avatar import avatar_url_for, generate_character_avatar

    try:
        generated = await asyncio.wait_for(
            generate_character_avatar(
                req.character, story_id=req.story_id, genre=req.genre
            ),
            timeout=120.0,
        )
    except asyncio.TimeoutError:
        logger.warning("avatar regeneration timeout for %s", req.character.name)
        raise HTTPException(status_code=504, detail="avatar generation timeout")

    if not generated:
        # FlowKit disabled / project_id unset / upstream failed. Surface a clear
        # 502 instead of a 200 with a null URL so the client can toast properly.
        raise HTTPException(status_code=502, detail="avatar generation unavailable")

    # Re-resolve via avatar_url_for so the response carries the fresh ?v=<mtime>
    # cache-buster (generate_character_avatar returns the bare path).
    url = avatar_url_for(req.character.name, req.story_id) or generated
    return AvatarRegenerateResponse(name=req.character.name, avatar_url=url)


@router.post(
    "/avatars/generate",
    response_model=AvatarBulkGenerateResponse,
    dependencies=[Depends(_rate_limit_dep)],
)
async def generate_all_character_avatars_route(
    req: AvatarBulkGenerateRequest,
) -> AvatarBulkGenerateResponse:
    """Queue portrait generation for many characters at once (fire-and-forget).

    Same rationale as ``/extract-story``: FlowKit serializes portraits
    (~25-30s each), so generating N inline would run minutes and trip the dev
    proxy's reset window ("socket hang up"). So kick the whole batch off the
    request path via the shared ``_generate_avatars_bg`` helper and return
    immediately; the client polls ``/avatars/lookup`` until each new file lands.
    A strong reference is held in ``_avatar_tasks`` so the loop can't GC the task.
    """
    chars = req.characters[:64]
    if not chars:
        return AvatarBulkGenerateResponse(accepted=0)

    task = asyncio.create_task(_generate_avatars_bg(chars, req.story_id, req.genre))
    _avatar_tasks.add(task)
    task.add_done_callback(_avatar_tasks.discard)

    return AvatarBulkGenerateResponse(accepted=len(chars))


__all__ = ["router"]
