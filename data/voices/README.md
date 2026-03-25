# Reference Audio Files

Place reference audio files here for TTS voice cloning (XTTS v2).

## Format Requirements

- **Format:** WAV (preferred) or MP3
- **Duration:** 6–30 seconds of clean speech
- **Sample rate:** 22050 Hz or higher
- **Channels:** Mono or stereo
- **Language:** Match the target language (Vietnamese recommended)
- **Quality:** No background noise, clear pronunciation

## Naming Convention

Name files after the character they represent:

```
data/voices/
├── narrator.wav        # Default narrator voice
├── CharacterName.wav   # Per-character voice
└── ...
```

## Config Mapping

Set character voices in `config.json` under `pipeline.character_voice_map`:

```json
{
  "character_voice_map": {
    "Lý Thần": "data/voices/ly_than.wav",
    "narrator": "data/voices/narrator.wav"
  }
}
```
