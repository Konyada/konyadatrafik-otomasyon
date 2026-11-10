"""Konya nöbetçi eczaneleri.

Birincil kaynak: 5. Bölge Konya Eczacı Odası'nın nöbet sitesi
(konyanobetcieczaneleri.com). Ulaşılamazsa posta.com.tr listesi yedek olarak kullanılır.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from . import temiz
from ..tarih import gun_ay_coz

RESMI_URL = "https://www.konyanobetcieczaneleri.com/"
RESMI_AD = "5. Bölge Konya Eczacı Odası"
# Sayfa, telefon/adres/tarif/ilçe bilgisini tarayıcıda bu adresten ayrıca yükler (sunucu HTML'inde boş gelir).
VERI_YOLU = "/nobet/onyuz/veri.php"
YUKLENIYOR = ("yükleniyor", "yukleniyor")
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


def _alan(art, ad: str) -> str | None:
    """Kartın data-alan="..." öğesinin metni; öğe yoksa None. 'Yükleniyor…' yer tutucusu boş sayılır."""
    el = art.find(attrs={"data-alan": ad})
    if el is None:
        return None
    t = temiz(el.get_text(" "))
    return "" if t.lower().startswith(YUKLENIYOR) else t


def resmi_ayrintilar(oturum, html: str) -> dict:
    """Sayfanın kendi betiğinin yaptığı gibi veri.php'den kart ayrıntılarını alır.

    Dönen sözlük kart anahtarına (data-anahtar, ör. "m-32") göredir:
    {"m-32": {"adres", "ilce", "tarif", "tel", "telLink", "lat", "lon", "placeId"}, ...}
    """
    soup = BeautifulSoup(html, "html.parser")
    govde = soup.body
    j = govde.get("data-j", "") if govde else ""
    if not j:
        raise RuntimeError("sayfada ayrıntı anahtarı (data-j) yok")
    url = urljoin(RESMI_URL, govde.get("data-veri") or VERI_YOLU)
    r = oturum.post(url, data={"j": j, "cf": "", "c": "masaustu", "t": "diger", "k": "normal"},
                    headers={"Accept": "application/json", "Origin": RESMI_URL.rstrip("/"), "Referer": RESMI_URL},
                    timeout=30)
    r.raise_for_status()
    veri = r.json()
    if not isinstance(veri, dict) or not veri:
        raise RuntimeError("ayrıntı verisi boş geldi")
    return veri


def resmi_coz(html: str, referans: date, bolumler: tuple[str, ...] | list[str] = ("merkez",),
              ayrinti: dict | None = None) -> NobetListesi:
    """ayrinti: resmi_ayrintilar() sonucu; verilirse telefon, adres, tarif ve gerçek ilçe oradan alınır."""
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
    ayrinti = ayrinti or {}
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
            bolge = temiz(art.get("data-bolge", ""))          # nöbet bölgesi, ör. "Karatay - Meram"
            kapsam_el = art.find("p", class_=lambda c: c and "uppercase" in c)
            kapsam = temiz(kapsam_el.get_text(" ")) if kapsam_el else bolge
            adres, tarif = _alan(art, "adres"), _alan(art, "tarif")
            if adres is None and tarif is None:                # eski yapı: adres/tarif doğrudan <p> içinde
                adres = tarif = ""
                for p in art.find_all("p"):
                    if p is kapsam_el:
                        continue
                    t = temiz(p.get_text(" "))
                    if not t or t.lower().startswith(YUKLENIYOR):
                        continue
                    if "italic" in " ".join(p.get("class", [])):
                        tarif = tarif or t
                    else:
                        adres = adres or t
            tel = art.get("data-tel", "") or _alan(art, "tel-yazi") or ""
            ilce = bolge if bolge and "-" not in bolge else ""   # tek ilçeli bölge = ilçe tahmini
            v = ayrinti.get(art.get("data-anahtar", "")) or {}
            if v:
                adres = temiz(v.get("adres")) or adres
                tarif = temiz(v.get("tarif")) or tarif
                tel = v.get("tel") or v.get("telLink") or tel
                ilce = temiz(v.get("ilce")) or ilce
            liste.eczaneler.append(Eczane(ad=ad, kapsam=kapsam, adres=adres or "", tarif=tarif or "",
                                          tel=telefon_duzelt(tel), ilce=ilce))
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
    telefonsuz = None
    try:
        r = oturum.get(RESMI_URL, timeout=30)
        r.raise_for_status()
        try:
            ayrinti = resmi_ayrintilar(oturum, r.text)
        except Exception as e:  # noqa: BLE001
            ayrinti = {}
            hatalar.append(f"resmi site ayrıntıları (telefon/adres): {e}")
        liste = resmi_coz(r.text, bugun, bolumler, ayrinti)
        if liste.eczaneler and any(e.tel for e in liste.eczaneler):
            return liste
        if liste.eczaneler:
            telefonsuz = liste                       # isimler var ama telefonlar yok: önce yedeği dene
            hatalar.append("resmi site: telefonlar alınamadı")
        else:
            hatalar.append("resmi site: liste boş")
    except Exception as e:  # noqa: BLE001
        hatalar.append(f"resmi site: {e}")
    log("Eczacı Odası sitesinden tam liste alınamadı, yedek kaynak deneniyor: " + "; ".join(hatalar))
    try:
        r = oturum.get(YEDEK_URL, timeout=30)
        r.raise_for_status()
        liste = yedek_coz(r.text, yedek_ilceler)
        if liste.eczaneler:
            return liste
        hatalar.append("yedek: liste boş")
    except Exception as e:  # noqa: BLE001
        hatalar.append(f"yedek: {e}")
    if telefonsuz:
        log("Yedek kaynak da olmadı; Eczacı Odası listesi telefonsuz kullanılıyor.")
        return telefonsuz
    raise RuntimeError("Nöbetçi eczane listesi alınamadı: " + "; ".join(hatalar))
