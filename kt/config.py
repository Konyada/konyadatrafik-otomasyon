"""config.yaml okuma."""

from __future__ import annotations

from pathlib import Path

import yaml

KOK = Path(__file__).resolve().parent.parent


def yukle(yol: Path | None = None) -> dict:
    yol = yol or KOK / "config.yaml"
    with open(yol, encoding="utf-8") as f:
        return yaml.safe_load(f)
