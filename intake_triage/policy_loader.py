from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

POLICY_PATH = Path(__file__).resolve().parent.parent / "policy.yaml"


@lru_cache(maxsize=1)
def load_policy(path: Path | None = None) -> dict:
    target = path or POLICY_PATH
    with target.open(encoding="utf-8") as handle:
        return yaml.safe_load(handle)
