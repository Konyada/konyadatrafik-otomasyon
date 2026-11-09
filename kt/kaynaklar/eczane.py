"""Konya nöbetçi eczaneleri.

Birincil kaynak: 5. Bölge Konya Eczacı Odası'nın nöbet sitesi
(konyanobetcieczaneleri.com). Ulaşılamazsa posta.com.tr listesi yedek olarak kullanılır.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date

from bs4 import BeautifulSoup

from . import temiz
from ..tarih import gun_ay_coz

RESMI_URL = "https://www.konyanobetcieczaneleri.com/"
RESMI_AD = "5. Bölge Konya Eczacı Odası"
YEDEK_URL = "https://www.posta.com.tr/nobetci-eczaneler/konya/"
YEDEK_AD = "posta.com.tr (Konya Eczacı Odası verisi)"


@dataclass
class Eczane:
    ad: str
    kapsam: str = ""
    adres: str = ""
    tarif: str = ""
    tel: str = ""
    ilce: str = ""

    def adres_kisa(self) -> str:
        """Adresin sonundaki '· Selçuklu' gibi ilçe ekini atar."""
        return re.sub(r"\s*·\s*[^·]+$", "", self.adres).strip() if "·" in self.adres else self.adres

    def story(self) -> dict:
        return {"ad": self.ad, "tel": self.tel, "tarif": self.tarif or self.adres_kisa()}


ILCE_SIRASI = ["Selçuklu", "Meram", "Karatay"]


def ilceye_gore(eczaneler: list[Eczane]) -> list[tuple[str, list[dict]]]:
    """Şablondaki gibi ilçe başlıkları altında gruplar: önce Selçuklu, Meram, Karatay."""
    gruplar: dict[str, list[dict]] = {}
    for e in eczaneler:
        ilce = e.ilce or e.kapsam or "Konya"
        gruplar.setdefault(ilce, []).append(e.story())
    sira = [i for i in ILCE_SIRASI if i in gruplar] + sorted(i for i in gruplar if i not in ILCE_SIRASI)
    return [(i, gruplar[i]) for i in sira]


@dataclass
class NobetListesi:
    baslangic: date | None
    pencere: str
    kaynak: str
    eczaneler: list[Eczane] = field(default_factory=list)


def telefon_duzelt(tel: str) -> str:
    rakam = re.sub(r"\D", "", tel or "")
    if rakam.startswith("90") and len(rakam) == 12:
        rakam = "0" + rakam[2:]
    if len(rakam) == 10:
        rakam = "0" + rakam
    if len(rakam) == 11 and rakam.startswith("0"):
        return f"{rakam[:4]} {rakam[4:7]} {rakam[7:9]} {rakam[9:]}"
    return temiz(tel)


PENCERE_RE = re.compile(
    r"(\d{1,2})\s+([A-Za-zÇĞİÖŞÜçğıöşü]+)\s+(\d{1,2}[:.]\d{2})\s*[–—-]\s*"
    r"(\d{1,2})\s+([A-Za-zÇĞİÖŞÜçğıöşü]+)\s+(\d{1,2}[:.]\d{2})"
)


def resmi_coz(html: str, referans: date, bolumler: tuple[str, ...] | list[str] = ("merkez",)) -> NobetListesi:
    soup = BeautifulSoup(html, "html.parser")
    pencere_yazi = ""
    for el in soup.find_all(["p", "span", "div"]):
        t = temiz(el.get_text(" "))
        if t.startswith("Merkez nöbeti") and len(t) < 140:
            pencere_yazi = t
            break
    baslangic, pencere = None, pencere_yazi.replace("Merkez nöbeti", "").strip()
    m = PENCERE_RE.search(pencere_yazi)
    if m:
        baslangic = gun_ay_coz(int(m.group(1)), m.group(2), referans)
        pencere = f"{m.group(1)} {m.group(2)} {m.group(3)} – {m.group(4)} {m.group(5)} {m.group(6)}"

    liste = NobetListesi(baslangic=baslangic, pencere=pencere, kaynak=RESMI_AD)
    for bolum in bolumler:
        sec = soup.find("section", attrs={"data-bolum": bolum})
        if not sec:
            continue
        for art in sec.find_all("article", attrs={"data-kart": True}):
            h3 = art.find("h3")
            ad = temiz(h3.get_text(" ")) if h3 else temiz(art.get("data-ad", ""))
            if not ad:
                continue
            if "eczane" not in ad.lower():
                ad = f"{ad} Eczanesi"
            kapsam_el = art.find("p", class_=lambda c: c and "uppercase" in c)
            kapsam = temiz(kapsam_el.get_text(" ")) if kapsam_el else temiz(art.get("data-bolge", ""))
            adres = tarif = ""
            for p in art.find_all("p"):
                if p is kapsam_el:
                    continue
                t = temiz(p.get_text(" "))
                if not t:
                    continue
                siniflar = " ".join(p.get("class", []))
                if "italic" in siniflar:
                    tarif = tarif or t
                else:
                    adres = adres or t
            liste.eczaneler.append(Eczane(
                ad=ad, kapsam=kapsam, adres=adres, tarif=tarif,
                tel=telefon_duzelt(art.get("data-tel", "")), ilce=temiz(art.get("data-bolge", "")),
            ))
    return liste


def yedek_coz(html: str, ilceler: list[str] | None = None) -> NobetListesi:
    soup = BeautifulSoup(html, "html.parser")
    zaman = soup.find("time", class_="pharmacy-module-date")
    baslangic = None
    if zaman and zaman.get("datetime"):
        baslangic = date.fromisoformat(zaman["datetime"][:10])
    bilgi = soup.find(class_="ecz-module-info-text")
    liste = NobetListesi(baslangic=baslangic, pencere=temiz(bilgi.get_text()) if bilgi else "", kaynak=YEDEK_AD)
    for kat in soup.select(".ecz-module-city-category"):
        h2 = kat.find("h2")
        ilce = temiz(h2.get_text()) if h2 else ""
        if ilceler and ilce not in ilceler:
            continue
        for oge in kat.select(".ecz-module-pharmacy-item"):
            ad_el = oge.select_one(".ecz-module-pharmacy-name")
            if not ad_el:
                continue
            adres_el = oge.select_one(".ecz-module-pharmacy-location")
            tel_el = oge.select_one(".ecz-module-pharmacy-contact")
            adres = temiz(adres_el.get_text(" ")) if adres_el else ""
            tel = temiz(tel_el.get_text(" ")) if tel_el else ""
            liste.eczaneler.append(Eczane(
                ad=temiz(ad_el.get_text()), kapsam=ilce,
                adres=re.sub(r"^Adres:\s*", "", adres), tel=telefon_duzelt(re.sub(r"^Telefon:\s*", "", tel)),
                ilce=ilce,
            ))
    return liste


def getir(oturum, bugun: date, bolumler=("merkez",), yedek_ilceler=None, log=print) -> NobetListesi:
    hatalar = []
    try:
        r = oturum.get(RESMI_URL, timeout=30)
        r.raise_for_status()
        liste = resmi_coz(r.text, bugun, bolumler)
        if liste.eczaneler:
            return liste
        hatalar.append("resmi site: liste boş")
    except Exception as e:  # noqa: BLE001
        hatalar.append(f"resmi site: {e}")
    log("Eczacı Odası sitesi okunamadı, yedek kaynağa geçiliyor: " + "; ".join(hatalar))
    try:
        r = oturum.get(YEDEK_URL, timeout=30)
        r.raise_for_status()
        liste = yedek_coz(r.text, yedek_ilceler)
        if liste.eczaneler:
            return liste
        hatalar.append("yedek: liste boş")
    except Exception as e:  # noqa: BLE001
        hatalar.append(f"yedek: {e}")
    raise RuntimeError("Nöbetçi eczane listesi alınamadı: " + "; ".join(hatalar))
