"""Tests for ui/handlers.py — pure handler functions."""

import unittest
from unittest.mock import MagicMock, patch, PropertyMock

_t = lambda k, **kw: k  # dummy translation callable


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_character(name="Alice"):
    c = MagicMock()
    c.name = name
    return c


def _make_chapter(num=1):
    ch = MagicMock()
    ch.chapter_number = num
    ch.content = "chapter content"
    return ch


def _make_story_draft(title="Story", chapters=None, characters=None, synopsis="syn"):
    d = MagicMock()
    d.title = title
    d.synopsis = synopsis
    d.characters = characters if characters is not None else [_make_character()]
    d.chapters = chapters if chapters is not None else [_make_chapter()]
    return d


def _make_enhanced_story(title="Enhanced"):
    es = MagicMock()
    es.title = title
    es.chapters = [_make_chapter()]
    return es


def _make_video_script(panels=None):
    vs = MagicMock()
    vs.panels = panels if panels is not None else []
    vs.character_descriptions = {}
    return vs


def _make_output(story_draft=None, enhanced_story=None, video_script=None):
    out = MagicMock()
    out.story_draft = story_draft
    out.enhanced_story = enhanced_story
    out.video_script = video_script
    return out


def _make_orch_state(story_draft=None, enhanced_story=None, video_script=None):
    orch = MagicMock()
    orch.output = _make_output(story_draft, enhanced_story, video_script)
    return orch


def _make_user_profile(user_id="u1", username="testuser"):
    p = MagicMock()
    p.user_id = user_id
    p.username = username
    p.model_dump.return_value = {"user_id": user_id, "username": username}
    return p


# ---------------------------------------------------------------------------
# Tests: handle_login
# ---------------------------------------------------------------------------

class TestHandleLogin(unittest.TestCase):

    def test_empty_username_returns_fail(self):
        from ui.handlers import handle_login
        result = handle_login("", "pass", _t)
        self.assertIsNone(result[0])
        self.assertEqual(result[1], "msg.login_fail")

    def test_empty_password_returns_fail(self):
        from ui.handlers import handle_login
        result = handle_login("user", "", _t)
        self.assertIsNone(result[0])

    @patch("ui.handlers.UserManager")
    def test_successful_login_returns_profile(self, MockUM):
        from ui.handlers import handle_login
        profile = _make_user_profile()
        um = MockUM.return_value
        um.login.return_value = profile
        um.list_stories.return_value = [
            {"story_id": "s1", "title": "T", "saved_at": "2024"}
        ]
        result = handle_login("user", "pass", _t)
        self.assertIsNotNone(result[0])
        self.assertEqual(result[0]["username"], "testuser")
        self.assertIn("msg.login_success", result[1])
        self.assertEqual(len(result[2]), 1)

    @patch("ui.handlers.UserManager")
    def test_failed_login_returns_none(self, MockUM):
        from ui.handlers import handle_login
        um = MockUM.return_value
        um.login.return_value = None
        result = handle_login("user", "wrongpass", _t)
        self.assertIsNone(result[0])
        self.assertEqual(result[1], "msg.login_fail")


# ---------------------------------------------------------------------------
# Tests: handle_register
# ---------------------------------------------------------------------------

class TestHandleRegister(unittest.TestCase):

    def test_empty_inputs_returns_fail(self):
        from ui.handlers import handle_register
        result = handle_register("", "", _t)
        self.assertIsNone(result[0])

    @patch("ui.handlers.UserManager")
    def test_successful_register(self, MockUM):
        from ui.handlers import handle_register
        profile = _make_user_profile()
        um = MockUM.return_value
        um.register.return_value = profile
        result = handle_register("newuser", "pass", _t)
        self.assertIsNotNone(result[0])
        self.assertEqual(result[1], "msg.register_success")

    @patch("ui.handlers.UserManager")
    def test_duplicate_register_returns_fail(self, MockUM):
        from ui.handlers import handle_register
        um = MockUM.return_value
        um.register.side_effect = ValueError("exists")
        result = handle_register("user", "pass", _t)
        self.assertIsNone(result[0])
        self.assertEqual(result[1], "msg.register_fail")


# ---------------------------------------------------------------------------
# Tests: handle_save_story
# ---------------------------------------------------------------------------

class TestHandleSaveStory(unittest.TestCase):

    def test_no_user_returns_no_login(self):
        from ui.handlers import handle_save_story
        msg, table = handle_save_story(None, None, "title", _t)
        self.assertEqual(msg, "msg.no_login")
        self.assertEqual(table, [])

    def test_no_orch_state_returns_no_story(self):
        from ui.handlers import handle_save_story
        msg, table = handle_save_story({"user_id": "u1"}, None, "title", _t)
        self.assertEqual(msg, "msg.no_story")

    @patch("ui.handlers.UserManager")
    def test_successful_save(self, MockUM):
        from ui.handlers import handle_save_story
        um = MockUM.return_value
        um.save_story.return_value = "story123"
        um.list_stories.return_value = [
            {"story_id": "story123", "title": "T", "saved_at": "2024"}
        ]
        orch = _make_orch_state(story_draft=_make_story_draft())
        orch.output.model_dump.return_value = {}
        result = handle_save_story({"user_id": "u1"}, orch, "My Story", _t)
        self.assertIn("story123", result[0])

    @patch("ui.handlers.UserManager")
    def test_exception_returns_error(self, MockUM):
        from ui.handlers import handle_save_story
        um = MockUM.return_value
        um.save_story.side_effect = Exception("DB error")
        orch = _make_orch_state(story_draft=_make_story_draft())
        msg, table = handle_save_story({"user_id": "u1"}, orch, "T", _t)
        self.assertIn("error", msg.lower())


# ---------------------------------------------------------------------------
# Tests: handle_export_pdf
# ---------------------------------------------------------------------------

class TestHandleExportPdf(unittest.TestCase):

    def test_no_orch_returns_none(self):
        from ui.handlers import handle_export_pdf
        result = handle_export_pdf(None, _t)
        self.assertIsNone(result[0])

    def test_no_story_returns_none(self):
        from ui.handlers import handle_export_pdf
        orch = _make_orch_state()
        result = handle_export_pdf(orch, _t)
        self.assertIsNone(result[0])

    @patch("ui.handlers.PDFExporter")
    def test_export_returns_path(self, MockPDF):
        from ui.handlers import handle_export_pdf
        MockPDF.export.return_value = "output/story.pdf"
        stats_mock = MagicMock()
        stats_mock.model_dump.return_value = {"total_words": 100}
        MockPDF.compute_reading_stats.return_value = stats_mock
        orch = _make_orch_state(
            story_draft=_make_story_draft(),
            enhanced_story=_make_enhanced_story(),
        )
        paths, stats = handle_export_pdf(orch, _t)
        self.assertEqual(paths, ["output/story.pdf"])

    @patch("ui.handlers.PDFExporter")
    def test_export_exception_returns_error_dict(self, MockPDF):
        from ui.handlers import handle_export_pdf
        MockPDF.export.side_effect = Exception("pdf fail")
        orch = _make_orch_state(enhanced_story=_make_enhanced_story())
        paths, stats = handle_export_pdf(orch, _t)
        self.assertIsNone(paths)
        self.assertIn("error", stats)


# ---------------------------------------------------------------------------
# Tests: handle_export_tts
# ---------------------------------------------------------------------------

class TestHandleExportTts(unittest.TestCase):

    def test_no_orch_returns_none(self):
        from ui.handlers import handle_export_tts
        self.assertIsNone(handle_export_tts(None, _t))

    def test_no_story_returns_none(self):
        from ui.handlers import handle_export_tts
        orch = _make_orch_state()
        self.assertIsNone(handle_export_tts(orch, _t))

    @patch("ui.handlers.TTSScriptGenerator")
    def test_export_returns_file(self, MockTTS):
        from ui.handlers import handle_export_tts
        gen = MockTTS.return_value
        gen.generate_full_script.return_value = MagicMock()
        gen.export_script.return_value = "output/tts.txt"
        orch = _make_orch_state(enhanced_story=_make_enhanced_story())
        result = handle_export_tts(orch, _t)
        self.assertEqual(result, ["output/tts.txt"])

    @patch("ui.handlers.TTSScriptGenerator")
    def test_export_exception_returns_none(self, MockTTS):
        from ui.handlers import handle_export_tts
        gen = MockTTS.return_value
        gen.generate_full_script.side_effect = Exception("tts fail")
        orch = _make_orch_state(enhanced_story=_make_enhanced_story())
        result = handle_export_tts(orch, _t)
        self.assertIsNone(result)


# ---------------------------------------------------------------------------
# Tests: handle_export_tts_audio
# ---------------------------------------------------------------------------

class TestHandleExportTtsAudio(unittest.TestCase):

    def test_no_orch_returns_none(self):
        from ui.handlers import handle_export_tts_audio
        paths, msg = handle_export_tts_audio(None)
        self.assertIsNone(paths)

    def test_no_story_returns_none(self):
        from ui.handlers import handle_export_tts_audio
        orch = _make_orch_state()
        paths, msg = handle_export_tts_audio(orch)
        self.assertIsNone(paths)

    def test_no_chapters_returns_none(self):
        from ui.handlers import handle_export_tts_audio
        es = _make_enhanced_story()
        es.chapters = []
        orch = _make_orch_state(enhanced_story=es)
        paths, msg = handle_export_tts_audio(orch)
        self.assertIsNone(paths)

    def test_export_audio_success(self):
        from ui.handlers import handle_export_tts_audio
        with patch("services.tts_audio_generator.TTSAudioGenerator") as MockTTS:
            gen = MockTTS.return_value
            gen.generate_full_audiobook.return_value = ["ch1.mp3", "ch2.mp3"]
            orch = _make_orch_state(enhanced_story=_make_enhanced_story())
            paths, msg = handle_export_tts_audio(orch)
            self.assertEqual(len(paths), 2)
            self.assertIn("2", msg)


# ---------------------------------------------------------------------------
# Tests: handle_share_story
# ---------------------------------------------------------------------------

class TestHandleShareStory(unittest.TestCase):

    def test_no_orch_returns_empty_link(self):
        from ui.handlers import handle_share_story
        link, _ = handle_share_story(None, _t)
        self.assertEqual(link, "")

    def test_no_story_returns_empty_link(self):
        from ui.handlers import handle_share_story
        orch = _make_orch_state()
        link, _ = handle_share_story(orch, _t)
        self.assertEqual(link, "")

    @patch("ui.handlers.ConfigManager")
    @patch("ui.handlers.ShareManager")
    def test_share_returns_link(self, MockShare, MockConfig):
        from ui.handlers import handle_share_story
        share = MagicMock()
        share.html_path = "output/share.html"
        MockShare.return_value.create_share.return_value = share
        cfg = MockConfig.return_value
        cfg.pipeline.share_base_url = "http://example.com/"
        orch = _make_orch_state(story_draft=_make_story_draft(), enhanced_story=_make_enhanced_story())
        link, _ = handle_share_story(orch, _t)
        self.assertIn("output/share.html", link)

    @patch("ui.handlers.ShareManager")
    @patch("ui.handlers.ConfigManager")
    def test_share_exception_returns_error(self, MockConfig, MockShare):
        from ui.handlers import handle_share_story
        MockShare.return_value.create_share.side_effect = Exception("share fail")
        MockConfig.return_value.pipeline.share_base_url = ""
        orch = _make_orch_state(enhanced_story=_make_enhanced_story())
        link, _ = handle_share_story(orch, _t)
        self.assertIn("error", link.lower())


# ---------------------------------------------------------------------------
# Tests: handle_export_files / handle_export_zip / handle_export_video_assets
# ---------------------------------------------------------------------------

class TestHandleExportFiles(unittest.TestCase):

    def test_no_orch_returns_none(self):
        from ui.handlers import handle_export_files
        self.assertIsNone(handle_export_files(None, ["json"]))

    def test_export_returns_paths(self):
        from ui.handlers import handle_export_files
        orch = MagicMock()
        orch.export_output.return_value = ["file1.json"]
        result = handle_export_files(orch, ["json"])
        self.assertEqual(result, ["file1.json"])

    def test_export_exception_returns_none(self):
        from ui.handlers import handle_export_files
        orch = MagicMock()
        orch.export_output.side_effect = Exception("fail")
        result = handle_export_files(orch, ["json"])
        self.assertIsNone(result)

    def test_empty_paths_returns_none(self):
        from ui.handlers import handle_export_files
        orch = MagicMock()
        orch.export_output.return_value = []
        result = handle_export_files(orch, ["json"])
        self.assertIsNone(result)


class TestHandleExportZip(unittest.TestCase):

    def test_no_orch_returns_none(self):
        from ui.handlers import handle_export_zip
        self.assertIsNone(handle_export_zip(None, [], _t))

    def test_export_zip_returns_list(self):
        from ui.handlers import handle_export_zip
        orch = MagicMock()
        orch.export_zip.return_value = "output/story.zip"
        result = handle_export_zip(orch, ["json"], _t)
        self.assertEqual(result, ["output/story.zip"])

    def test_export_zip_none_returns_none(self):
        from ui.handlers import handle_export_zip
        orch = MagicMock()
        orch.export_zip.return_value = None
        result = handle_export_zip(orch, ["json"], _t)
        self.assertIsNone(result)

    def test_export_zip_exception_returns_none(self):
        from ui.handlers import handle_export_zip
        orch = MagicMock()
        orch.export_zip.side_effect = Exception("zip fail")
        result = handle_export_zip(orch, ["json"], _t)
        self.assertIsNone(result)


class TestHandleExportVideoAssets(unittest.TestCase):

    def test_no_orch_returns_none(self):
        from ui.handlers import handle_export_video_assets
        self.assertIsNone(handle_export_video_assets(None, _t))

    def test_returns_path(self):
        from ui.handlers import handle_export_video_assets
        orch = MagicMock()
        orch.export_video_assets.return_value = "output/video.zip"
        result = handle_export_video_assets(orch, _t)
        self.assertEqual(result, "output/video.zip")

    def test_exception_returns_none(self):
        from ui.handlers import handle_export_video_assets
        orch = MagicMock()
        orch.export_video_assets.side_effect = Exception("fail")
        result = handle_export_video_assets(orch, _t)
        self.assertIsNone(result)


# ---------------------------------------------------------------------------
# Tests: get_checkpoint_choices / resolve_checkpoint_path
# ---------------------------------------------------------------------------

class TestCheckpointHelpers(unittest.TestCase):

    @patch("ui.handlers.PipelineOrchestrator")
    def test_get_checkpoint_choices_formats(self, MockOrch):
        from ui.handlers import get_checkpoint_choices
        MockOrch.list_checkpoints.return_value = [
            {"file": "story_layer1.json", "modified": "2024-01-01 10:00", "size_kb": 5}
        ]
        choices = get_checkpoint_choices()
        self.assertEqual(len(choices), 1)
        self.assertIn("story_layer1.json", choices[0])
        self.assertIn("5KB", choices[0])

    @patch("ui.handlers.PipelineOrchestrator")
    def test_get_checkpoint_choices_empty(self, MockOrch):
        from ui.handlers import get_checkpoint_choices
        MockOrch.list_checkpoints.return_value = []
        choices = get_checkpoint_choices()
        self.assertEqual(choices, [])

    def test_resolve_checkpoint_path_none_returns_none(self):
        from ui.handlers import resolve_checkpoint_path
        self.assertIsNone(resolve_checkpoint_path(None))

    def test_resolve_checkpoint_path_empty_returns_none(self):
        from ui.handlers import resolve_checkpoint_path
        self.assertIsNone(resolve_checkpoint_path(""))

    @patch("ui.handlers.PipelineOrchestrator")
    def test_resolve_checkpoint_path_extracts_filename(self, MockOrch):
        from ui.handlers import resolve_checkpoint_path
        MockOrch.CHECKPOINT_DIR = "output/checkpoints"
        path = resolve_checkpoint_path("story_layer1.json (2024-01-01, 5KB)")
        self.assertIn("story_layer1.json", path)


# ---------------------------------------------------------------------------
# Tests: handle_load_checkpoint
# ---------------------------------------------------------------------------

class TestHandleLoadCheckpoint(unittest.TestCase):

    def test_no_choice_returns_no_checkpoint(self):
        from ui.handlers import handle_load_checkpoint
        msg, orch = handle_load_checkpoint("", None, _t)
        self.assertEqual(msg, "continue.no_checkpoint")

    @patch("ui.handlers.PipelineOrchestrator")
    def test_loads_checkpoint_with_story(self, MockOrch):
        from ui.handlers import handle_load_checkpoint
        MockOrch.CHECKPOINT_DIR = "output/checkpoints"
        orch_instance = MagicMock()
        MockOrch.return_value = orch_instance
        draft = _make_story_draft(title="Loaded", synopsis="syn", characters=[_make_character()])
        draft.chapters = [_make_chapter()]
        orch_instance.output.story_draft = draft
        msg, returned_orch = handle_load_checkpoint("story_layer1.json (2024-01-01, 5KB)", None, _t)
        self.assertIn("continue.loaded", msg)

    @patch("ui.handlers.PipelineOrchestrator")
    def test_load_no_story_returns_no_story(self, MockOrch):
        from ui.handlers import handle_load_checkpoint
        MockOrch.CHECKPOINT_DIR = "output/checkpoints"
        orch_instance = MagicMock()
        MockOrch.return_value = orch_instance
        orch_instance.output.story_draft = None
        msg, _ = handle_load_checkpoint("story_layer1.json (2024-01-01, 5KB)", None, _t)
        self.assertEqual(msg, "continue.no_story")


# ---------------------------------------------------------------------------
# Tests: handle_add_chapters / handle_delete_chapters / handle_update_character
# ---------------------------------------------------------------------------

class TestHandleAddChapters(unittest.TestCase):

    def test_no_orch_returns_no_story(self):
        from ui.handlers import handle_add_chapters
        msg, orch = handle_add_chapters(None, 5, 2000, _t)
        self.assertEqual(msg, "continue.no_story")

    def test_no_draft_returns_no_story(self):
        from ui.handlers import handle_add_chapters
        orch = MagicMock()
        orch.output.story_draft = None
        msg, _ = handle_add_chapters(orch, 5, 2000, _t)
        self.assertEqual(msg, "continue.no_story")

    def test_add_chapters_calls_continue(self):
        from ui.handlers import handle_add_chapters
        orch = MagicMock()
        orch.output.story_draft = _make_story_draft()
        orch.continue_story = MagicMock()
        msg, returned = handle_add_chapters(orch, 3, 2000, _t)
        orch.continue_story.assert_called_once()
        self.assertIn("continue.chapters_added", msg)


class TestHandleDeleteChapters(unittest.TestCase):

    def test_no_orch_returns_no_story(self):
        from ui.handlers import handle_delete_chapters
        msg, orch = handle_delete_chapters(None, 3, _t)
        self.assertEqual(msg, "continue.no_story")

    def test_no_draft_returns_no_story(self):
        from ui.handlers import handle_delete_chapters
        orch = MagicMock()
        orch.output.story_draft = None
        msg, _ = handle_delete_chapters(orch, 3, _t)
        self.assertEqual(msg, "continue.no_story")

    def test_delete_calls_remove_chapters(self):
        from ui.handlers import handle_delete_chapters
        orch = MagicMock()
        orch.output.story_draft = _make_story_draft()
        msg, returned = handle_delete_chapters(orch, 5, _t)
        orch.remove_chapters.assert_called_once_with(5)
        self.assertIn("continue.chapters_deleted", msg)


class TestHandleUpdateCharacter(unittest.TestCase):

    def test_no_orch_returns_no_story(self):
        from ui.handlers import handle_update_character
        msg, orch = handle_update_character(None, "Alice", "brave", "save world", _t)
        self.assertEqual(msg, "continue.no_story")

    def test_no_draft_returns_no_story(self):
        from ui.handlers import handle_update_character
        orch = MagicMock()
        orch.output.story_draft = None
        msg, _ = handle_update_character(orch, "Alice", "brave", "save world", _t)
        self.assertEqual(msg, "continue.no_story")

    def test_empty_name_returns_char_name_msg(self):
        from ui.handlers import handle_update_character
        orch = MagicMock()
        orch.output.story_draft = _make_story_draft()
        msg, _ = handle_update_character(orch, "", "brave", "save world", _t)
        self.assertEqual(msg, "continue.char_name")

    def test_no_updates_returns_hint(self):
        from ui.handlers import handle_update_character
        orch = MagicMock()
        orch.output.story_draft = _make_story_draft()
        msg, _ = handle_update_character(orch, "Alice", "", "", _t)
        self.assertIn("continue.char_personality", msg)

    def test_update_calls_orch_update(self):
        from ui.handlers import handle_update_character
        orch = MagicMock()
        orch.output.story_draft = _make_story_draft()
        msg, returned = handle_update_character(orch, "Alice", "brave", "save world", _t)
        orch.update_character.assert_called_once()
        self.assertIn("continue.char_updated", msg)


# ---------------------------------------------------------------------------
# Tests: handle_enhance
# ---------------------------------------------------------------------------

class TestHandleEnhance(unittest.TestCase):

    def test_no_orch_returns_no_story(self):
        from ui.handlers import handle_enhance
        msg, orch = handle_enhance(None, 3, 2000, _t)
        self.assertEqual(msg, "continue.no_story")

    def test_no_draft_returns_no_story(self):
        from ui.handlers import handle_enhance
        orch = MagicMock()
        orch.output.story_draft = None
        msg, _ = handle_enhance(orch, 3, 2000, _t)
        self.assertEqual(msg, "continue.no_story")

    def test_calls_enhance_chapters(self):
        from ui.handlers import handle_enhance
        orch = MagicMock()
        orch.output.story_draft = _make_story_draft()
        msg, returned = handle_enhance(orch, 3, 2000, _t)
        orch.enhance_chapters.assert_called_once()
        self.assertIn("continue.enhanced", msg)


# ---------------------------------------------------------------------------
# Tests: handle_genre_autofill
# ---------------------------------------------------------------------------

class TestHandleGenreAutofill(unittest.TestCase):

    def test_known_genre_returns_preset(self):
        from ui.handlers import handle_genre_autofill
        result = handle_genre_autofill("Tiên Hiệp")
        self.assertEqual(result[0], 50)
        self.assertEqual(result[1], 3000)
        self.assertEqual(result[2], "Miêu tả chi tiết")

    def test_unknown_genre_returns_none_tuple(self):
        from ui.handlers import handle_genre_autofill
        result = handle_genre_autofill("Unknown Genre")
        self.assertEqual(result, (None, None, None))

    def test_empty_genre_returns_none_tuple(self):
        from ui.handlers import handle_genre_autofill
        result = handle_genre_autofill("")
        self.assertEqual(result, (None, None, None))

    def test_ngon_tinh_preset(self):
        from ui.handlers import handle_genre_autofill
        result = handle_genre_autofill("Ngôn Tình")
        self.assertEqual(result[0], 30)
        self.assertEqual(result[1], 2500)

    def test_do_thi_preset(self):
        from ui.handlers import handle_genre_autofill
        result = handle_genre_autofill("Đô Thị")
        self.assertEqual(result[2], "Đối thoại sắc bén")


# ---------------------------------------------------------------------------
# Tests: handle_character_gallery
# ---------------------------------------------------------------------------

class TestHandleCharacterGallery(unittest.TestCase):

    def test_no_orch_returns_empty(self):
        from ui.handlers import handle_character_gallery
        result = handle_character_gallery(None)
        self.assertEqual(result, [])

    def test_no_output_returns_empty(self):
        from ui.handlers import handle_character_gallery
        orch = MagicMock()
        orch.output = None
        result = handle_character_gallery(orch)
        self.assertEqual(result, [])

    def test_no_char_refs_returns_empty(self):
        from ui.handlers import handle_character_gallery
        orch = MagicMock()
        orch.output.character_refs = None
        vs = MagicMock()
        vs.character_refs = None
        orch.output.video_script = vs
        result = handle_character_gallery(orch)
        self.assertEqual(result, [])

    @patch("os.path.exists")
    def test_char_refs_with_existing_paths(self, mock_exists):
        from ui.handlers import handle_character_gallery
        mock_exists.return_value = True
        orch = MagicMock()
        orch.output.character_refs = {"Alice": "path/alice.png", "Bob": "path/bob.png"}
        result = handle_character_gallery(orch)
        self.assertEqual(len(result), 2)
        names = [r[1] for r in result]
        self.assertIn("Alice", names)

    @patch("os.path.exists")
    def test_char_refs_with_missing_paths_excluded(self, mock_exists):
        from ui.handlers import handle_character_gallery
        mock_exists.return_value = False
        orch = MagicMock()
        orch.output.character_refs = {"Alice": "path/alice.png"}
        result = handle_character_gallery(orch)
        self.assertEqual(result, [])


# ---------------------------------------------------------------------------
# Tests: handle_generate_images
# ---------------------------------------------------------------------------

class TestHandleGenerateImages(unittest.TestCase):

    def test_no_orch_returns_empty(self):
        from ui.handlers import handle_generate_images
        paths, msg = handle_generate_images(None, t=_t)
        self.assertEqual(paths, [])

    def test_no_video_script_returns_empty(self):
        from ui.handlers import handle_generate_images
        orch = _make_orch_state()
        paths, msg = handle_generate_images(orch, t=_t)
        self.assertEqual(paths, [])

    def test_no_panels_returns_empty(self):
        from ui.handlers import handle_generate_images
        orch = _make_orch_state(video_script=_make_video_script(panels=[]))
        paths, msg = handle_generate_images(orch, t=_t)
        self.assertEqual(paths, [])

    def test_with_panels_calls_generators(self):
        from ui.handlers import handle_generate_images
        panel = MagicMock()
        panel.chapter_number = 1
        vs = _make_video_script(panels=[panel])
        orch = _make_orch_state(video_script=vs)
        with patch("services.image_generator.ImageGenerator") as MockImgGen, \
             patch("services.image_prompt_generator.ImagePromptGenerator") as MockPromptGen:
            MockPromptGen.return_value.generate_from_panel.return_value = MagicMock()
            MockImgGen.return_value.generate_story_images.return_value = ["img1.png"]
            paths, msg = handle_generate_images(orch, provider="dalle", t=_t)
            self.assertEqual(paths, ["img1.png"])


# ---------------------------------------------------------------------------
# Tests: handle_compose_video
# ---------------------------------------------------------------------------

class TestHandleComposeVideo(unittest.TestCase):

    def test_no_orch_returns_none(self):
        from ui.handlers import handle_compose_video
        audio, video, msg = handle_compose_video(None)
        self.assertIsNone(audio)
        self.assertIsNone(video)

    def test_no_story_returns_msg(self):
        from ui.handlers import handle_compose_video
        orch = _make_orch_state()
        audio, video, msg = handle_compose_video(orch)
        self.assertIsNone(audio)

    def test_no_chapters_returns_msg(self):
        from ui.handlers import handle_compose_video
        es = _make_enhanced_story()
        es.chapters = []
        orch = _make_orch_state(enhanced_story=es)
        audio, video, msg = handle_compose_video(orch)
        self.assertIsNone(audio)

    @patch("os.path.exists")
    def test_compose_with_story_no_images(self, mock_exists):
        from ui.handlers import handle_compose_video
        mock_exists.return_value = False
        orch = _make_orch_state(enhanced_story=_make_enhanced_story())
        with patch("services.tts_audio_generator.TTSAudioGenerator") as MockTTS, \
             patch("services.video_composer.VideoComposer"):
            gen = MockTTS.return_value
            gen.generate_full_audiobook.return_value = ["ch1.mp3"]
            audio, video, msg = handle_compose_video(orch)
            self.assertIsNotNone(audio)
            self.assertIsNone(video)
            self.assertIn("1 audio", msg)


if __name__ == "__main__":
    unittest.main()
