"""Rule-based bilingual (Vietnamese/English) emotion classifier."""

EMOTION_KEYWORDS = {
    "sad": ["buồn", "khóc", "nước mắt", "đau", "thương", "mất", "chia ly", "cô đơn", "tuyệt vọng", "tang", "tiếc", "sầu", "lệ"],
    "happy": ["vui", "cười", "hạnh phúc", "sung sướng", "hoan hỉ", "niềm vui", "phấn khích", "mừng", "rạng rỡ", "hân hoan"],
    "angry": ["giận", "tức", "phẫn nộ", "căm hận", "thù", "nổi điên", "gầm", "quát", "nghiến", "hận"],
    "tense": ["nguy hiểm", "chiến đấu", "chạy", "trốn", "hồi hộp", "căng thẳng", "máu", "chết", "kinh hoàng", "sợ", "hoảng"],
    "neutral": [],
}

EMOTION_KEYWORDS_EN = {
    "sad": ["sad", "cry", "tears", "pain", "grief", "loss", "lonely", "despair", "mourn", "sorrow", "weep", "heartbreak"],
    "happy": ["happy", "laugh", "joy", "delight", "excited", "cheerful", "smile", "celebrate", "thrilled", "elated"],
    "angry": ["angry", "furious", "rage", "hatred", "wrath", "scream", "yell", "clench", "resentment", "outraged"],
    "tense": ["danger", "fight", "run", "escape", "suspense", "tense", "blood", "death", "horror", "fear", "panic", "threat"],
    "neutral": [],
}

# Voice parameter adjustments per emotion (for edge-tts)
EMOTION_VOICE_PARAMS = {
    "sad":     {"rate": "-15%", "pitch": "-5Hz"},
    "happy":   {"rate": "+10%", "pitch": "+3Hz"},
    "angry":   {"rate": "+5%",  "pitch": "+5Hz"},
    "tense":   {"rate": "+8%",  "pitch": "+2Hz"},
    "neutral": {"rate": "+0%",  "pitch": "+0Hz"},
}

_VIETNAMESE_CHARS = set("àáảãạăắằẳẵặâấầẩẫậèéẻẽẹêếềểễệìíỉĩịòóỏõọôốồổỗộơớờởỡợùúủũụưứừửữựỳýỷỹỵđ")


def _detect_language(text: str) -> str:
    """Detect language by checking for Vietnamese diacritical marks."""
    sample = text[:500].lower()
    vn_count = sum(1 for c in sample if c in _VIETNAMESE_CHARS)
    return "vi" if vn_count > 3 else "en"


def classify_emotion(text: str) -> str:
    """Classify text emotion by keyword frequency. Auto-detects Vietnamese vs English."""
    if not text or not text.strip():
        return "neutral"
    text_lower = text.lower()
    lang = _detect_language(text)
    # Primary keyword set based on detected language, fallback to other
    primary = EMOTION_KEYWORDS if lang == "vi" else EMOTION_KEYWORDS_EN
    secondary = EMOTION_KEYWORDS_EN if lang == "vi" else EMOTION_KEYWORDS
    scores = {}
    for emotion, keywords in primary.items():
        if not keywords:
            continue
        scores[emotion] = sum(text_lower.count(kw) for kw in keywords)
    # If primary yields nothing, try secondary (handles short mixed text)
    if not scores or max(scores.values()) == 0:
        scores = {}
        for emotion, keywords in secondary.items():
            if not keywords:
                continue
            scores[emotion] = sum(text_lower.count(kw) for kw in keywords)
    if not scores or max(scores.values()) == 0:
        return "neutral"
    return max(scores, key=scores.get)


def get_voice_params(emotion: str) -> dict:
    """Return rate/pitch adjustments for given emotion."""
    return EMOTION_VOICE_PARAMS.get(emotion, EMOTION_VOICE_PARAMS["neutral"])
