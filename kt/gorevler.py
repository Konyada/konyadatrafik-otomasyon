"""Görevler: günün sözü, nöbetçi eczane, vefat listesi, yapay zekâ haberi."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable

from . import gorsel_kaynak, render
from .config import KOK
from .durum import Durum
from .kaynaklar import ajans as ajans_kaynak
from .kaynaklar import eczane as eczane_kaynak
from .kaynaklar import haber as haber_kaynak
from .kaynaklar import soz as soz_kaynak
from .kaynaklar import vefat as vefat_kaynak
from .tarih import tarih_yazi


@dataclass
class Sonuc:
    durum: str                      # paylasildi | atlandi | tekrar | hata
    mesaj: str
    gorseller: list[Path] = field(default_factory=list)
    medya: list[str] = field(default_factory=list)
    adresler: list[str] = field(default_factory=list)


@dataclass
class Baglam:
    cfg: dict
    tema: render.Tema
    durum: Durum
    simdi: datetime
    deneme: bool
    cikti: Path
    oturum: object
    yayinla: Callable[[list[Path], str], tuple[list[str], list[str]]]
    log: Callable[[str], None] = print

    @property
    def bugun(self):
        return self.simdi.date()


def soz(b: Baglam, slot: dict) -> Sonuc:
    s = soz_kaynak.gunun_sozu(b.bugun)
    yollar = render.gunun_sozu(b.tema, s["soz"], s.get("kaynak", "Atasözü"), tarih_yazi(b.bugun), b.cikti)
    medya, adresler = b.yayinla(yollar, "soz")
    return Sonuc("paylasildi", f"Günün sözü: {s['soz']}", yollar, medya, adresler)


def nobet_gecerli_mi(baslangic, simdi: datetime, saat: int = 8, dakika: int = 30) -> bool:
    """Merkez nöbeti başlangıç günü 08:30'dan ertesi gün 08:30'a kadar sürer."""
    bas = datetime(baslangic.year, baslangic.month, baslangic.day, saat, dakika, tzinfo=simdi.tzinfo)
    return bas <= simdi < bas + timedelta(days=1)


def eczane(b: Baglam, slot: dict) -> Sonuc:
    ayar = b.cfg.get("eczane", {})
    liste = eczane_kaynak.getir(b.oturum, b.bugun, tuple(ayar.get("bolumler", ["merkez"])),
                                ayar.get("yedek_ilceler"), log=b.log)
    if liste.baslangic and not nobet_gecerli_mi(liste.baslangic, b.simdi):
        if not b.deneme:
            return Sonuc("tekrar", f"Liste henüz güncellenmemiş (nöbet başlangıcı {liste.baslangic}).")
        b.log(f"  Deneme: liste {liste.baslangic} nöbetine ait (henüz başlamadı); görsel yine de üretiliyor.")
    telefonlu = sum(1 for e in liste.eczaneler if e.tel)
    if telefonlu < 0.8 * len(liste.eczaneler) and not b.deneme and not slot.get("elle"):
        saat, dakika = (int(x) for x in str(slot.get("saat", "00:00")).split(":"))
        if b.simdi - b.simdi.replace(hour=saat, minute=dakika, second=0, microsecond=0) < timedelta(minutes=60):
            return Sonuc("tekrar", f"{len(liste.eczaneler) - telefonlu} eczanenin telefonu henüz bulunamadı; "
                                   "15 dakika sonra tekrar denenecek.")
    alt_yazi = liste.pencere if liste.pencere and len(liste.pencere) <= 40 else tarih_yazi(liste.baslangic or b.bugun)
    yollar = render.nobetci_eczaneler(b.tema, eczane_kaynak.ilceye_gore(liste.eczaneler), alt_yazi, b.cikti)
    medya, adresler = b.yayinla(yollar, "eczane")
    return Sonuc("paylasildi", f"{len(liste.eczaneler)} nöbetçi eczane, tek story ({liste.kaynak}; "
                               f"{telefonlu} telefonlu)", yollar, medya, adresler)


def vefat(b: Baglam, slot: dict) -> Sonuc:
    kayitlar = vefat_kaynak.getir(b.oturum)
    bugunku = vefat_kaynak.gune_gore(kayitlar, b.bugun)
    if not bugunku:
        return Sonuc("tekrar", "Bugün için henüz vefat kaydı girilmemiş.")
    paylasilan = b.durum.vefat_paylasilan(b.bugun)
    yeni = [k for k in bugunku if k.anahtar() not in paylasilan]
    if not yeni:
        return Sonuc("atlandi", f"Bugünkü {len(bugunku)} kaydın hepsi daha önce paylaşıldı.")
    # Liste her zaman tek story'dir (render gerekirse küçültür / iki sütuna geçer).
    yollar = render.vefat_edenler(b.tema, [k.story() for k in yeni], tarih_yazi(b.bugun), b.cikti,
                                  dosya_on_ek=f"vefat-{b.simdi:%H%M}")
    *_, kapasite = render.vefat_duzeni(len(yeni))
    gosterilen = yeni if len(yeni) <= kapasite else yeni[:max(0, kapasite - 1)]   # aşırı kalabalıkta "+N kişi daha"
    medya, adresler = b.yayinla(yollar, "vefat")
    if not b.deneme:
        b.durum.vefat_ekle(b.bugun, [k.anahtar() for k in gosterilen])           # kalanlar sonraki story'de
    ek = f" ({len(yeni) - len(gosterilen)} kişi sonraki story'ye kaldı)" if len(gosterilen) < len(yeni) else ""
    return Sonuc("paylasildi", f"{len(gosterilen)} vefat kaydı, tek story{ek}", yollar, medya, adresler)


ORNEK_HABER = KOK / "data" / "ornek_haber.json"


def haber(b: Baglam, slot: dict) -> Sonuc:
    # Örnek haber: yalnızca ELLE başlatılan DENEME çalıştırmasında, tasarımı görmek için kullanılır.
    # Zamanlanmış görevler ve gerçek paylaşımlar bu dosyaya hiç bakmaz.
    ornek = None
    if b.deneme and slot.get("elle") and ORNEK_HABER.exists():
        ornek = json.loads(ORNEK_HABER.read_text(encoding="utf-8"))
        b.log("  Deneme: data/ornek_haber.json'daki örnek haber kullanılıyor (yapay zekâ çağrılmadı).")
    if ornek is None and not os.environ.get("ANTHROPIC_API_KEY"):
        return Sonuc("atlandi", "Claude API anahtarı (ANTHROPIC_API_KEY) tanımlı değil; haber atlandı.")
    ayar = b.cfg.get("haber", {})
    tur = slot.get("tur", "genel")
    gecmis = b.durum.haber_gecmisi(int(ayar.get("gecmis_gun", 5)), b.bugun)
    if ornek is not None:
        return _haber_story(b, ornek, tur)
    ajans_ayar = b.cfg.get("ajans") or {}
    adaylar = []
    if ajans_ayar.get("kaynaklar"):
        adaylar = ajans_kaynak.getir(
            b.oturum, ajans_ayar["kaynaklar"], b.simdi, int(ajans_ayar.get("son_saat", 24)),
            int(ajans_ayar.get("en_fazla_makale", 6)), gorulen_linkler={g.get("url") for g in gecmis}, log=b.log,
        )[: int(ajans_ayar.get("en_fazla_aday", 25))]
    h = haber_kaynak.haber_yaz(
        b.oturum, os.environ.get("ANTHROPIC_API_KEY", ""), ayar.get("model", "claude-sonnet-5-5"), tur,
        b.simdi, gecmis, editoryal=os.environ.get("EDITORIAL_GUIDE") or None,
        en_fazla_arama=int(ayar.get("en_fazla_arama", 3)), adaylar=adaylar,
    )
    if h is None:
        return Sonuc("atlandi", "Uygun ve yeni bir haber bulunamadı.")
    return _haber_story(b, h, tur)


def _haber_story(b: Baglam, h: dict, tur: str) -> Sonuc:
    foto, foto_notu = gorsel_kaynak.foto_bul(h, b.cfg, b.oturum, b.cikti, log=b.log)
    yollar = render.haber(b.tema, h["konum"], h["kategori"], h["baslik"], h["etiketler"], h["metin"],
                          h["kapanis"], tarih_yazi(b.bugun, gun_adi=False), b.cikti, foto=foto,
                          dosya_adi=f"haber-{tur}-{b.simdi:%H%M}.jpg", foto_notu=foto_notu)
    medya, adresler = b.yayinla(yollar, f"haber-{tur}")
    if not b.deneme:
        b.durum.haber_ekle(b.bugun, h["baslik"], h["kaynak_url"], h["kategori"])
    kaynak = f"{h['kaynak_adi']}" + (" (abone ajans/resmi kurum)" if h.get("ajans") else " (web)")
    foto_yazi = f"fotoğraf: {foto_notu or (foto.parent.name + '/' + foto.name)}" if foto else "fotoğrafsız"
    return Sonuc("paylasildi", f"[{h['kategori']}] {h['baslik']} — {kaynak}, {foto_yazi} — {h['kaynak_url']}",
                 yollar, medya, adresler)


GOREVLER = {"soz": soz, "eczane": eczane, "vefat": vefat, "haber": haber}
