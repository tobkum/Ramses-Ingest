# -*- coding: utf-8 -*-
"""Entry point for `python -m ramses_ingest`."""

import sys
import os

# Add shared Ramses API library path (project root)
_lib = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "lib")
if _lib not in sys.path:
    sys.path.insert(0, _lib)

# Apply upstream Ramses API patches before app/gui (and publisher, which imports
# the ramses library at module load) are pulled in.
from ramses_ingest import monkeypatches  # noqa: F401

from ramses_ingest.app import main

if __name__ == "__main__":
    main()
