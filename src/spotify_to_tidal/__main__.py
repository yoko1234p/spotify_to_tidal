"""Deprecated entry point. Forwards to ``totidal_backend.__main__.main``."""
from __future__ import annotations

import sys
import warnings

from totidal_backend.__main__ import main

warnings.warn(
    "`python -m spotify_to_tidal` is deprecated; use `python -m totidal_backend` "
    "or the `totidal` CLI instead.",
    DeprecationWarning,
    stacklevel=2,
)

if __name__ == "__main__":
    main()
    sys.exit(0)
