# Eval Pipeline Specification

**Version:** 1.0 — Sprint 14
**Status:** Draft

---

## 1. Human Eval Dataset Schema

Stories submitted for human evaluation are stored as JSON records conforming to:

```json
{
  "story_id":   "uuid-string",
  "evaluator_id": "user-uuid or evaluator-email",
  "scores": {
    "coherence":             3,
    "character_consistency": 4,
    "engagement":            5,
    "language_quality":      4
  },
  "comments":  "Free-text observations (optional, max 2 000 chars)",
  "timestamp": "2026-04-02T10:30:00+00:00"
}
```

### Field constraints
| Field                          | Type    | Range / Format            |
|--------------------------------|---------|---------------------------|
| `story_id`                     | string  | UUID v4                   |
| `evaluator_id`                 | string  | UUID v4 or email          |
| `scores.coherence`             | integer | 1–5                       |
| `scores.character_consistency` | integer | 1–5                       |
| `scores.engagement`            | integer | 1–5                       |
| `scores.language_quality`      | integer | 1–5                       |
| `comments`                     | string  | optional, ≤ 2 000 chars   |
| `timestamp`                    | string  | ISO-8601 with timezone    |

---

## 2. Automated Metrics

### 2.1 Narrative Coherence Score (LLM self-eval)
- **Method:** Send story synopsis + last chapter to the generation model with a structured prompt asking for a coherence score 0.0–1.0.
- **Prompt:** `"Rate the logical consistency of this story (plot continuity, cause-effect, timeline). Return JSON: {\"coherence\": <float 0-1>, \"issues\": [<string>]}"`
- **Output field:** `auto_coherence` ∈ [0.0, 1.0]

### 2.2 Character Name Consistency (regex)
- Extract all character names from the story config.
- Scan chapter content with: `re.findall(r'\b<name>\b', content, re.IGNORECASE)` for each name.
- Flag any chapter where a declared character has zero mentions (possible continuity gap).
- **Output field:** `character_mentions` → dict `{name: [chapter_numbers]}`

### 2.3 Chapter Length Variance
- Compute word counts per chapter: `wc[i] = len(chapter.content.split())`
- Compute coefficient of variation: `cv = std(wc) / mean(wc)`
- **Acceptable range:** cv ≤ 0.35 (>35% variance flags uneven pacing)
- **Output field:** `chapter_length_cv` ∈ [0.0, ∞)

### 2.4 Vietnamese Language Purity
- Tokenise with whitespace split; apply heuristic: a token is Vietnamese if it contains at least one Vietnamese diacritic character (Unicode blocks: U+00C0–U+024F, U+1E00–U+1EFF) or is a common ASCII word ≤ 3 chars (function words).
- **Formula:** `vi_purity = vi_tokens / total_tokens`
- **Target:** ≥ 0.80 for stories with `genre != "fantasy_en"`
- **Output field:** `vi_purity` ∈ [0.0, 1.0]

---

## 3. Data Collection Flow

```
Story Generated
      │
      ▼
[Auto-Score Service]  ──► stores auto_coherence, character_mentions,
      │                    chapter_length_cv, vi_purity in eval DB
      │
      ▼
Human Eval Form (optional)
      │  evaluator fills in 4 scores + comments
      ▼
Eval Record persisted (JSON schema §1)
      │
      ▼
Aggregate Dashboard
      │  shows per-story final_score, trend charts, flagged issues
```

### Trigger points
1. **Automatic:** fires after every successful pipeline Layer 1 completion.
2. **Human:** evaluator visits `/eval/{story_id}` form; submission stored via `POST /api/v1/eval`.
3. **Dashboard:** `GET /api/v1/eval/summary` returns aggregated scores for admin view.

---

## 4. Scoring Formula

When **no human eval** is available:
```
final_score = auto_score
```

When **human eval** is available:
```
final_score = 0.4 * auto_score + 0.6 * human_avg
```

Where:
- `auto_score = (auto_coherence + char_consistency_ok + chapter_pacing_ok + vi_purity) / 4` normalised to [0, 1]
- `human_avg = mean(coherence, character_consistency, engagement, language_quality) / 5` normalised to [0, 1]
- `char_consistency_ok` = 1.0 if all characters appear in ≥ 50% of chapters, else 0.0
- `chapter_pacing_ok` = max(0, 1 - chapter_length_cv)

### Example
| Metric              | Value |
|---------------------|-------|
| auto_coherence      | 0.80  |
| char_consistency_ok | 1.00  |
| chapter_pacing_ok   | 0.75  |
| vi_purity           | 0.88  |
| auto_score          | 0.858 |
| human_avg (4 scores = 4.0/5.0) | 0.800 |
| **final_score**     | **0.823** |

---

## 5. Storage

- Eval records: `data/evals/{story_id}.jsonl` (one JSON object per line)
- Auto scores: appended to story metadata in pipeline output JSON
- Aggregated dashboard data: computed on-the-fly from JSONL files (no separate DB table required in MVP)
