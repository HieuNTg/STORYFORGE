"""Test TTSScriptGenerator service."""
import os
from services.tts_script_generator import TTSScriptGenerator


def test_export_script_creates_file(tmp_path):
    gen = TTSScriptGenerator()
    script = '[Narrator] (calm) "Test narration"\n[PAUSE 2s]\n[Minh] (angry) "Test dialogue"'
    path = gen.export_script(script, str(tmp_path / "narration.txt"))
    assert os.path.exists(path)
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    assert "[Narrator]" in content
    assert "[Minh]" in content


def test_export_script_empty(tmp_path):
    gen = TTSScriptGenerator()
    path = gen.export_script("", str(tmp_path / "empty.txt"))
    assert os.path.exists(path)
