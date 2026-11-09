"""Günün sözü: data/sozler.json listesinden her gün sıradaki söz."""

from __future__ import annotations

import json
from datetime import date

from ..config import KOK


def tum_sozler() -> list[dict]:
    return json.loads((KOK / "data" / "sozler.json").read_text(encoding="utf-8"))


def gunun_sozu(gun: date) -> dict:
    sozler = tum_sozler()
    return sozler[gun.toordinal() % len(sozler)]
