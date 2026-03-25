"""Rule-based Vietnamese emotion classifier for TTS voice modulation."""

EMOTION_KEYWORDS = {
    "sad": ["buồn", "khóc", "nước mắt", "đau", "thương", "mất", "chia ly", "cô đơn", "tuyệt vọng", "tang", "tiếc", "sầu", "lệ"],
    "happy": ["vui", "cười", "hạnh phúc", "sung sướng", "hoan hỉ", "niềm vui", "phấn khích", "mừng", "rạng rỡ", "hân hoan"],
    "angry": ["giận", "tức", "phẫn nộ", "căm hận", "thù", "nổi điên", "gầm", "quát", "nghiến", "hận"],
    "tense": ["nguy hiểm", "chiến đấu", "chạy", "trốn", "hồi hộp", "căng thẳng", "máu", "chết", "kinh hoàng", "sợ", "hoảng"],
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


def classify_emotion(text: str) -> str:
    """Classify text emotion by Vietnamese keyword frequency. Returns emotion label."""
    if not text or not text.strip():
        return "neutral"
    text_lower = text.lower()
    scores = {}
    for emotion, keywords in EMOTION_KEYWORDS.items():
        if not keywords:
            continue
        scores[emotion] = sum(text_lower.count(kw) for kw in keywords)
    if not scores or max(scores.values()) == 0:
        return "neutral"
    return max(scores, key=scores.get)


def get_voice_params(emotion: str) -> dict:
    """Return rate/pitch adjustments for given emotion."""
    return EMOTION_VOICE_PARAMS.get(emotion, EMOTION_VOICE_PARAMS["neutral"])
