"""Deprecated entry point. Forwards to ``totidal_backend.__main__.main``."""
from __future__ import annotations

import sys

from totidal_backend.__main__ import main

if __name__ == "__main__":
    import warnings

    warnings.warn(
        "`python -m spotify_to_tidal` is deprecated; use `python -m totidal_backend` "
        "or the `totidal` CLI instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    sys.exit(main())
