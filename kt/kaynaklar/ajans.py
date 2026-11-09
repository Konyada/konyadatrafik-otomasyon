"""Abone olunan ajansların (İHA, DHA, AA) ve resmi kurumların (ör. Selçuklu Belediyesi) haberleri.

Ajanslar API vermediği için haberler kendi web sitelerindeki herkese açık sayfalardan okunur:
- "liste" türü: Konya haber listesi sayfasındaki haber bağlantıları bulunur, her haberin
  sayfasından başlık, özet, metin, fotoğraf ve tarih alınır (og:title, og:image, datePublished…).
- "rss" türü: RSS akışındaki başlık, özet, tarih ve fotoğraf alanları okunur (ör. AA).
Bu içerikler abonelik kapsamında kullanılır; fotoğrafların üzerine "Foto: İHA" gibi kaynak notu basılır.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from . import temiz
from ..tarih import TZ, tr_kucuk

KONYA_ILCELERI = [
    "Ahırlı", "Akören", "Akşehir", "Altınekin", "Beyşehir", "Bozkır", "Cihanbeyli", "Çeltik", "Çumra",
    "Derbent", "Derebucak", "Doğanhisar", "Emirgazi", "Ereğli", "Güneysınır", "Hadim", "Halkapınar",
    "Hüyük", "Ilgın", "Kadınhanı", "Karapınar", "Karatay", "Kulu", "Meram", "Sarayönü", "Selçuklu",
    "Seydişehir", "Taşkent", "Tuzlukçu", "Yalıhüyük", "Yunak",
]

OGE_ETIKETLERI = {"item", "entry", "haber", "news", "article"}
BASLIK = ("title", "baslik", "haberbaslik", "headline")
OZET = ("description", "summary", "ozet", "spot", "content", "icerik", "habermetni", "metin", "detay", "encoded")
BAGLANTI = ("link", "url", "haberurl", "guid", "haberlink")
TARIH = ("pubdate", "published", "updated", "date", "tarih", "yayintarihi", "haberzamani")
GORSEL = {"image", "resim", "foto", "fotograf", "photo", "picture", "imageurl", "resimurl", "fotourl",
          "buyukresim", "haberresim", "thumbnail"}
BASLIK_EKLERI = re.compile(r"\s*(\|.*|[-–]\s*(İHA|DHA|AA|Anadolu Ajansı).*|İhlas Haber Ajansı)\s*$", re.I)


@dataclass
class AjansHaberi:
    ajans: str                      # haberi veren kaynak adı (İHA, DHA, AA, Selçuklu Belediyesi…)
    baslik: str
    ozet: str = ""
    link: str = ""
    tarih: datetime | None = None
    gorsel: str = ""
    metin: str = ""
    kredi: str = ""                 # fotoğraf üzerine basılacak not, ör. "Foto: İHA"
    resmi: bool = False


# --------------------------------------------------------------------------- yardımcılar
def _yerel(etiket: str) -> str:
    return etiket.rsplit("}", 1)[-1].lower()


def tarih_coz(s: str | None) -> datetime | None:
    s = (s or "").strip()
    if not s:
        return None
    d = None
    try:
        d = parsedate_to_datetime(s)
    except (TypeError, ValueError, IndexError):
        pass
    if d is None:
        try:
            d = datetime.fromisoformat(s.replace("Z", "+00:00"))
        except ValueError:
            m = re.search(r"(\d{1,2})[./-](\d{1,2})[./-](\d{4})(?:\s+(\d{1,2}):(\d{2}))?", s)
            if not m:
                return None
            try:
                d = datetime(int(m.group(3)), int(m.group(2)), int(m.group(1)),
                             int(m.group(4) or 0), int(m.group(5) or 0))
            except ValueError:
                return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=TZ)
    return d.astimezone(TZ)


def konya_ile_ilgili(h: AjansHaberi) -> bool:
    metin = tr_kucuk(f"{h.baslik} {h.ozet} {h.metin[:600]}")
    return "konya" in metin or any(tr_kucuk(i) in metin for i in KONYA_ILCELERI)


# --------------------------------------------------------------------------- RSS
def akis_coz(xml_metni: str | bytes, ajans: str, kredi: str = "") -> list[AjansHaberi]:
    kok = ET.fromstring(xml_metni)
    sonuc: list[AjansHaberi] = []
    for oge in kok.iter():
        if _yerel(oge.tag) not in OGE_ETIKETLERI:
            continue
        alanlar: dict[str, str] = {}
        gorseller: list[str] = []
        for c in oge.iter():
            if c is oge:
                continue
            ad = _yerel(c.tag)
            tur = (c.get("type") or c.get("medium") or "").lower()
            url = c.get("url") or c.get("href") or ""
            if ad in ("enclosure", "content") and url and ("image" in tur or re.search(r"\.(jpe?g|png|webp)", url, re.I)):
                gorseller.append(url)
                continue
            if ad in GORSEL:
                deger = url or "".join(c.itertext()).strip()
                if deger.startswith("http"):
                    gorseller.append(deger)
                continue
            if ad == "link" and c.get("href"):
                alanlar.setdefault("link", c.get("href"))
                continue
            metin = "".join(c.itertext()).strip()
            if not metin:
                continue
            for anahtar, adaylar in (("baslik", BASLIK), ("ozet", OZET), ("link", BAGLANTI), ("tarih", TARIH)):
                if ad in adaylar and anahtar not in alanlar:
                    alanlar[anahtar] = metin
        baslik = temiz(alanlar.get("baslik", ""))
        if not baslik:
            continue
        ozet_ham = alanlar.get("ozet", "")
        if "<" in ozet_ham:
            soup = BeautifulSoup(ozet_ham, "html.parser")
            gorseller += [i.get("src") for i in soup.find_all("img") if i.get("src")]
            ozet_ham = soup.get_text(" ")
        gorsel = next((g for g in gorseller if g.startswith("http")), "")
        sonuc.append(AjansHaberi(ajans=ajans, baslik=baslik, ozet=temiz(ozet_ham), link=temiz(alanlar.get("link", "")),
                                 tarih=tarih_coz(alanlar.get("tarih")), gorsel=gorsel, kredi=kredi))
    return sonuc


# --------------------------------------------------------------------------- haber sayfası
def _meta(soup: BeautifulSoup, *adlar: str) -> str:
    for ad in adlar:
        el = soup.find("meta", attrs={"property": ad}) or soup.find("meta", attrs={"name": ad})
        if el and el.get("content", "").strip():
            return el["content"].strip()
    return ""


def makale_coz(html: str, url: str) -> dict:
    """Bir haber sayfasından başlık, özet, metin, fotoğraf ve yayın tarihini çıkarır."""
    soup = BeautifulSoup(html, "html.parser")
    baslik = _meta(soup, "og:title", "twitter:title")
    if not baslik:
        h1 = soup.find("h1")
        baslik = h1.get_text(" ") if h1 else (soup.title.get_text() if soup.title else "")
    baslik = BASLIK_EKLERI.sub("", temiz(baslik))
    ozet = temiz(_meta(soup, "og:description", "description", "twitter:description")).rstrip("…").strip()
    gorsel = _meta(soup, "og:image", "twitter:image", "og:image:url")
    if not gorsel:
        for img in soup.find_all("img"):
            src = img.get("data-src") or img.get("src") or ""
            if re.search(r"/(news|haber|contents|images|uploads)/", src, re.I) and not re.search(r"logo|icon|avatar", src, re.I):
                gorsel = src
                break
    tarih = None
    for blok in soup.find_all("script", attrs={"type": "application/ld+json"}):
        m = re.search(r'"datePublished"\s*:\s*"([^"]+)"', blok.get_text() or "")
        if m:
            tarih = tarih_coz(m.group(1))
            break
    if not tarih:
        tarih = tarih_coz(_meta(soup, "article:published_time", "pubdate", "date"))
    if not tarih:
        t = soup.find("time", attrs={"datetime": True})
        tarih = tarih_coz(t["datetime"]) if t else None
    if not tarih and gorsel:                                   # ör. .../News/2026/11/09/...jpg
        m = re.search(r"/(20\d{2})/(\d{1,2})/(\d{1,2})/", gorsel)
        if m:
            tarih = datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)), 12, 0, tzinfo=TZ)
    paragraflar = [temiz(p.get_text(" ")) for p in soup.find_all("p")]
    metin = " ".join(p for p in paragraflar if len(p) > 60)[:1800]
    return {"baslik": baslik, "ozet": ozet, "metin": metin,
            "gorsel": urljoin(url, gorsel) if gorsel else "", "tarih": tarih}


def liste_baglantilari(html: str, taban: str, desen: str) -> list[str]:
    bulunan = re.findall(desen, html)
    return list(dict.fromkeys(urljoin(taban, b) for b in bulunan))


# --------------------------------------------------------------------------- toplama
def kaynak_haberleri(oturum, kaynak: dict, simdi: datetime, son_saat: int = 24, en_fazla_makale: int = 6,
                     log=print) -> list[AjansHaberi]:
    ad = kaynak["ad"]
    kredi = kaynak.get("kredi", f"Foto: {ad}")
    sinir = simdi - timedelta(hours=son_saat)
    haberler: list[AjansHaberi] = []
    if kaynak.get("tur") == "rss":
        for adres in kaynak.get("adresler", []):
            r = oturum.get(adres, timeout=30)
            r.raise_for_status()
            haberler += akis_coz(r.content, ad, kredi)
    else:
        r = oturum.get(kaynak["liste"], timeout=30)
        r.raise_for_status()
        for link in liste_baglantilari(r.text, kaynak["liste"], kaynak["makale_deseni"])[:en_fazla_makale]:
            try:
                ra = oturum.get(link, timeout=30)
                ra.raise_for_status()
                m = makale_coz(ra.text, link)
            except Exception as e:  # noqa: BLE001
                log(f"  {ad}: bir haber okunamadı ({type(e).__name__})")
                continue
            if m["baslik"]:
                haberler.append(AjansHaberi(ajans=ad, baslik=m["baslik"], ozet=m["ozet"], link=link,
                                            tarih=m["tarih"], gorsel=m["gorsel"], metin=m["metin"], kredi=kredi))
    for h in haberler:
        h.resmi = bool(kaynak.get("resmi"))
    hepsi_konya = bool(kaynak.get("hepsi_konya"))
    uygun = [h for h in haberler
             if (hepsi_konya or konya_ile_ilgili(h)) and (h.tarih is None or h.tarih >= sinir)]
    return uygun


def getir(oturum, kaynaklar: list[dict], simdi: datetime, son_saat: int = 24, en_fazla_makale: int = 6,
          gorulen_linkler: set[str] | None = None, log=print) -> list[AjansHaberi]:
    gorulen_linkler = gorulen_linkler or set()
    hepsi: list[AjansHaberi] = []
    for kaynak in kaynaklar:
        if not kaynak.get("aktif", True):
            continue
        try:
            haberler = kaynak_haberleri(oturum, kaynak, simdi, son_saat, en_fazla_makale, log)
        except Exception as e:  # noqa: BLE001
            log(f"  {kaynak['ad']}: haberler okunamadı ({type(e).__name__}: {str(e)[:120]})")
            continue
        yeni = [h for h in haberler if h.link not in gorulen_linkler]
        log(f"  {kaynak['ad']}: {len(yeni)} yeni Konya haberi")
        hepsi.extend(yeni)
    hepsi.sort(key=lambda h: h.tarih or simdi, reverse=True)
    return hepsi
