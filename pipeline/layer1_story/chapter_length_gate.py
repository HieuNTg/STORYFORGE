"""Length gate: expand a chapter that came back materially under target.

Why this exists
---------------
`word_count` reaches the model as one soft bullet among a dozen others
("- Viết chương N đầy đủ, khoảng {word_count} từ"), and nothing downstream ever
compared the produced chapter against it — `count_words()` only recorded the
result. Measured on a 10-chapter run with a 2000-word target: min 884, mean
1450, max 1895, and 9 of 10 chapters ended on a complete sentence. So the model
was not being truncated by `max_tokens` (8192, roughly double what the target
needs); it simply stopped early, and raising the token ceiling could not help.

The gate closes that loop: measure, and if the chapter is materially short, ask
for one targeted expansion. The prompt asks for added *substance* — scene beats,
dialogue, interiority — because padding an existing draft to hit a number reads
worse than the short version it replaced.

Deliberately conservative:
  * one attempt, never a loop;
  * the expansion must actually be longer than the original AND at least as long
    as the model's first attempt, otherwise the original is kept;
  * every failure path is non-fatal and returns the chapter untouched.
"""

import logging

logger = logging.getLogger(__name__)

# Below this fraction of the requested length a chapter is treated as short.
# 0.85 leaves room for the natural variance of prose while still catching the
# 884/2000 (44%) cases that motivated this gate.
_DEFAULT_MIN_RATIO = 0.85

EXPAND_CHAPTER = """\
{user_story_idea_header}Bạn là nhà văn chuyên nghiệp. Chương dưới đây ĐẠT CHẤT LƯỢNG nhưng CHƯA ĐỦ ĐỘ DÀI.

Độ dài hiện tại: {current_words} từ.
Độ dài yêu cầu: {target_words} từ (cần bổ sung khoảng {missing_words} từ).

## Nhiệm vụ
Viết lại chương ĐẦY ĐỦ, giữ NGUYÊN cốt truyện, thứ tự sự kiện và kết chương.
Bổ sung độ dài bằng CHẤT LIỆU THẬT, không kéo dài lê thê:
- Khai triển các cảnh đang bị tóm tắt vội thành cảnh diễn ra trực tiếp
- Thêm đối thoại bộc lộ tính cách và đẩy tình tiết
- Thêm nội tâm, phản ứng cơ thể, cảm giác giác quan tại các khoảnh khắc quan trọng
- Làm dày bối cảnh ở nơi người đọc cần hình dung

## TUYỆT ĐỐI KHÔNG
- Không thêm sự kiện mới làm lệch cốt truyện
- Không lặp lại ý đã viết bằng cách diễn đạt khác
- Không thêm lời dẫn/meta ("Dưới đây là...", "Phiên bản mở rộng...")
- Không đổi kết chương

Chỉ trả về văn xuôi của chương đã mở rộng, viết hoàn toàn bằng tiếng Việt.

## CHƯƠNG HIỆN TẠI
{content}
"""


def expand_chapter_if_short(
    pipeline_config,
    llm,
    chapter,
    outline,
    word_count: int,
    layer_model: str | None = None,
    progress_callback=None,
    draft=None,
) -> None:
    """Expand `chapter` in place when it is materially under `word_count`.

    No-op unless `enable_length_gate` is set (defaults on). Never raises.
    """
    if not getattr(pipeline_config, "enable_length_gate", True):
        return
    if not word_count or word_count <= 0:
        return

    try:
        from models.schemas import count_words

        content = getattr(chapter, "content", "") or ""
        if not content:
            return

        current = count_words(content)
        ratio = float(
            getattr(pipeline_config, "length_gate_min_ratio", _DEFAULT_MIN_RATIO)
        )
        floor = int(word_count * ratio)
        if current >= floor:
            return

        ch_num = getattr(outline, "chapter_number", "?")
        logger.info(
            "Ch%s length gate: %d/%d words (%.0f%% of target) - expanding",
            ch_num,
            current,
            word_count,
            100.0 * current / word_count,
        )
        if progress_callback:
            progress_callback(
                f"Ch{ch_num}: {current}/{word_count} từ — đang viết bổ sung..."
            )

        from services.text_utils import build_idea_header
        from pipeline.layer1_story.chapter_self_critique import strip_llm_preamble

        _idea = getattr(draft, "original_idea", "") or "" if draft is not None else ""
        _idea_sum = (
            getattr(draft, "idea_summary_for_chapters", "") or ""
            if draft is not None
            else ""
        )
        idea_header = build_idea_header(_idea, _idea_sum) if _idea else ""

        expanded = llm.generate(
            system_prompt=(
                "Bạn là nhà văn. Chỉ trả về văn xuôi của chương đã mở rộng, "
                "không thêm bất kỳ lời dẫn nào."
            ),
            user_prompt=EXPAND_CHAPTER.format(
                user_story_idea_header=idea_header,
                current_words=current,
                target_words=word_count,
                missing_words=max(0, word_count - current),
                content=content,
            ),
            model=layer_model,
            max_tokens=8192,
        )
        if not isinstance(expanded, str):
            return
        expanded = strip_llm_preamble(expanded)
        new_words = count_words(expanded)

        # Only accept a genuine expansion. A model that "rewrites" into something
        # shorter has replaced the chapter with a summary of itself — the exact
        # failure this gate exists to prevent, so keep the original instead.
        if new_words <= current:
            logger.warning(
                "Ch%s length gate: expansion returned %d words (was %d) - keeping original",
                ch_num,
                new_words,
                current,
            )
            return

        chapter.content = expanded
        chapter.word_count = new_words
        logger.info(
            "Ch%s length gate: expanded %d -> %d words (%.0f%% of target)",
            ch_num,
            current,
            new_words,
            100.0 * new_words / word_count,
        )
        if progress_callback:
            progress_callback(
                f"Ch{ch_num}: đã bổ sung {current} → {new_words} từ"
            )
    except Exception as exc:  # never break generation over a length tweak
        logger.warning("length gate failed (non-fatal): %s", exc)
