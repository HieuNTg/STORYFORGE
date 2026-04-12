---
phase: 4
title: "Scene-Level Enhancement + Dialogue Subtext + Thematic Resonance"
status: completed
effort: 3h
depends_on: [1, 2, 3]
---

# Phase 4: Scene-Level Enhancement + Dialogue Subtext + Thematic Resonance

## Context Links
- Plan: [plan.md](plan.md)
- Phases 1-3: earlier phases
- Enhancer: `pipeline/layer2_enhance/enhancer.py` (314 lines)
- Scene decomposer (L1): `pipeline/layer1_story/scene_decomposer.py` (170 lines)
- Prompts: `services/prompts/analysis_prompts.py`, `revision_prompts.py`

## Overview
Three enhancements to the story enhancement pipeline: (1) decompose chapters into scenes, score each, enhance only weak scenes; (2) generate dialogue with explicit says-vs-means subtext layer; (3) extract and track central theme + recurring motifs.

## Key Insights
- L2 enhancer rewrites entire chapter as blob, truncated to 6000 chars (enhancer.py:96)
- L1 `scene_decomposer.py` already decomposes outlines into 3-5 scenes — reusable for L2
- `ENHANCE_CHAPTER` prompt says "doi thoai sac ben" but has no structured analysis of what characters say vs mean
- No concept of "theme" anywhere in L2 — enhancement can accidentally drift from story's central message
- `_find_weak_chapters()` scores entire chapters — scene-level scoring would be more granular

---

## Enhancement #5: Scene-Level Enhancement

### New file: `pipeline/layer2_enhance/scene_enhancer.py` (~180 lines)

```python
class SceneScore(BaseModel):
    scene_number: int
    drama_score: float = 0.5
    weak_points: list[str] = Field(default_factory=list)
    strong_points: list[str] = Field(default_factory=list)
    needs_enhancement: bool = False

class SceneEnhancer:
    def __init__(self): self.llm = LLMClient()

    def decompose_chapter_content(self, chapter: Chapter) -> list[dict]:
        """Decompose written chapter content (not outline) into scenes.
        Uses LLM to identify scene boundaries in existing text."""

    def score_scenes(self, scenes: list[dict], genre: str) -> list[SceneScore]:
        """Score each scene for drama quality. Returns list of SceneScore."""

    def enhance_weak_scenes(self, chapter: Chapter, scenes: list[dict],
                            scores: list[SceneScore], sim_result, genre: str) -> Chapter:
        """Re-enhance only scenes with needs_enhancement=True. Stitch back together."""

    def enhance_chapter_by_scenes(self, chapter: Chapter, sim_result, genre: str, draft=None) -> Chapter:
        """Full pipeline: decompose -> score -> enhance weak -> stitch."""
```

### Integration point:
- Called from `StoryEnhancer.enhance_chapter()` instead of rewriting entire chapter
- Fallback: if scene decomposition fails, fall through to existing blob enhancement

### Key difference from L1 scene_decomposer:
- L1 decomposes **outlines** before writing
- L2 decomposes **written content** after writing, for scoring and targeted enhancement

---

## Enhancement #6: Dialogue Subtext Layer

### New file: `pipeline/layer2_enhance/dialogue_subtext.py` (~150 lines)

```python
class DialogueLine(BaseModel):
    character: str
    says: str                  # What they literally say
    means: str                 # What they actually mean/want
    subtext_type: str          # "deflection" | "half_truth" | "loaded_silence" | "misdirection" | "genuine"
    tension_contribution: float = 0.0

class DialogueSubtextAnalyzer:
    def __init__(self): self.llm = LLMClient()

    def analyze_dialogue(self, chapter_content: str, characters: list[Character]) -> list[DialogueLine]:
        """Extract dialogue lines and analyze says-vs-means."""

    def generate_subtext_guidance(self, psychology_map: dict[str, CharacterPsychology],
                                   knowledge_state: dict[str, list[str]]) -> str:
        """Generate per-character dialogue guidance for enhancement prompt.
        Uses psychology (fears, defenses) and knowledge (what they know/don't know)."""

    def format_for_prompt(self, guidance: str) -> str:
        """Format subtext guidance for injection into ENHANCE_CHAPTER prompt."""
```

### Prompt: `DIALOGUE_SUBTEXT_GUIDANCE`
```python
DIALOGUE_SUBTEXT_GUIDANCE = """Phân tích đối thoại trong đoạn văn sau. Với MỖI câu thoại quan trọng, chỉ ra:

NỘI DUNG:
{content}

NHÂN VẬT VÀ TÂM LÝ:
{character_psychology}

KIẾN THỨC CỦA TỪNG NHÂN VẬT:
{knowledge_state}

Trả về JSON:
{{
  "dialogue_analysis": [
    {{
      "character": "tên",
      "says": "câu nói nguyên văn",
      "means": "ý nghĩa thực sự / điều muốn đạt được",
      "subtext_type": "deflection/half_truth/loaded_silence/misdirection/genuine",
      "tension_contribution": 0.7
    }}
  ],
  "enhancement_guidance": "hướng dẫn cụ thể để cải thiện đối thoại: thêm im lặng đầy ý nghĩa, lời nói nửa vời, né tránh..."
}}"""
```

### Integration:
- `DialogueSubtextAnalyzer.generate_subtext_guidance()` called before `enhance_chapter()`
- Guidance injected into ENHANCE_CHAPTER prompt as a new section
- Uses psychology data from Phase 1 and knowledge data from Phase 2

---

## Enhancement #7: Thematic Resonance Tracking

### New file: `pipeline/layer2_enhance/thematic_tracker.py` (~150 lines)

```python
class ThemeProfile(BaseModel):
    central_theme: str                    # e.g., "sự cứu chuộc qua hy sinh"
    recurring_motifs: list[str]           # e.g., ["lửa", "bóng tối", "máu"]
    symbolic_items: list[str]             # e.g., ["thanh kiếm gãy", "chiếc nhẫn"]
    thematic_questions: list[str]         # e.g., ["Hy sinh có đáng không?"]

class ChapterThematicScore(BaseModel):
    chapter_number: int
    theme_alignment: float = 0.5         # 0-1: how well chapter reinforces theme
    motifs_present: list[str] = Field(default_factory=list)
    motifs_missing: list[str] = Field(default_factory=list)
    drift_warning: str = ""              # If chapter drifts from theme

class ThematicTracker:
    def __init__(self): self.llm = LLMClient()

    def extract_theme(self, draft: StoryDraft) -> ThemeProfile:
        """Extract central theme + motifs from L1 output (synopsis, premise, chapters)."""

    def score_chapter_theme(self, chapter: Chapter, theme: ThemeProfile) -> ChapterThematicScore:
        """Score how well a chapter reinforces the theme."""

    def generate_thematic_guidance(self, theme: ThemeProfile, chapter_score: ChapterThematicScore) -> str:
        """Generate guidance for enhancement: which motifs to weave in, drift to correct."""

    def format_for_prompt(self, guidance: str) -> str:
        """Format thematic guidance for ENHANCE_CHAPTER prompt injection."""
```

### Prompt: `EXTRACT_THEME`
```python
EXTRACT_THEME = """Phân tích chủ đề trung tâm của truyện sau:

TIÊU ĐỀ: {title}
THỂ LOẠI: {genre}
TÓM TẮT: {synopsis}
TIỀN ĐỀ CHỦ ĐỀ: {premise}

NHÂN VẬT:
{characters}

Trả về JSON:
{{
  "central_theme": "chủ đề trung tâm (1 câu)",
  "recurring_motifs": ["biểu tượng/hình ảnh lặp lại"],
  "symbolic_items": ["vật thể mang ý nghĩa biểu tượng"],
  "thematic_questions": ["câu hỏi chủ đề truyện đặt ra cho người đọc"]
}}"""

SCORE_CHAPTER_THEME = """Đánh giá mức độ chương này củng cố chủ đề trung tâm.

CHỦ ĐỀ: {central_theme}
MOTIF CẦN CÓ: {motifs}
BIỂU TƯỢNG: {symbols}

NỘI DUNG CHƯƠNG:
{content}

Trả về JSON:
{{
  "theme_alignment": 0.7,
  "motifs_present": ["motif đã xuất hiện"],
  "motifs_missing": ["motif nên thêm vào"],
  "drift_warning": "cảnh báo nếu chương lệch chủ đề (hoặc rỗng nếu ổn)"
}}"""
```

### Integration:
- `ThematicTracker.extract_theme()` called once at start of L2 enhancement
- `score_chapter_theme()` called per chapter before enhancement
- Guidance injected into ENHANCE_CHAPTER prompt

---

## Implementation Steps

### Scene-Level Enhancement (#5)

1. **Create `pipeline/layer2_enhance/scene_enhancer.py`**:
   - `SceneEnhancer.__init__()` — `LLMClient()`
   - `decompose_chapter_content(chapter)` — LLM prompt: "Chia nội dung chương thành 3-5 cảnh. Trả về JSON với ranh giới văn bản." Returns list of `{"scene_number", "content", "start_marker", "end_marker", "characters_present"}`
   - `score_scenes(scenes, genre)` — for each scene, call LLM with QUICK_DRAMA_CHECK-like prompt, return `SceneScore`. Mark `needs_enhancement = True` if `drama_score < 0.6`
   - `enhance_weak_scenes(chapter, scenes, scores, sim_result, genre)` — for each weak scene: build focused enhancement prompt with scene content + relevant events. Stitch enhanced scenes back with strong scenes unchanged.
   - `enhance_chapter_by_scenes(chapter, sim_result, genre, draft)` — orchestrate: decompose -> score -> enhance_weak -> stitch. Return enhanced Chapter.

2. **Modify `enhancer.py` `enhance_chapter()`** (line 30):
   - Add import: `from pipeline.layer2_enhance.scene_enhancer import SceneEnhancer`
   - Before the existing enhancement logic (line 46), try scene-level enhancement:
     ```python
     try:
         scene_enhancer = SceneEnhancer()
         return scene_enhancer.enhance_chapter_by_scenes(chapter, sim_result, genre, draft)
     except Exception as e:
         logger.warning(f"Scene-level enhancement failed, falling back to blob: {e}")
     # ... existing blob enhancement below ...
     ```

3. **Add prompt** `DECOMPOSE_CHAPTER_CONTENT` to `services/prompts/layer2_enhanced_prompts.py`:
   ```
   DECOMPOSE_CHAPTER_CONTENT = """Chia nội dung chương sau thành 3-5 cảnh riêng biệt...
   Trả về JSON: {{"scenes": [{{"scene_number": 1, "content": "nội dung cảnh", "characters_present": [...]}}]}}"""
   ```

### Dialogue Subtext (#6)

4. **Create `pipeline/layer2_enhance/dialogue_subtext.py`**:
   - `DialogueSubtextAnalyzer.__init__()` — `LLMClient()`
   - `analyze_dialogue(chapter_content, characters)` — LLM call with DIALOGUE_SUBTEXT_GUIDANCE, parse into `DialogueLine` list
   - `generate_subtext_guidance(psychology_map, knowledge_state)` — build per-character guidance string: "Character X fears Y, doesn't know Z — their dialogue should deflect when topic Z comes up"
   - `format_for_prompt(guidance)` — wrap in section header for ENHANCE_CHAPTER injection

5. **Add `DIALOGUE_SUBTEXT_GUIDANCE` prompt** to `services/prompts/layer2_enhanced_prompts.py`

6. **Modify `scene_enhancer.py` `enhance_weak_scenes()`**:
   - Before enhancing each weak scene, call `dialogue_analyzer.generate_subtext_guidance()` with relevant characters' psychology + knowledge
   - Inject subtext guidance into the scene enhancement prompt

### Thematic Resonance (#7)

7. **Create `pipeline/layer2_enhance/thematic_tracker.py`**:
   - `ThematicTracker.__init__()` — `LLMClient()`
   - `extract_theme(draft)` — use EXTRACT_THEME prompt with draft.title, draft.genre, draft.synopsis, draft.premise, characters text. Parse into `ThemeProfile`. Use `model_tier="cheap"`.
   - `score_chapter_theme(chapter, theme)` — use SCORE_CHAPTER_THEME prompt with theme data + chapter content[:3000]. Parse into `ChapterThematicScore`.
   - `generate_thematic_guidance(theme, chapter_score)` — format missing motifs + drift warning into enhancement guidance string
   - `format_for_prompt(guidance)` — wrap in section header

8. **Add `EXTRACT_THEME` and `SCORE_CHAPTER_THEME` prompts** to `services/prompts/layer2_enhanced_prompts.py`

9. **Wire thematic tracking into `enhancer.py`**:
   - In `enhance_story()` (line 127): before enhancing chapters, call `thematic_tracker.extract_theme(draft)` once
   - Pass `ThemeProfile` to `enhance_chapter()` as new optional parameter
   - In `enhance_chapter()`: if theme provided, call `score_chapter_theme()` and inject thematic guidance into prompt

10. **Update `services/prompts/__init__.py`**: import and export all new prompts

## Todo
- [x] Create scene_enhancer.py with SceneEnhancer class
- [x] Create dialogue_subtext.py with DialogueSubtextAnalyzer
- [x] Create thematic_tracker.py with ThematicTracker
- [x] Add DECOMPOSE_CHAPTER_CONTENT prompt
- [x] Add DIALOGUE_SUBTEXT_GUIDANCE prompt
- [x] Add EXTRACT_THEME and SCORE_CHAPTER_THEME prompts
- [x] Wire SceneEnhancer into enhancer.enhance_chapter (with fallback)
- [x] Wire DialogueSubtextAnalyzer into scene enhancement
- [x] Wire ThematicTracker.extract_theme into enhance_story
- [x] Wire thematic scoring into per-chapter enhancement
- [x] Update prompts/__init__.py

## Success Criteria
- Chapters enhanced at scene level: strong scenes preserved, weak scenes improved
- Enhancement prompt includes dialogue subtext guidance (says vs means)
- Theme extracted from story and tracked across chapters
- Thematic drift detected and corrected in enhancement
- All three enhancements are non-fatal: failure falls back to existing behavior
- No increase in chapter count or structural changes

## Risk Assessment
- **Scene decomposition of content**: More complex than outline decomposition. Mitigate: simple approach (split by scene markers/paragraph groups), not perfect boundary detection.
- **LLM cost for scene scoring**: N scenes x M chapters. Mitigate: only decompose chapters that need it (after initial drama check), use model_tier="cheap" for scoring.
- **Theme extraction quality**: LLM may extract vague themes. Mitigate: use premise data from L1 if available, fall back to empty guidance.
- **Dialogue analysis overhead**: One extra LLM call per weak scene. Mitigate: only analyze scenes being enhanced, not all scenes.

## Security Considerations
- No new external dependencies
- All data flows through existing LLM client

## Next Steps
Phase 5 wires all enhancements into the orchestrator and updates quality scoring.
