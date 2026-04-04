"""Bridge between PromptManager and ABTestManager for prompt A/B testing."""

from typing import Optional

from services.ab_testing import manager as ab_manager


class PromptABBridge:
    """Connects PromptManager with ABTestManager for A/B testing prompt variants."""

    def __init__(self) -> None:
        self._prompt_experiments: dict[str, str] = {}  # prompt_name -> experiment_id

    def _get_prompt_manager(self):
        """Lazy import to avoid circular dependency and support parallel agent build."""
        from services.prompt_manager import prompt_manager  # noqa: PLC0415
        return prompt_manager

    def create_prompt_experiment(self, prompt_name: str, variant_versions: list[str]) -> str:
        """Create an A/B experiment for a prompt, using version strings as variants.

        Args:
            prompt_name: Name of the prompt (e.g. ``"write_chapter"``).
            variant_versions: List of version strings to test (e.g. ``["v1", "v2"]``).

        Returns:
            experiment_id assigned by ABTestManager.
        """
        experiment_name = f"prompt:{prompt_name}"
        experiment_id = ab_manager.create_experiment(experiment_name, variant_versions)
        self._prompt_experiments[prompt_name] = experiment_id
        return experiment_id

    def get_prompt(self, prompt_name: str, session_id: str, **kwargs) -> str:
        """Return a formatted prompt, routing to the A/B variant when active.

        If an experiment exists for ``prompt_name``, the variant (version) is
        determined deterministically from ``session_id``.  Otherwise the latest
        version is returned.

        Args:
            prompt_name: Prompt to retrieve.
            session_id: Pipeline session identifier used for variant assignment.
            **kwargs: Format arguments forwarded to ``prompt_manager.get``.

        Returns:
            Formatted prompt string.
        """
        pm = self._get_prompt_manager()
        experiment_id = self._prompt_experiments.get(prompt_name)
        if experiment_id:
            try:
                version = ab_manager.assign_variant(experiment_id, session_id)
                return pm.get(prompt_name, version=version, **kwargs)
            except (KeyError, Exception):
                pass  # fall through to latest on any error
        return pm.get(prompt_name, version="latest", **kwargs)

    def record_quality(self, prompt_name: str, session_id: str, score: float) -> None:
        """Record a quality score for the active experiment of a prompt.

        Args:
            prompt_name: Prompt being evaluated.
            session_id: Session that produced the output.
            score: Quality score (e.g. 0.0–1.0, or arbitrary float).
        """
        experiment_id = self._prompt_experiments.get(prompt_name)
        if experiment_id is None:
            return
        ab_manager.record_result(experiment_id, session_id, metric="quality", value=score)

    def get_experiment_results(self, prompt_name: str) -> dict:
        """Return per-variant aggregated results for a prompt's experiment.

        Args:
            prompt_name: Prompt whose experiment results to retrieve.

        Returns:
            Dict with ``experiment_id``, ``prompt_name``, and per-variant ``results``.

        Raises:
            KeyError: If no experiment is registered for ``prompt_name``.
        """
        experiment_id = self._prompt_experiments.get(prompt_name)
        if experiment_id is None:
            raise KeyError(f"No active experiment for prompt {prompt_name!r}")
        results = ab_manager.get_results(experiment_id)
        return {
            "experiment_id": experiment_id,
            "prompt_name": prompt_name,
            "results": results,
        }

    def list_active_experiments(self) -> list[dict]:
        """Return metadata for all active prompt experiments.

        Returns:
            List of dicts with ``prompt_name`` and ``experiment_id`` merged with
            ABTestManager experiment metadata.
        """
        all_experiments = {e["id"]: e for e in ab_manager.list_experiments()}
        active = []
        for prompt_name, experiment_id in self._prompt_experiments.items():
            entry = {"prompt_name": prompt_name, "experiment_id": experiment_id}
            if experiment_id in all_experiments:
                entry.update(all_experiments[experiment_id])
            active.append(entry)
        return active

    def get_active_experiment_id(self, prompt_name: str) -> Optional[str]:
        """Return the experiment_id for a prompt, or None if no active experiment."""
        return self._prompt_experiments.get(prompt_name)


# Module-level singleton
bridge = PromptABBridge()
