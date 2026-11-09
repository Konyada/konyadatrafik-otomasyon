"""Veri kaynakları: nöbetçi eczane, vefat listesi, günün sözü, yapay zekâ haberleri."""

from __future__ import annotations

import re

import requests

UA = ("Mozilla/5.0 (compatible; KonyadaTrafikStoryBot/1.0; "
      "+https://www.instagram.com/konyada_trafik/)")


def oturum() -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": UA, "Accept-Language": "tr-TR,tr;q=0.9"})
    return s


def temiz(metin: str | None) -> str:
    return re.sub(r"\s+", " ", metin or "").strip()
