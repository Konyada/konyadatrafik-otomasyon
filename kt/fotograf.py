"""Haber story'leri için sayfanın kendi fotoğraf arşivinden seçim.

assets/fotograflar/ altındaki klasörler:
  1) ilçe/semt klasörü      (ör. kulu, selcuklu, meram)
  2) kategori klasörü       (ör. trafik, kaza, buyuksehir, konyaspor, saglik, hava-durumu)
  3) genel                  (her habere uyan Konya fotoğrafları — en son çare olarak kullanılır)
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

from .config import KOK
from .tarih import tr_kucuk

DIZIN = KOK / "assets" / "fotograflar"
UZANTILAR = {".jpg", ".jpeg", ".png", ".webp"}


def klasor_adi(metin: str) -> str:
    s = tr_kucuk(metin or "")
    for a, b in zip("çğıöşüâî", "cgiosuai"):
        s = s.replace(a, b)
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


def _klasorden(klasor: Path, anahtar: str) -> Path | None:
    if not klasor.is_dir():
        return None
    dosyalar = sorted(p for p in klasor.iterdir() if p.suffix.lower() in UZANTILAR)
    if not dosyalar:
        return None
    return dosyalar[int(hashlib.md5(anahtar.encode("utf-8")).hexdigest(), 16) % len(dosyalar)]


def sec(kategori: str, konum: str, anahtar: str, dizin: Path = DIZIN, genel: bool = True) -> Path | None:
    """Önce ilçe, sonra kategori klasörüne bakar; genel=True ise en son 'genel' klasörüne."""
    adlar = [klasor_adi(konum), klasor_adi(kategori)] + (["genel"] if genel else [])
    for ad in adlar:
        if ad:
            secilen = _klasorden(dizin / ad, anahtar)
            if secilen:
                return secilen
    return None


def sec_genel(anahtar: str, dizin: Path = DIZIN) -> Path | None:
    return _klasorden(dizin / "genel", anahtar)
