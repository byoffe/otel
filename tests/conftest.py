"""Global pytest configuration.

Loaded before any test module is imported, so the env-var and patch setup
here takes effect when service modules run their module-level code.
"""

import os

# Services read these constants at import time; zero them out so tests run fast.
os.environ.setdefault("SIM_DELAY_MIN", "0")
os.environ.setdefault("SIM_DELAY_MAX", "0")
os.environ.setdefault("SIM_ERROR_RATE", "0")

from unittest.mock import MagicMock, patch  # noqa: E402

# Replace init_otel with a no-op before any service module is imported.
# Each service calls init_otel() at module level; without this every import
# would attempt a gRPC connection to a collector that doesn't exist in tests.
patch("otel_common.init_otel", MagicMock()).start()
