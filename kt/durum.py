"""Sistemin hafızası: hangi görev ne zaman yapıldı, hangi vefat/haber paylaşıldı.

data/durum.json dosyasında tutulur ve her paylaşımdan sonra depoya kaydedilir.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

from .config import KOK
from .tarih import simdi

VARSAYILAN_YOL = KOK / "data" / "durum.json"
SAKLAMA_GUN = 14


class Durum:
    def __init__(self, yol: Path = VARSAYILAN_YOL):
        self.yol = yol
        if yol.exists():
            self.veri = json.loads(yol.read_text(encoding="utf-8"))
        else:
            self.veri = {}
        self.veri.setdefault("gunler", {})
        self.veri.setdefault("vefat", {})
        self.veri.setdefault("haberler", [])
        self.veri.setdefault("ayar", {})
        self.degisti = False

    # --- görev (slot) kayıtları -------------------------------------------------
    def slot(self, gun: date, slot_id: str) -> dict:
        return self.veri["gunler"].get(gun.isoformat(), {}).get(slot_id, {})

    def slot_kaydet(self, gun: date, slot_id: str, **bilgi) -> None:
        kayit = self.veri["gunler"].setdefault(gun.isoformat(), {}).setdefault(slot_id, {})
        kayit.update(bilgi)
        kayit["guncelleme"] = simdi().isoformat(timespec="seconds")
        self.degisti = True

    # --- vefat ------------------------------------------------------------------
    def vefat_paylasilan(self, gun: date) -> set[str]:
        return set(self.veri["vefat"].get(gun.isoformat(), []))

    def vefat_ekle(self, gun: date, anahtarlar: list[str]) -> None:
        mevcut = self.veri["vefat"].setdefault(gun.isoformat(), [])
        for a in anahtarlar:
            if a not in mevcut:
                mevcut.append(a)
        self.degisti = True

    # --- haber ------------------------------------------------------------------
    def haber_gecmisi(self, gun_sayisi: int, bugun: date) -> list[dict]:
        sinir = (bugun - timedelta(days=gun_sayisi)).isoformat()
        return [h for h in self.veri["haberler"] if h.get("tarih", "") >= sinir]

    def haber_ekle(self, tarih: date, baslik: str, url: str, kategori: str) -> None:
        self.veri["haberler"].append(
            {"tarih": tarih.isoformat(), "baslik": baslik, "url": url, "kategori": kategori}
        )
        self.degisti = True

    # --- ayarlar (ör. bulunan Instagram hesap kimliği) ---------------------------
    def ayar(self, anahtar: str, varsayilan=None):
        return self.veri["ayar"].get(anahtar, varsayilan)

    def ayar_kaydet(self, anahtar: str, deger) -> None:
        if self.veri["ayar"].get(anahtar) != deger:
            self.veri["ayar"][anahtar] = deger
            self.degisti = True

    # --- kaydet -------------------------------------------------------------------
    def buda(self, bugun: date) -> None:
        sinir = (bugun - timedelta(days=SAKLAMA_GUN)).isoformat()
        for alan in ("gunler", "vefat"):
            for g in [g for g in self.veri[alan] if g < sinir]:
                del self.veri[alan][g]
                self.degisti = True
        once = len(self.veri["haberler"])
        self.veri["haberler"] = [h for h in self.veri["haberler"] if h.get("tarih", "") >= sinir]
        if len(self.veri["haberler"]) != once:
            self.degisti = True

    def kaydet(self) -> None:
        self.yol.parent.mkdir(parents=True, exist_ok=True)
        self.yol.write_text(json.dumps(self.veri, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
