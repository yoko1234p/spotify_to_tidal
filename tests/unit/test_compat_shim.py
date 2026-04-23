"""Verify the spotify_to_tidal -> totidal_backend compatibility shim."""
from __future__ import annotations

import importlib
import sys
import warnings

import pytest


@pytest.fixture(autouse=True)
def _purge_modules():
    """Every test must start from a clean module cache.

    Autouse fixtures defined in a test file apply only to that file — they do
    not leak into the rest of the suite. Any test elsewhere that holds a bound
    reference to a `spotify_to_tidal.*` module will keep its old object, which
    is the correct isolation boundary.
    """
    for name in list(sys.modules):
        if name == "spotify_to_tidal" or name.startswith("spotify_to_tidal."):
            del sys.modules[name]
        if name == "totidal_backend" or name.startswith("totidal_backend."):
            del sys.modules[name]
    yield


def test_importing_old_name_emits_deprecation_warning():
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        importlib.import_module("spotify_to_tidal")
    messages = [str(w.message) for w in caught if issubclass(w.category, DeprecationWarning)]
    assert any("totidal_backend" in m for m in messages), messages


def test_importing_old_submodule_first_also_emits_warning():
    """`import spotify_to_tidal.sync` without touching the parent must still warn."""
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        importlib.import_module("spotify_to_tidal.sync")
    messages = [str(w.message) for w in caught if issubclass(w.category, DeprecationWarning)]
    assert any("totidal_backend" in m for m in messages), messages


def test_old_submodule_import_resolves_to_new_package():
    old = importlib.import_module("spotify_to_tidal.sync")
    new = importlib.import_module("totidal_backend.sync")
    assert old is new


def test_new_then_old_submodule_import_shares_module_object():
    """Reverse order: loading the new name first must still unify with the old alias."""
    new = importlib.import_module("totidal_backend.sync")
    old = importlib.import_module("spotify_to_tidal.sync")
    assert old is new


def test_old_from_import_resolves_to_new_package():
    import spotify_to_tidal  # noqa: F401
    import totidal_backend.auth as new_auth
    from spotify_to_tidal import auth as old_auth
    assert old_auth is new_auth


def test_type_subpackage_still_reachable():
    old = importlib.import_module("spotify_to_tidal.type.config")
    new = importlib.import_module("totidal_backend.type.config")
    assert old is new
