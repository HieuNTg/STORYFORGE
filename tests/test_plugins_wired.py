"""Sprint 3 — the plugin hooks were decoration, and the /api/v1 mirror was dead weight.

`plugin_manager` exposes eleven hook call sites on the hot path — every quality
score, every genre-rule lookup, every export format — but `load_all()` was
never called anywhere in production. The plugin list was therefore always
empty, so all eleven were no-ops that still cost a call and a try/except. The
repo ships `plugins/README.md` and an example plugin, documenting an extension
point that could not fire.

Wiring it in has one trap, which is why the loader changed too: the shipped
`example-custom-genre.py` registers a genre *and* adds a bonus in `on_score`.
Loading it at startup would have quietly changed every user's quality scores
because the repo ships documentation. Examples are skipped by name; copy one to
enable it.

Separately, `api/v1/` re-mounted nine routers under a second prefix nobody
called, and installed a BaseHTTPMiddleware that ran on every single request to
set a Deprecation header on those unused paths.
"""

import inspect
from pathlib import Path

import pytest

from plugins.loader import PluginManager


PLUGIN_SOURCE = '''
from plugins.base import StoryForgePlugin


class {cls}(StoryForgePlugin):
    name = "{name}"
    version = "1.0"

    def register(self):
        pass
'''


def _write_plugin(directory: Path, filename: str, cls: str, name: str) -> None:
    (directory / filename).write_text(
        PLUGIN_SOURCE.format(cls=cls, name=name), encoding="utf-8"
    )


class TestExamplesAreNotLoaded:
    def test_a_shipped_example_does_not_register_itself(self, tmp_path):
        """It modifies on_score; loading it would change everyone's numbers."""
        _write_plugin(tmp_path, "example-custom-genre.py", "ExampleP", "example")

        mgr = PluginManager()
        mgr.load_all(tmp_path)

        assert mgr._plugins == []

    def test_the_underscore_spelling_is_skipped_too(self, tmp_path):
        _write_plugin(tmp_path, "example_other.py", "ExampleOther", "example-other")

        mgr = PluginManager()
        mgr.load_all(tmp_path)

        assert mgr._plugins == []

    def test_copying_an_example_to_your_own_name_enables_it(self, tmp_path):
        """The documented way to turn an example on must actually work."""
        _write_plugin(tmp_path, "my_cyberpunk.py", "MyPlugin", "mine")

        mgr = PluginManager()
        mgr.load_all(tmp_path)

        assert [p.name for p in mgr._plugins] == ["mine"]

    def test_the_real_example_file_is_still_shipped(self):
        """Skipping it is not the same as deleting the documentation."""
        assert Path("plugins/example-custom-genre.py").exists()

    def test_the_real_example_is_skipped_by_the_real_loader(self):
        mgr = PluginManager()
        mgr.load_all()
        assert all("Cyberpunk" not in p.name for p in mgr._plugins)


class TestLoaderBasics:
    def test_infrastructure_files_are_never_treated_as_plugins(self, tmp_path):
        for stem in ("__init__", "base", "loader"):
            (tmp_path / f"{stem}.py").write_text("raise RuntimeError('imported')")

        mgr = PluginManager()
        mgr.load_all(tmp_path)

        assert mgr._plugins == []

    def test_loading_is_idempotent(self, tmp_path):
        _write_plugin(tmp_path, "once.py", "Once", "once")

        mgr = PluginManager()
        mgr.load_all(tmp_path)
        mgr.load_all(tmp_path)

        assert len(mgr._plugins) == 1

    def test_a_broken_plugin_does_not_stop_the_others(self, tmp_path):
        (tmp_path / "broken.py").write_text("raise RuntimeError('boom')")
        _write_plugin(tmp_path, "good.py", "Good", "good")

        mgr = PluginManager()
        mgr.load_all(tmp_path)

        assert [p.name for p in mgr._plugins] == ["good"]

    def test_the_base_class_itself_is_not_registered(self, tmp_path):
        (tmp_path / "reexport.py").write_text(
            "from plugins.base import StoryForgePlugin\n", encoding="utf-8"
        )

        mgr = PluginManager()
        mgr.load_all(tmp_path)

        assert mgr._plugins == []


class TestStartupActuallyLoadsThem:
    def test_app_startup_calls_load_all(self):
        """The whole defect: eleven hooks that could never fire."""
        source = Path("app.py").read_text(encoding="utf-8")
        assert "plugin_manager.load_all()" in source

    def test_plugin_failure_cannot_stop_the_server_booting(self):
        source = Path("app.py").read_text(encoding="utf-8")
        idx = source.index("plugin_manager.load_all()")
        window = source[max(0, idx - 400) : idx + 400]
        assert "except Exception" in window


class TestTheV1MirrorIsGone:
    def test_the_package_no_longer_exists(self):
        with pytest.raises(ImportError):
            import api.v1  # noqa: F401

    def test_app_no_longer_mounts_it(self):
        source = Path("app.py").read_text(encoding="utf-8")
        assert "v1_router" not in source
        assert "DeprecationMiddleware" not in source

    def test_the_eval_prefix_is_unaffected(self):
        """/api/v1/eval belongs to eval_routes itself, not to the mirror."""
        from api.eval_routes import router

        assert router.prefix == "/v1/eval"

    def test_eval_routes_still_serve_that_path(self):
        from fastapi import FastAPI

        from api.eval_routes import router

        app = FastAPI()
        app.include_router(router, prefix="/api")
        paths = {r.path for r in app.routes}
        assert any(p.startswith("/api/v1/eval") for p in paths)


class TestHooksAreStillCalled:
    """Wiring the loader in is pointless if the call sites were removed."""

    @pytest.mark.parametrize(
        "module,hook",
        [
            ("pipeline.orchestrator_layers", "apply_score"),
            ("pipeline.orchestrator_layers", "apply_genre_rules"),
            ("pipeline.orchestrator_export", "apply_export"),
        ],
    )
    def test_the_hook_still_has_a_call_site(self, module, hook):
        import importlib

        mod = importlib.import_module(module)
        source = inspect.getsource(mod)
        assert f"plugin_manager.{hook}(" in source

    def test_an_empty_plugin_list_leaves_data_untouched(self):
        """The default path must stay a pass-through, not a mutation."""
        mgr = PluginManager()
        payload = {"overall": 4.2}
        assert mgr.apply_score(dict(payload)) == payload
