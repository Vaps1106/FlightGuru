"""Foundation smoke tests — package import, provider gating, clean main run."""

from __future__ import annotations

from flightguru import __version__
from flightguru import main as main_mod
from flightguru import search as search_mod
from flightguru.config import _int_env, enabled_providers


def test_int_env_defaults_and_bad_values(monkeypatch):
    monkeypatch.delenv("FG_TEST_INT", raising=False)
    assert _int_env("FG_TEST_INT", 5) == 5          # unset -> default
    monkeypatch.setenv("FG_TEST_INT", "12")
    assert _int_env("FG_TEST_INT", 5) == 12         # numeric -> parsed
    monkeypatch.setenv("FG_TEST_INT", "7O0")        # typo (letter O) -> default
    assert _int_env("FG_TEST_INT", 5) == 5


def test_package_has_version():
    assert __version__


def test_enabled_providers_filters_placeholders(make_settings):
    s = make_settings(duffel_token="PASTE_DUFFEL_TOKEN_HERE")
    enabled = enabled_providers(s)
    assert "duffel" not in enabled       # placeholder -> excluded
    assert "serpapi" in enabled          # real key -> included


def test_enabled_providers_empty_when_unconfigured(make_settings):
    s = make_settings(duffel_token="", serpapi_key="")
    assert enabled_providers(s) == []


def test_main_runs_clean(monkeypatch):
    # No network: stub the search so main() exercises orchestration only.
    monkeypatch.setattr(search_mod, "search_all", lambda settings, on_error=None: [])
    assert main_mod.main() == 0
