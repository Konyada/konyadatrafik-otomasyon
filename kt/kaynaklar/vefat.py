"""Konya Büyükşehir Belediyesi vefat listesi (mezarlik.konya.bel.tr)."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import date

from bs4 import BeautifulSoup

from . import temiz
from ..tarih import tr_baslik, tr_buyuk, tr_kucuk

ANA_URL = "https://mezarlik.konya.bel.tr/"
ARAMA_URL = "https://mezarlik.konya.bel.tr/detayliArama"

SUTUNLAR = {
    "vefat tarihi": "vefat_tarihi",
    "defin tarihi": "defin_tarihi",
    "adı soyadı": "ad_soyad",
    "baba adı": "baba_adi",
    "doğum yeri": "dogum_yeri",
    "doğum tarihi": "dogum_tarihi",
    "camii": "camii",
    "cami": "camii",
    "namaz": "namaz",
    "defin yeri": "defin_yeri",
}


def _tarih(s: str) -> date | None:
    m = re.search(r"(\d{1,2})[-./](\d{1,2})[-./](\d{4})", s or "")
    if not m:
        return None
    try:
        return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    except ValueError:
        return None


def _parantez_duzelt(s: str) -> str:
    s = re.sub(r"\(\s+", "(", s)
    s = re.sub(r"\s+\)", ")", s)
    return temiz(s)


@dataclass
class Vefat:
    ad_soyad: str
    defin_tarihi: date | None = None
    vefat_tarihi: date | None = None
    baba_adi: str = ""
    dogum_yeri: str = ""
    dogum_tarihi: str = ""
    camii: str = ""
    namaz: str = ""
    defin_yeri: str = ""

    def anahtar(self) -> str:
        ham = f"{tr_buyuk(self.ad_soyad)}|{tr_buyuk(self.baba_adi)}|{self.defin_tarihi}"
        return hashlib.sha1(ham.encode("utf-8")).hexdigest()[:16]

    def cenaze_yazi(self) -> str:
        cami = _parantez_duzelt(self.camii)
        cami = "Mezarlıkta" if tr_kucuk(cami) in ("mezarlıkta", "mezarlikta") else tr_baslik(cami)
        namaz = tr_baslik(temiz(self.namaz))
        namaz = re.sub(r"^(Ögle|Ogle|Öğle)\b", "Öğle", namaz)
        return " – ".join(p for p in (cami, namaz) if p)

    def mezarlik_kisa(self) -> str:
        """'SEYİT ŞAHİN ( KURTULUŞ ) MEZARLIĞI' -> 'Seyit Şahin (Kurtuluş)'"""
        yer = tr_baslik(_parantez_duzelt(self.defin_yeri))
        return re.sub(r"\s+Mezarl[ıi][ğg][ıi]$", "", yer).strip()

    def story(self) -> dict:
        return {
            "ad": tr_baslik(temiz(self.ad_soyad)),
            "defin": self.mezarlik_kisa(),
            "baba": tr_baslik(temiz(self.baba_adi)),
            "cenaze": self.cenaze_yazi(),
        }


def tablo_coz(html: str) -> list[Vefat]:
    soup = BeautifulSoup(html, "html.parser")
    tablo = soup.find("table")
    if not tablo:
        return []
    basliklar = [tr_kucuk(temiz(th.get_text())) for th in tablo.find_all("th")]
    alanlar = [SUTUNLAR.get(b) for b in basliklar]
    sonuc = []
    govde = tablo.find("tbody") or tablo
    for tr in govde.find_all("tr"):
        hucreler = [temiz(td.get_text(" ")) for td in tr.find_all("td")]
        if not hucreler:
            continue
        kayit = {}
        for alan, deger in zip(alanlar, hucreler):
            if alan:
                kayit[alan] = deger
        if not kayit.get("ad_soyad"):
            continue
        sonuc.append(Vefat(
            ad_soyad=kayit["ad_soyad"],
            defin_tarihi=_tarih(kayit.get("defin_tarihi", "")),
            vefat_tarihi=_tarih(kayit.get("vefat_tarihi", "")),
            baba_adi=kayit.get("baba_adi", ""),
            dogum_yeri=kayit.get("dogum_yeri", ""),
            dogum_tarihi=kayit.get("dogum_tarihi", ""),
            camii=kayit.get("camii", ""),
            namaz=kayit.get("namaz", ""),
            defin_yeri=kayit.get("defin_yeri", ""),
        ))
    return sonuc


def getir(oturum) -> list[Vefat]:
    """Ana sayfadaki listeyi ve 'Bugün Vefat Edenler' aramasını birleştirir."""
    r = oturum.get(ANA_URL, timeout=30)
    r.raise_for_status()
    kayitlar = tablo_coz(r.text)
    soup = BeautifulSoup(r.text, "html.parser")
    token = soup.find("input", {"name": "_token"})
    if token and token.get("value"):
        r2 = oturum.post(ARAMA_URL, timeout=30, headers={"Referer": ANA_URL}, data={
            "_token": token["value"], "defin_tarih": "0", "olen_ad": "", "olen_soyad": "",
        })
        if r2.ok:
            kayitlar += tablo_coz(r2.text)
    tekil, gorulen = [], set()
    for k in kayitlar:
        if k.anahtar() not in gorulen:
            gorulen.add(k.anahtar())
            tekil.append(k)
    return tekil


def gune_gore(kayitlar: list[Vefat], gun: date) -> list[Vefat]:
    return [k for k in kayitlar if k.defin_tarihi == gun]
