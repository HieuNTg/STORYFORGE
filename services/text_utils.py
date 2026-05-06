"""Shared text utility functions."""

import re as _re


def build_idea_block(idea: str, idea_summary: str = "") -> str:
    """Build the [Ý TƯỞNG GỐC] payload inserted into chapter/beat/scene prompts.

    Verbatim if idea ≤3000 chars; head 2000 + tail 500 + summary otherwise.
    Empty idea returns the explicit "no idea provided" placeholder.
    Shared by L1 (chapter_writer) and L2 (scene_enhancer) so prompt format stays identical.
    """
    if not idea:
        return "(Tác giả không cung cấp ý tưởng cụ thể.)"
    if len(idea) <= 3000:
        return idea
    head = idea[:2000]
    tail = idea[-500:]
    summary = idea_summary or "(Tóm tắt không khả dụng — chỉ dùng đầu+cuối)"
    return (
        f"[ĐOẠN ĐẦU NGUYÊN VĂN]\n{head}\n\n"
        f"[ĐOẠN CUỐI NGUYÊN VĂN]\n{tail}\n\n"
        f"[TÓM TẮT GIỮ TÊN RIÊNG]\n{summary}"
    )


def build_idea_header(idea: str, idea_summary: str = "") -> str:
    """Wrap build_idea_block with the [Ý TƯỞNG GỐC] header/footer used at prompt top."""
    block = build_idea_block(idea, idea_summary)
    return (
        "[Ý TƯỞNG GỐC CỦA TÁC GIẢ — TUYỆT ĐỐI KHÔNG ĐƯỢC LỆCH]\n"
        f"{block}\n"
        "[KẾT THÚC Ý TƯỞNG GỐC]\n\n"
    )

try:
    import nh3 as _nh3
    _HAS_NH3 = True
except ImportError:
    _nh3 = None  # type: ignore[assignment]
    _HAS_NH3 = False

_ALLOWED_TAGS = {"strong", "em", "br", "p", "h1", "h2", "h3", "h4",
                 "ul", "ol", "li", "a", "code", "pre", "blockquote"}
_ALLOWED_ATTRS = {"a": {"href", "target", "rel"}}


def sanitize_story_html(content: str) -> str:
    """Sanitize HTML content to prevent XSS. Strips all non-allowlisted tags."""
    if not content:
        return ""
    if not _HAS_NH3:
        return content
    return _nh3.clean(content, tags=_ALLOWED_TAGS, attributes=_ALLOWED_ATTRS, link_rel=None)

_PREAMBLE_PATTERNS = [
    _re.compile(r"^\s*(dưới đây|sau đây|đây là|dưới đấy)[^\n]*?(viết lại|bản viết|nâng cấp|cải thiện|phiên bản|cảnh|đoạn)[^\n]*\n+", _re.IGNORECASE),
    _re.compile(r"^\s*(lưu ý|ghi chú|chú thích)[:\-][^\n]*\n+", _re.IGNORECASE),
]
_SCAFFOLD_LABEL = _re.compile(
    r"^\s*\*{0,2}(BỐI CẢNH|NHÂN VẬT|ĐỊA ĐIỂM|THỜI GIAN|NỘI DUNG|CẢNH|TÓM TẮT|GHI CHÚ|HƯỚNG DẪN)\b[^\n]*:\*{0,2}\s*",
    _re.IGNORECASE,
)
_SECTION_DIVIDER = _re.compile(r"^\s*(\*{3,}|-{3,}|={3,}|#{1,6}\s*\*{3,})\s*$")


def strip_llm_scaffolding(text: str) -> str:
    """Remove LLM preamble and scene-scaffolding labels that leak into prose."""
    if not text:
        return text
    out = text
    for pat in _PREAMBLE_PATTERNS:
        out = pat.sub("", out, count=1)
    lines = out.splitlines()
    cleaned: list[str] = []
    for ln in lines:
        if _SECTION_DIVIDER.match(ln):
            continue
        stripped = _SCAFFOLD_LABEL.sub("", ln, count=1)
        cleaned.append(stripped)
    result = "\n".join(cleaned)
    return _re.sub(r"\n{3,}", "\n\n", result).strip()


def excerpt_text(text: str, max_chars: int = 4000, head_ratio: float = 0.67) -> str:
    """Return a head+tail excerpt of text for use in prompts.

    If text fits within max_chars, return it unchanged.
    Otherwise take head_ratio of max_chars from the start and the rest from the end,
    joined by an ellipsis marker so the model knows content was trimmed.

    Args:
        text: Input text to excerpt.
        max_chars: Maximum total characters in the result (default 4000).
        head_ratio: Fraction of max_chars taken from the head (default 0.67 → 67%).
    """
    if len(text) <= max_chars:
        return text
    head = int(max_chars * head_ratio)
    tail = max_chars - head
    return text[:head] + "\n...\n" + text[-tail:]
