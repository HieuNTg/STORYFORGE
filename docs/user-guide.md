# StoryForge User Guide

StoryForge is a three-layer AI pipeline that turns a story idea into a full novel draft — complete with character development, dramatic enhancement, and video storyboard output.

---

## Getting Started

### 1. Open the App

Go to **http://localhost:7860** in your browser after starting StoryForge.

### 2. Configure Your LLM Provider

Before generating, tell StoryForge which AI model to use:

1. Click the **Settings** tab (or gear icon).
2. Enter your **API Key**.
3. Set the **Base URL** for your provider (default is OpenAI; see [self-hosting.md](./self-hosting.md) for other providers).
4. Choose a **Model** (e.g. `gpt-4o-mini`, `gemini-2.0-flash`, `llama3.2`).
5. Click **Save**.

### 3. Generate Your First Story

1. Open the **Pipeline** tab.
2. Select a **Genre** from the dropdown.
3. Type your **Story Idea** — a sentence or two is enough to start.
4. Choose a **Preset** (Beginner is fastest).
5. Click **Generate** and watch the pipeline run.

Stories are saved automatically to the `output/` directory.

---

## Understanding the Pipeline

StoryForge processes your idea through three sequential layers. Each builds on the previous one.

### Layer 1: Story Draft

**What it does**: Generates the complete raw story.

- Creates a cast of characters (protagonist, antagonist, supporting roles) with personalities, backgrounds, and motivations.
- Builds a world setting: era, locations, and rules of the universe.
- Writes a chapter-by-chapter outline.
- Writes each chapter in full, maintaining a rolling context of character states and plot events so the story stays consistent across chapters.

**Output**: A complete draft with every chapter written.

### Layer 2: Drama Enhancement

**What it does**: AI agents review and intensify the story.

- A team of specialized agents (CharacterSpecialist, DramaCritic, DialogueExpert, ContinuityChecker, EditorInChief) each analyze the draft.
- Agents debate weak points and suggest improvements.
- Chapters below the quality threshold are automatically revised.
- The result is a more dramatically engaging version of the original draft.

**Output**: Enhanced story with improved pacing, dialogue, and emotional arcs.

### Layer 3: Video Storyboard

**What it does**: Breaks the story into visual scenes.

- Generates shot-by-shot storyboard metadata for each chapter.
- Writes narration lines and image-generation prompts per shot.
- Packages everything for CapCut import or manual video editing.

**Output**: SRT file, voiceover script, image prompts, and CapCut JSON bundle (ZIP).

---

## Genre Guide

The genre you choose shapes the tone, pacing, and emphasis of the story. StoryForge includes 12 built-in genre profiles:

| Genre | Best For |
|-------|----------|
| **Tien Hiep** (Xianxia) | Cultivation, martial arts, immortality arcs |
| **Huyen Huyen** (Xuanhuan) | Fantasy worlds, magic systems, adventure |
| **Do Thi** (Urban) | Modern city life, romance, contemporary drama |
| **Romance** | Emotional relationships, slow-burn arcs |
| **Mystery** | Plot twists, clue-based pacing, suspense |
| **Thriller** | High-stakes tension, fast pacing, action beats |
| **Historical** | Period accuracy, political intrigue |
| **Sci-Fi** | World-building, technology concepts, exploration |
| **Horror** | Atmosphere, dread, psychological tension |
| **Comedy** | Light tone, comedic timing, banter |
| **Slice of Life** | Character-driven, quiet moments, realism |
| **Literary** | Prose quality focus, thematic depth |

If you are unsure, start with the genre closest to the story you have in mind. You can regenerate with a different genre to compare.

---

## Quality Scores

After generation, the **Quality** tab shows scores for every chapter and the story overall.

### Four Dimensions

| Dimension | What It Measures |
|-----------|-----------------|
| **Coherence** | Plot logic, cause-and-effect, no contradictions |
| **Character Consistency** | Characters behave true to their established personalities |
| **Drama** | Emotional impact, conflict intensity, tension |
| **Writing Quality** | Prose style, sentence variety, vocabulary |

### Score Range

All scores are on a **1–5 scale**:
- 1–2: Needs significant work
- 3: Acceptable baseline
- 4: Good, above average
- 5: Excellent

The overall score is the average of all four dimensions.

### Quality Gate

In **Advanced** and **Pro** presets, a quality gate runs between Layer 1 and Layer 2. If the average chapter score is below the threshold (default 3.0), the pipeline pauses and reports which chapters need attention. You can lower the threshold in Settings if you want to proceed regardless.

---

## Presets

Presets configure the pipeline trade-off between speed and output quality.

### Beginner
- **Time**: ~5 minutes
- Chapter self-review: off
- Agent debate: off
- Smart revision: off
- Quality gate: off
- **Best for**: Quick prototypes, testing your story idea

### Advanced
- **Time**: ~15 minutes
- Chapter self-review: on (threshold 3.0)
- Agent debate: lite mode
- Smart revision: on
- Quality gate: on
- **Best for**: Most users who want good quality without long waits

### Pro
- **Time**: ~30 minutes
- Chapter self-review: on (threshold 3.5)
- Agent debate: full 3-round protocol
- Smart revision: on (threshold 3.5)
- Quality gate: on (stricter threshold)
- **Best for**: Final drafts, publishing-ready output

You can also customize individual settings in the **Settings** tab after selecting a preset.

---

## Exports

After generation, open the **Export** tab to download your story.

### Available Formats

| Format | Description |
|--------|-------------|
| **PDF** | Full Vietnamese font support (NotoSans). Good for printing or sharing. |
| **EPUB** | E-reader compatible (Kindle, Kobo, Apple Books). Includes chapter navigation. |
| **HTML** | Self-contained web reader with dark/light mode toggle and chapter navigation. Works offline. |
| **TXT / MD** | Plain text and Markdown, for editing in any text editor. |
| **ZIP** | All formats bundled together in one download. |
| **Video (ZIP)** | Storyboard bundle: SRT, voiceover script, image prompts, CapCut JSON, CSV. |

### Video Export and CapCut

The video ZIP is designed for import into CapCut:
1. Export the Video ZIP from the Export tab.
2. In CapCut, use **Import** → select the `capcut.json` file.
3. The timeline, shots, and narration are pre-structured for you.

---

## Tips for Better Stories

**Be specific with your story idea.** Instead of "a martial arts story," try "a young farmer discovers he has ice cultivation roots and must earn his place in a prestigious sect that looks down on his background." The more detail you give, the more focused the opening chapters will be.

**Match genre to idea.** A romance-focused story generates better with the Romance or Urban genre than with Thriller, even if both could technically work.

**Use Advanced or Pro preset for anything you plan to share.** The Beginner preset is fast but skips the revision and debate loops that significantly improve drama and consistency.

**Let the pipeline run without interruption.** Each layer feeds into the next. If the browser tab closes, the generation can be resumed from the last checkpoint — look for the **Resume** button when you reopen the app.

**Try the HTML export for reading.** The HTML reader has a clean dark mode and chapter navigation, making it much more comfortable to read than a raw text file.

---

## FAQ

**How long does generation take?**

Depends on chapter count, word count per chapter, preset, and your LLM provider's speed.
- Beginner preset, 5 chapters: ~5 minutes with GPT-4o-mini
- Pro preset, 10 chapters: 25–40 minutes
- Local Ollama models are slower (2–5x) depending on your GPU.

**Can I use free LLM models?**

Yes. OpenRouter offers several free-tier models (e.g. `mistralai/mistral-7b-instruct:free`). Quality will be lower than GPT-4o or Gemini Pro, but the pipeline works. Ollama is also free and fully local.

**How do I generate in English?**

In the **Settings** tab, set **Language** to `en`. All prompts, chapter text, and system messages will switch to English. The default is Vietnamese (`vi`).

**How do I resume an interrupted generation?**

If the pipeline stops mid-run (network drop, browser close, etc.), reopen the app at http://localhost:7860. If a checkpoint was saved, a **Resume** button will appear on the Pipeline tab. Click it to continue from where the pipeline stopped. Checkpoints are saved after each completed chapter.

**Why are some chapters blank or very short?**

Usually caused by LLM rate limits or timeouts. Check the quality score for that chapter — a score of 1 with very short content means the LLM returned an empty response. Try regenerating that chapter using the **Continue** tab, or increase `STORYFORGE_TEMPERATURE` slightly in Settings.

**How do I change characters mid-story?**

Open the **Continue** tab after generation. Use the character editor to modify name, personality, background, or relationships. Then click **Re-enhance** to have Layer 2 agents re-process the affected chapters with the updated character profile.
