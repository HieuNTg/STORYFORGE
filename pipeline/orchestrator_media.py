"""Layer 3.5 media production: images, TTS audio, video composition."""

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from config import ConfigManager
from services.seedream_client import SeedreamClient
from services.tts_audio_generator import TTSAudioGenerator
from services.video_composer import VideoComposer

logger = logging.getLogger(__name__)


class MediaProducer:
    """Handles Layer 3.5: character images, scene images, TTS audio, video."""

    def __init__(self, config: ConfigManager):
        self.config = config

    def run(self, draft, enhanced, video_script, progress_callback=None) -> dict:
        """Generate images, TTS audio, compose video.

        Returns dict with paths: {character_refs, scene_images, audio_paths, video_path}
        """
        result = {"character_refs": {}, "scene_images": [], "audio_paths": [], "video_path": ""}
        cfg = self.config.pipeline

        def _log(msg):
            if progress_callback:
                progress_callback(msg)

        # Step 1: Character reference images (Seedream)
        seedream = SeedreamClient(api_key=cfg.seedream_api_key, base_url=cfg.seedream_api_url)
        if seedream.is_configured() and draft.characters:
            _log("[MEDIA] Tao anh tham chieu nhan vat...")
            for char in draft.characters:
                desc = char.appearance or char.personality or char.name
                ref_path = seedream.generate_character_reference(char.name, desc)
                if ref_path:
                    char.reference_image = ref_path
                    result["character_refs"][char.name] = ref_path
                    _log(f"[MEDIA] + {char.name}")

        # Step 2: Scene images — parallel with ThreadPoolExecutor
        char_refs = result["character_refs"]
        if seedream.is_configured() and video_script and video_script.panels:
            panels = video_script.panels
            _log(f"[MEDIA] Tao {len(panels)} anh canh (song song)...")

            # Prepare panel data before parallel execution
            prepared = []
            for panel in panels:
                refs = [char_refs[n] for n in panel.characters_in_frame if n in char_refs]
                prompt = panel.image_prompt or panel.description
                filename = f"ch{panel.chapter_number:02d}_p{panel.panel_number:02d}.png"
                prepared.append((panel, prompt, refs, filename))

            completed = 0
            total = len(prepared)
            max_workers = min(5, total)

            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = {
                    executor.submit(seedream.generate_scene, prompt, refs, filename): panel
                    for panel, prompt, refs, filename in prepared
                }
                for future in as_completed(futures):
                    panel = futures[future]
                    completed += 1
                    try:
                        path = future.result()
                        if path:
                            panel.image_path = path
                            result["scene_images"].append(path)
                    except Exception as e:
                        logger.warning(f"Image gen failed for panel {panel.panel_number}: {e}")
                    if completed % 3 == 0 or completed == total:
                        _log(f"[MEDIA] Anh: {completed}/{total}")

        # Step 3: TTS audio — multi-voice when characters available
        if enhanced and enhanced.chapters:
            _log("[MEDIA] Tao audio giong doc...")
            tts = TTSAudioGenerator(voice="female")
            audio_dir = "output/audiobook"

            try:
                use_multivoice = bool(draft.characters)
                voice_map = tts.assign_voices(draft.characters) if use_multivoice else {}

                audio_paths = []
                chapter_durations = {}  # chapter_num -> duration_seconds

                for ch in enhanced.chapters:
                    try:
                        if use_multivoice and voice_map:
                            path, duration = tts.generate_chapter_multivoice(
                                ch.content, ch.chapter_number, voice_map, audio_dir
                            )
                        else:
                            path = tts.generate_chapter_audio(
                                ch.content, ch.chapter_number, audio_dir
                            )
                            duration = TTSAudioGenerator.measure_duration(path) if path else 0.0

                        if path:
                            audio_paths.append(path)
                            chapter_durations[ch.chapter_number] = duration
                            logger.info(f"Audio ch{ch.chapter_number}: {duration:.1f}s")
                    except Exception as e:
                        logger.warning(f"TTS chapter {ch.chapter_number} failed: {e}")

                result["audio_paths"] = audio_paths
                _log(f"[MEDIA] + {len(audio_paths)} file audio")

                # Distribute audio duration across panels per chapter
                if video_script and video_script.panels and chapter_durations:
                    _distribute_panel_durations(video_script.panels, chapter_durations)

            except Exception as e:
                _log(f"[MEDIA] TTS loi: {e}")

        # Step 4: Video composition
        if result["scene_images"] and video_script:
            _log("[MEDIA] Dang ghep video...")
            composer = VideoComposer()
            audio_path = ""
            if result["audio_paths"]:
                merged = composer.merge_chapter_audios(result["audio_paths"])
                if merged:
                    audio_path = merged
            video_path = composer.compose(video_script.panels, audio_path)
            if video_path:
                result["video_path"] = video_path
                _log(f"[MEDIA] + Video: {video_path}")
            else:
                _log("[MEDIA] Khong tao duoc video")

        return result


def _distribute_panel_durations(panels: list, chapter_durations: dict) -> None:
    """Distribute chapter audio duration evenly across its panels."""
    from collections import defaultdict
    chapter_panels = defaultdict(list)
    for panel in panels:
        chapter_panels[panel.chapter_number].append(panel)

    for ch_num, ch_panels in chapter_panels.items():
        duration = chapter_durations.get(ch_num)
        if duration and duration > 0 and ch_panels:
            per_panel = round(duration / len(ch_panels), 2)
            for panel in ch_panels:
                panel.duration_seconds = per_panel
