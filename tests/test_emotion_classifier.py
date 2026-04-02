"""Tests for rule-based Vietnamese emotion classifier."""


from services.emotion_classifier import (
    EMOTION_VOICE_PARAMS,
    classify_emotion,
    get_voice_params,
)


class TestClassifyEmotion:
    def test_empty_string_returns_neutral(self):
        assert classify_emotion("") == "neutral"

    def test_whitespace_only_returns_neutral(self):
        assert classify_emotion("   ") == "neutral"

    def test_no_keywords_returns_neutral(self):
        assert classify_emotion("Hôm nay trời đẹp lắm.") == "neutral"

    def test_sad_keyword_detected(self):
        assert classify_emotion("Anh ấy khóc suốt đêm vì buồn.") == "sad"

    def test_happy_keyword_detected(self):
        assert classify_emotion("Cô ấy vui và cười rạng rỡ.") == "happy"

    def test_angry_keyword_detected(self):
        assert classify_emotion("Hắn giận dữ và quát to.") == "angry"

    def test_tense_keyword_detected(self):
        assert classify_emotion("Họ chạy trốn nguy hiểm và sợ hãi.") == "tense"

    def test_mixed_highest_count_wins(self):
        # sad has 3 keywords, happy has 1
        text = "buồn buồn buồn vui"
        assert classify_emotion(text) == "sad"

    def test_case_insensitive(self):
        # keywords are lowercase; text uppercased should still match
        assert classify_emotion("BUỒN") == "sad"

    def test_single_keyword_match(self):
        assert classify_emotion("tang lễ hôm nay.") == "sad"


class TestGetVoiceParams:
    def test_sad_params(self):
        params = get_voice_params("sad")
        assert params["rate"] == "-15%"
        assert params["pitch"] == "-5Hz"

    def test_happy_params(self):
        params = get_voice_params("happy")
        assert params["rate"] == "+10%"
        assert params["pitch"] == "+3Hz"

    def test_angry_params(self):
        params = get_voice_params("angry")
        assert params["rate"] == "+5%"
        assert params["pitch"] == "+5Hz"

    def test_tense_params(self):
        params = get_voice_params("tense")
        assert params["rate"] == "+8%"
        assert params["pitch"] == "+2Hz"

    def test_neutral_params(self):
        params = get_voice_params("neutral")
        assert params["rate"] == "+0%"
        assert params["pitch"] == "+0Hz"

    def test_unknown_emotion_falls_back_to_neutral(self):
        params = get_voice_params("unknown_xyz")
        assert params == EMOTION_VOICE_PARAMS["neutral"]

    def test_returns_dict(self):
        assert isinstance(get_voice_params("sad"), dict)
