# Emotion Classifier Options for StoryForge

## Current State

StoryForge uses a rule-based emotion classifier (`services/emotion_classifier.py`) with
regex patterns and keyword lists to detect emotion categories in story text.

## Option Comparison

| Method | Accuracy (est.) | Latency | Dependencies | Vietnamese Support | Effort |
|---|---|---|---|---|---|
| **Rule-based (current)** | ~60-65% | <1ms | None | Manual keyword lists | Zero (already exists) |
| **underthesea Vietnamese NLP** | ~72-78% | 5-20ms | `underthesea` (~50MB) | Native, purpose-built | Low (1-2 days) |
| **PhoBERT-sentiment** | ~85-91% | 50-200ms (CPU), 5-30ms (GPU) | `transformers`, `torch` (~2GB) | State-of-art Vietnamese | High (3-5 days + infra) |

## Detailed Notes

### Rule-based (current)
- Pros: zero dependencies, zero latency, fully offline, easy to extend with new keywords
- Cons: brittle for novel phrasing, ~60% accuracy ceiling, misses nuanced context
- Best for: zero-dependency deployments, serverless, edge

### underthesea
- Vietnamese NLP toolkit with pre-trained sentiment/emotion models
- Includes word segmentation critical for Vietnamese (no spaces between morphemes)
- Pros: purpose-built for Vietnamese, reasonable accuracy gain, small footprint
- Cons: requires pip install, larger docker image, slower than rule-based
- Best for: production where moderate accuracy + low infra cost is acceptable

### PhoBERT-sentiment
- BERT-based transformer pre-trained on Vietnamese corpus (VinAI Research)
- Fine-tuned variants available for sentiment/emotion on UIT-VSFC dataset
- Pros: SOTA Vietnamese accuracy (~88% on benchmark datasets), context-aware
- Cons: large model weights (~2GB), requires `torch`+`transformers`, needs GPU for fast inference
- Best for: high-quality pipelines where accuracy > speed

## Recommendation

- **Accuracy priority** → PhoBERT: use `vinai/phobert-base` with fine-tuned sentiment head
- **Zero-dependency** → Keep rule-based: extend keyword lists per genre
- **Middle ground** → underthesea: best effort-to-accuracy ratio

## Migration Path (Rule-based → PhoBERT)

1. Add `STORYFORGE_EMOTION_BACKEND=phobert|underthesea|rules` env var
2. Create `services/emotion_backends/` with `rules.py`, `underthesea_backend.py`, `phobert_backend.py`
3. `emotion_classifier.py` reads env var and delegates to backend
4. Ship rule-based as default; PhoBERT opt-in via env var
5. Benchmark on 200-sample Vietnamese story corpus before switching default
6. PhoBERT model can be cached in `data/models/phobert/` to avoid re-download
