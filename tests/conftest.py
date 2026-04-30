"""Test bootstrap: load local .env so e2e tests can use developer credentials.

In CI the secrets are injected via the workflow's env, so this no-op is
fine when no .env is present.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

_repo_root = Path(__file__).resolve().parent.parent
_env_path = _repo_root / ".env"
if _env_path.exists():
    load_dotenv(_env_path, override=False)
