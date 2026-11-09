"""İstanbul saatine göre tarih işlemleri ve Türkçe tarih yazımı."""

from __future__ import annotations

import os
import re
from datetime import date, datetime
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/Istanbul")

AYLAR = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran",
         "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"]
GUNLER = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"]


def simdi() -> datetime:
    """Şu anki İstanbul saati. Test için KT_SIMDI=2026-11-10T09:00 verilebilir."""
    sabit = os.environ.get("KT_SIMDI", "").strip()
    if sabit:
        return datetime.fromisoformat(sabit).replace(tzinfo=TZ)
    return datetime.now(TZ)


def bugun() -> date:
    return simdi().date()


def tarih_yazi(d: date, gun_adi: bool = True, yil: bool = True) -> str:
    """10 Kasım 2026 Salı"""
    s = f"{d.day} {AYLAR[d.month - 1]}"
    if yil:
        s += f" {d.year}"
    if gun_adi:
        s += f" {GUNLER[d.weekday()]}"
    return s


def tr_kucuk(s: str) -> str:
    return s.replace("I", "ı").replace("İ", "i").lower()


def tr_buyuk(s: str) -> str:
    return s.replace("i", "İ").replace("ı", "I").upper()


def tr_baslik(s: str) -> str:
    """'SARI CAMİİ' -> 'Sarı Camii' (Türkçe kurallarıyla)."""
    kelimeler = re.split(r"(\s+|-|/|\()", tr_kucuk(s))
    out = []
    for k in kelimeler:
        if k and k[0].isalpha():
            out.append(tr_buyuk(k[0]) + k[1:])
        else:
            out.append(k)
    return "".join(out)


def ay_numarasi(ad: str) -> int:
    ad = tr_kucuk(ad.strip())
    for i, a in enumerate(AYLAR, start=1):
        if tr_kucuk(a) == ad:
            return i
    raise ValueError(f"Ay adı anlaşılamadı: {ad!r}")


def gun_ay_coz(gun: int, ay_adi: str, referans: date) -> date:
    """'9 Kasım' gibi yılı olmayan tarihi referans tarihe en yakın yıla oturtur."""
    ay = ay_numarasi(ay_adi)
    adaylar = [date(referans.year + dy, ay, gun) for dy in (-1, 0, 1)]
    return min(adaylar, key=lambda d: abs((d - referans).days))
