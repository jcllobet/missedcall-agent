"""Test bootstrap: load local .env so e2e tests can use developer credentials.

In CI the secrets are injected via the workflow's env, so this no-op is
fine when no .env is present.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

_voice_root = Path(__file__).resolve().parent.parent
for _env_path in (_voice_root.parent / ".env", _voice_root / ".env"):
    if _env_path.exists():
        load_dotenv(_env_path, override=False)
