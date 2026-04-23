"""Deprecated alias for the :mod:`totidal_backend` package.

This shim exists so that users and tests that still import the old
``spotify_to_tidal`` name continue to work for one release cycle.
All attribute access, submodule imports, and ``python -m spotify_to_tidal``
invocations are forwarded to :mod:`totidal_backend`.

Remove this shim no earlier than the release AFTER 1.0.7.
"""
from __future__ import annotations

import importlib
import pkgutil
import sys
import warnings

_NEW_NAME = "totidal_backend"
_OLD_NAME = "spotify_to_tidal"

warnings.warn(
    f"The {_OLD_NAME!r} package name is deprecated; import {_NEW_NAME!r} instead. "
    "The alias will be removed in the next minor release.",
    DeprecationWarning,
    stacklevel=2,
)

_target = importlib.import_module(_NEW_NAME)

# Eagerly import every submodule of totidal_backend (skipping __main__, which
# would run argparse on import) so that ``import spotify_to_tidal.sync`` style
# statements resolve via the sys.modules cache populated below instead of the
# import machinery looking inside this shim's own directory.
for _info in pkgutil.walk_packages(_target.__path__, prefix=_target.__name__ + "."):
    if _info.name.rsplit(".", 1)[-1] == "__main__":
        continue
    importlib.import_module(_info.name)

# Alias every already-imported submodule so the old namespace is fully populated.
for _name, _mod in list(sys.modules.items()):
    if _name == _NEW_NAME or _name.startswith(_NEW_NAME + "."):
        _alias = _OLD_NAME + _name[len(_NEW_NAME):]
        sys.modules.setdefault(_alias, _mod)


# Forward attribute access (covers ``from spotify_to_tidal import sync``).
def __getattr__(name: str):
    try:
        sub = importlib.import_module(f"{_NEW_NAME}.{name}")
    except ModuleNotFoundError:
        try:
            return getattr(_target, name)
        except AttributeError as exc:
            raise AttributeError(
                f"module {_OLD_NAME!r} has no attribute {name!r}"
            ) from exc
    sys.modules[f"{_OLD_NAME}.{name}"] = sub
    return sub


def __dir__() -> list[str]:
    return sorted(set(dir(_target)) | {"__getattr__", "__dir__"})
