"""Evaluation runner for LLM-as-judge quality scoring benchmark.

Loads the golden dataset, scores each example (mock or live LLM), then
reports Pearson correlation, MAE, bias, and score distribution per dimension.

Usage:
    python eval_runner.py                  # mock mode (no LLM needed)
    python eval_runner.py --live           # live LLM mode
    python eval_runner.py --out report.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from eval_metrics import evaluate, mock_score

_THIS_DIR = Path(__file__).parent
_DATASET_PATH = _THIS_DIR / "golden_dataset.json"
_DEFAULT_REPORT_PATH = _THIS_DIR / "eval_report.json"


# ---------------------------------------------------------------------------
# Live scorer (lazy import — requires working LLM setup)
# ---------------------------------------------------------------------------

def _live_score(example: dict[str, Any]) -> dict[str, float]:
    """Score a chapter using the real quality scorer."""
    import sys
    # Add project root to sys.path for direct script execution
    project_root = str(_THIS_DIR.parent.parent)
    if project_root not in sys.path:
        sys.path.insert(0, project_root)

    from models.schemas import Chapter  # noqa: PLC0415
    from services.quality_scorer import QualityScorer  # noqa: PLC0415

    scorer = QualityScorer()
    chapter = Chapter(
        chapter_number=1,
        title=example.get("prompt", "")[:80],
        content=example["chapter_text"],
    )
    result = scorer.score_chapter(chapter)
    return {
        "coherence": result.coherence,
        "character_consistency": result.character_consistency,
        "drama": result.drama,
        "writing_quality": result.writing_quality,
    }


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def run_evaluation(
    dataset_path: Path = _DATASET_PATH,
    live: bool = False,
) -> dict[str, Any]:
    """Load golden dataset and run evaluation.

    Args:
        dataset_path: Path to golden_dataset.json.
        live: If True, call real LLM scorer; otherwise use mock.

    Returns:
        Evaluation metrics report dict.
    """
    with open(dataset_path, encoding="utf-8") as f:
        examples = json.load(f)
    score_fn = _live_score if live else mock_score
    return evaluate(examples, score_fn, mode_label="live" if live else "mock")


# ---------------------------------------------------------------------------
# Terminal summary
# ---------------------------------------------------------------------------

def print_summary(report: dict[str, Any]) -> None:
    """Print human-readable evaluation summary to stdout."""
    print(f"\n{'='*60}")
    print("  StoryForge Quality Scorer — Benchmark Report")
    print(f"  Mode: {report['mode'].upper()} | Examples: {report['n_examples']}")
    print(f"{'='*60}")

    om = report["overall_metrics"]
    print(f"\nOverall  Pearson={om['pearson']:+.3f}  MAE={om['mae']:.3f}  "
          f"Bias={om['bias']:+.3f}  "
          f"(LLM avg {om['llm_mean']:.2f} vs Human avg {om['human_mean']:.2f})")

    print(f"\n{'Dimension':<22} {'Pearson':>8} {'MAE':>7} {'Bias':>8} "
          f"{'LLM avg':>9} {'Human avg':>10}")
    print("-" * 70)
    for dim, m in report["dimension_metrics"].items():
        print(f"{dim:<22} {m['pearson']:>+8.3f} {m['mae']:>7.3f} "
              f"{m['bias']:>+8.3f} {m['llm_mean']:>9.2f} {m['human_mean']:>10.2f}")

    ld = report["score_distributions"]["llm_overall"]
    hd = report["score_distributions"]["human_overall"]
    print("\nScore Distribution (LLM vs Human):")
    print(f"  Low  (1-2):  LLM={ld['low_1_2']:3d}  Human={hd['low_1_2']:3d}")
    print(f"  Mid  (2-4):  LLM={ld['mid_2_4']:3d}  Human={hd['mid_2_4']:3d}")
    print(f"  High (4-5):  LLM={ld['high_4_5']:3d}  Human={hd['high_4_5']:3d}")

    bs = report["bias_summary"]
    max_dim = max(bs, key=lambda d: abs(bs[d]))
    direction = "over-scores" if bs[max_dim] > 0 else "under-scores"
    print(f"\nBias Alert: LLM most {direction} '{max_dim}' (mean diff {bs[max_dim]:+.3f})")
    print(f"{'='*60}\n")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Run quality scorer benchmark")
    parser.add_argument("--live", action="store_true", help="Use real LLM (default: mock)")
    parser.add_argument("--dataset", default=str(_DATASET_PATH))
    parser.add_argument("--out", default=str(_DEFAULT_REPORT_PATH))
    args = parser.parse_args()

    report = run_evaluation(dataset_path=Path(args.dataset), live=args.live)
    print_summary(report)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"Report saved to {out_path}")


if __name__ == "__main__":
    main()
