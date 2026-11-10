"""Konya nöbetçi eczaneleri.

Liste (hangi eczaneler nöbette, nöbet saatleri, sıra) 5. Bölge Konya Eczacı Odası'nın nöbet
sitesinden (konyanobetcieczaneleri.com) alınır. Odanın sitesi telefon ve adresleri tarayıcıda ayrı bir
adresten yüklüyor ve o adres otomatik erişime kapalı (403); bu yüzden telefon, adres ve ilçe, aynı
Oda verisini yayınlayan posta.com.tr listesinden eczane adıyla eşleştirilerek eklenir.
Oda sitesine ulaşılamazsa liste tamamen posta.com.tr'den alınır.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from difflib import SequenceMatcher

from bs4 import BeautifulSoup

from . import temiz
from ..tarih import gun_ay_coz, tr_kucuk

RESMI_URL = "https://www.konyanobetcieczaneleri.com/"
RESMI_AD = "5. Bölge Konya Eczacı Odası"
YUKLENIYOR = ("yükleniyor", "yukleniyor")       # Oda sitesinde telefon yerine duran yer tutucu
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
        """Story için kısa adres: 'Mahallesi' → 'Mh.' vb., sondaki ilçe / Konya ekleri atılır."""
        return adres_kisalt(self.adres, self.ilce)

    def story(self) -> dict:
        return {"ad": self.ad, "tel": self.tel, "tarif": self.tarif or self.adres_kisa()}


KISALTMALAR = [
    (r"\bMahallesi\b|\bMah\.(?=\s|,|$)", "Mh."), (r"\bCaddesi\b|\bCad\.(?=\s|,|$)", "Cd."),
    (r"\bSokağı\b|\bSokak\b|\bSok\.(?=\s|,|$)", "Sk."), (r"\bBulvarı\b", "Blv."),
]


def adres_kisalt(adres: str, ilce: str = "") -> str:
    a = temiz(adres)
    a = re.sub(r"\s*·\s*[^·]+$", "", a)                          # Oda sitesindeki "· Selçuklu" eki
    for desen, yerine in KISALTMALAR:
        a = re.sub(desen, yerine, a)
    for _ in range(2):                                           # "... Selçuklu / Konya" gibi sondaki ekler
        a = re.sub(r"[\s,/–-]*\bKonya\s*$", "", a, flags=re.IGNORECASE)
        if ilce:
            a = re.sub(rf"[\s,/–-]*\b{re.escape(ilce)}\s*$", "", a, flags=re.IGNORECASE)
    return a.strip(" ,/–-")


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


def _ad_anahtari(ad: str) -> str:
    """'ÖZGÜL ECZANESİ' / 'Özgül Eczanesi' → 'ozgul' (eşleştirme için)."""
    t = tr_kucuk(ad)
    t = re.sub(r"\beczanes[iı]\b|\beczane\b|\becz\b\.?", " ", t)
    t = t.translate(str.maketrans("çğıöşüâîû", "cgiosuaiu"))
    return re.sub(r"[^a-z0-9]", "", t)


def birlestir(resmi: NobetListesi, yedek: NobetListesi, log=print) -> NobetListesi:
    """Oda listesindeki her eczaneye yedek listeden telefon, adres ve ilçe ekler (adla eşleştirerek)."""
    kalan = list(yedek.eczaneler)

    def sec(e: Eczane, adaylar: list[Eczane]) -> Eczane | None:
        if not adaylar:
            return None
        kapsam = tr_kucuk(f"{e.kapsam} {e.ilce}")
        return next((y for y in adaylar if y.ilce and tr_kucuk(y.ilce) in kapsam), adaylar[0])

    eksik = []
    for e in resmi.eczaneler:
        anahtar = _ad_anahtari(e.ad)
        y = sec(e, [y for y in kalan if _ad_anahtari(y.ad) == anahtar])
        if y is None:                                            # yazım farkı: en benzer adı dene
            puanli = sorted(((SequenceMatcher(None, anahtar, _ad_anahtari(y.ad)).ratio(), i)
                             for i, y in enumerate(kalan)), reverse=True)
            if puanli and puanli[0][0] >= 0.88:
                y = kalan[puanli[0][1]]
        if y is None:
            eksik.append(e.ad)
            continue
        kalan.remove(y)
        e.tel, e.adres, e.ilce = y.tel or e.tel, y.adres or e.adres, y.ilce or e.ilce
    eslesen = len(resmi.eczaneler) - len(eksik)
    log(f"Eczane telefonları: {eslesen}/{len(resmi.eczaneler)} eşleşti"
        + (f" (eşleşmeyen: {', '.join(eksik)})" if eksik else ""))
    resmi.kaynak = f"{RESMI_AD}; telefon/adres: posta.com.tr"
    return resmi


def getir(oturum, bugun: date, bolumler=("merkez",), yedek_ilceler=None, log=print) -> NobetListesi:
    hatalar = []
    resmi = yedek = None
    try:
        r = oturum.get(RESMI_URL, timeout=30)
        r.raise_for_status()
        resmi = resmi_coz(r.text, bugun, bolumler)
        if not resmi.eczaneler:
            hatalar.append("Oda sitesi: liste boş")
            resmi = None
    except Exception as e:  # noqa: BLE001
        hatalar.append(f"Oda sitesi: {e}")
    try:
        r = oturum.get(YEDEK_URL, timeout=30)
        r.raise_for_status()
        yedek = yedek_coz(r.text)                                # eşleştirme için bütün ilçeler
        if not yedek.eczaneler:
            hatalar.append("posta.com.tr: liste boş")
            yedek = None
    except Exception as e:  # noqa: BLE001
        hatalar.append(f"posta.com.tr: {e}")

    if resmi and yedek:
        return birlestir(resmi, yedek, log)
    if hatalar:
        log("Uyarı: " + "; ".join(hatalar))
    if resmi:
        log("Telefonlar eklenemedi; Eczacı Odası listesi telefonsuz kullanılıyor.")
        return resmi
    if yedek:
        if yedek_ilceler:
            yedek.eczaneler = [e for e in yedek.eczaneler if e.ilce in yedek_ilceler]
        if yedek.eczaneler:
            return yedek
    raise RuntimeError("Nöbetçi eczane listesi alınamadı: " + "; ".join(hatalar))
