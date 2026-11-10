"""Story tasarım motoru: 1080x1920 JPEG görseller (Pillow).

Tasarımlar Konya'da Trafik'in kendi şablonlarına göre hazırlandı:
- Liste şablonları (vefat, nöbetçi eczane, günün sözü): koyu yeşil zemin, ortada logo,
  "KONYA'DA BUGÜN" üst başlığı, beyaz kart içinde satırlar, altta dilek cümlesi.
- Haber şablonu: üstte fotoğraf, sağ üstte logo, kırmızı konum + yeşil kategori etiketi,
  büyük başlık, çerçeveli kısa bilgi etiketleri, metin, yeşil kapanış cümlesi, tarih ve hesap adı.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

from .config import KOK
from .tarih import tr_buyuk

W, H = 1080, 1920
KART_X1, KART_X2 = 60, 1020
IC_X1, IC_X2 = 100, 980             # kart içi yazı hizası
DIPNOT_TABAN = 1841                 # en alttaki küçük yazının taban çizgisi

FONT_DOSYA = {
    "regular": "Inter-Regular.otf", "medium": "Inter-Medium.otf", "semibold": "Inter-SemiBold.otf",
    "bold": "Inter-Bold.otf", "extrabold": "Inter-ExtraBold.otf", "black": "Inter-Black.otf",
    "italic": "Inter-Italic.otf",
}


@dataclass
class Tema:
    zemin: tuple = (10, 24, 16)          # haber zemini
    zemin_ust: tuple = (10, 35, 21)      # liste şablonu üst
    zemin_alt: tuple = (15, 22, 14)      # liste şablonu alt
    isilti: tuple = (24, 64, 32)         # logo arkasındaki yeşil ışıltı (eklenen değer)
    yesil: tuple = (14, 149, 63)
    acik_yesil: tuple = (120, 210, 150)
    kirmizi: tuple = (214, 40, 40)
    beyaz: tuple = (245, 245, 240)
    soluk: tuple = (190, 210, 195)
    kart: tuple = (255, 255, 255)
    kart_alt: tuple = (238, 246, 240)
    koyu_metin: tuple = (20, 32, 26)
    mezarlik: tuple = (70, 112, 90)
    telefon: tuple = (11, 122, 51)
    tarif: tuple = (91, 117, 102)
    ayrac: tuple = (226, 232, 228)
    govde: tuple = (200, 214, 206)
    altbilgi: tuple = (150, 175, 160)
    logo: str = "assets/logo.png"
    instagram: str = "konyada_trafik"
    jpeg_kalite: int = 90

    @classmethod
    def configden(cls, cfg: dict) -> "Tema":
        t = cls()
        for anahtar, deger in (cfg.get("tasarim") or {}).items():
            if hasattr(t, anahtar):
                if isinstance(getattr(t, anahtar), tuple) and isinstance(deger, str):
                    deger = _rgb(deger)
                setattr(t, anahtar, deger)
        t.instagram = (cfg.get("sayfa") or {}).get("instagram", t.instagram)
        return t


# --------------------------------------------------------------------------- yardımcılar
def _rgb(hex_renk: str) -> tuple[int, int, int]:
    h = hex_renk.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


@lru_cache(maxsize=128)
def font(agirlik: str, boyut: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(KOK / "assets" / "fonts" / FONT_DOSYA[agirlik]), boyut)


def genislik(metin: str, f: ImageFont.FreeTypeFont) -> float:
    return f.getlength(metin)


def satirlara_bol(metin: str, f: ImageFont.FreeTypeFont, max_gen: float) -> list[str]:
    satirlar: list[str] = []
    for paragraf in metin.split("\n"):
        kelimeler = paragraf.split()
        if not kelimeler:
            satirlar.append("")
            continue
        satir = ""
        for k in kelimeler:
            aday = f"{satir} {k}".strip()
            if genislik(aday, f) <= max_gen:
                satir = aday
                continue
            if satir:
                satirlar.append(satir)
            while genislik(k, f) > max_gen:          # tek kelime bile sığmıyorsa böl
                kes = len(k)
                while kes > 1 and genislik(k[:kes] + "-", f) > max_gen:
                    kes -= 1
                satirlar.append(k[:kes] + "-")
                k = k[kes:]
            satir = k
        satirlar.append(satir)
    return satirlar


def kisalt(metin: str, f: ImageFont.FreeTypeFont, max_gen: float) -> str:
    if genislik(metin, f) <= max_gen:
        return metin
    while metin and genislik(metin + "…", f) > max_gen:
        metin = metin[:-1]
    return metin.rstrip(" ,.;:-–") + "…"


def sigdir(metin: str, agirlik: str, en_buyuk: int, en_kucuk: int, max_gen: float,
           en_fazla_satir: int, adim: int = 2) -> tuple[ImageFont.FreeTypeFont, list[str]]:
    boyut = en_buyuk
    while boyut >= en_kucuk:
        f = font(agirlik, boyut)
        satirlar = satirlara_bol(metin, f, max_gen)
        if len(satirlar) <= en_fazla_satir:
            return f, satirlar
        boyut -= adim
    f = font(agirlik, en_kucuk)
    satirlar = satirlara_bol(metin, f, max_gen)[:en_fazla_satir]
    satirlar[-1] = kisalt(satirlar[-1] + " …", f, max_gen)
    return f, satirlar


def _ortala(ciz: ImageDraw.ImageDraw, y_taban: float, metin: str, f, renk) -> None:
    ciz.text((W / 2, y_taban), metin, font=f, fill=renk, anchor="ms")


def _kaydet(img: Image.Image, yol: Path, kalite: int) -> Path:
    yol.parent.mkdir(parents=True, exist_ok=True)
    img.convert("RGB").save(yol, "JPEG", quality=kalite, optimize=True, subsampling=0)
    return yol


@lru_cache(maxsize=8)
def _logo(yol: str, cap: int) -> Image.Image | None:
    p = KOK / yol
    if not p.exists():
        return None
    logo = Image.open(p).convert("RGBA")
    k = min(logo.size)
    logo = logo.crop(((logo.width - k) // 2, (logo.height - k) // 2, (logo.width + k) // 2, (logo.height + k) // 2))
    return logo.resize((cap, cap), Image.LANCZOS)


def logo_yapistir(img: Image.Image, tema: Tema, x: int, y: int, cap: int) -> None:
    logo = _logo(tema.logo, cap)
    if logo is not None:
        img.alpha_composite(logo, (x, y))
        return
    ciz = ImageDraw.Draw(img)            # logo dosyası yoksa geçici rozet
    ciz.ellipse((x, y, x + cap, y + cap), fill=tema.yesil, outline=(0, 0, 0), width=max(3, cap // 40))
    ciz.text((x + cap / 2, y + cap / 2), "KT", font=font("black", cap // 3), fill=(255, 255, 255), anchor="mm")


def _isiltili_zemin(tema: Tema, kompakt: bool = False) -> Image.Image:
    """Üstten alta koyu yeşil geçiş + logonun arkasında yumuşak yeşil ışıltı."""
    merkez, yaricap = ((540, 155), 290) if kompakt else ((540, 195), 360)
    return _zemin_hazirla(tema.zemin_ust, tema.zemin_alt, tema.isilti, merkez, yaricap).copy()


@lru_cache(maxsize=4)
def _zemin_hazirla(zemin_ust, zemin_alt, isilti, merkez, yaricap) -> Image.Image:
    kucuk_w, kucuk_h = W // 4, H // 4
    zemin = Image.new("RGB", (kucuk_w, kucuk_h))
    px = zemin.load()
    mx, my, r = merkez[0] / 4, merkez[1] / 4, yaricap / 4
    for y in range(kucuk_h):
        t = y / (kucuk_h - 1)
        taban = [zemin_ust[i] + (zemin_alt[i] - zemin_ust[i]) * t for i in range(3)]
        for x in range(kucuk_w):
            d = math.hypot(x - mx, y - my)
            g = max(0.0, 1 - d / r) ** 2
            px[x, y] = tuple(int(min(255, taban[i] + isilti[i] * g)) for i in range(3))
    return zemin.resize((W, H), Image.BICUBIC).convert("RGBA")


LISTE_Y0, KOMPAKT_Y0 = 590, 455      # liste kartının başladığı y (normal / kalabalık günler için kompakt başlık)


def _liste_basligi(img: Image.Image, tema: Tema, baslik: str, tarih_yazisi: str,
                   ust_yazi: str = "KONYA'DA BUGÜN", kompakt: bool = False) -> int:
    """Ortada logo + üst başlık + büyük başlık + tarih + yeşil çizgi. Kartın başlayacağı y'yi döndürür."""
    ciz = ImageDraw.Draw(img)
    if kompakt:                                   # aynı düzen, daha küçük logo ve yazılar
        logo_yapistir(img, tema, (W - 150) // 2, 80, 150)
        _ortala(ciz, 282, ust_yazi, font("semibold", 30), tema.acik_yesil)
        f, _ = sigdir(tr_buyuk(baslik), "bold", 68, 48, W - 2 * 70, 1)
        _ortala(ciz, 356, tr_buyuk(baslik), f, tema.beyaz)
        _ortala(ciz, 404, tarih_yazisi, font("regular", 30), tema.soluk)
        ciz.rounded_rectangle((W / 2 - 60, 424, W / 2 + 60, 430), radius=3, fill=tema.yesil)
        return KOMPAKT_Y0
    logo_yapistir(img, tema, (W - 230) // 2, 80, 230)
    _ortala(ciz, 380, ust_yazi, font("semibold", 34), tema.acik_yesil)
    f, _ = sigdir(tr_buyuk(baslik), "bold", 84, 56, W - 2 * 70, 1)
    _ortala(ciz, 470, tr_buyuk(baslik), f, tema.beyaz)
    _ortala(ciz, 529, tarih_yazisi, font("regular", 34), tema.soluk)
    ciz.rounded_rectangle((W / 2 - 70, 552, W / 2 + 70, 558), radius=3, fill=tema.yesil)
    return LISTE_Y0


def _kart(img: Image.Image, tema: Tema, y1: int, y2: int) -> ImageDraw.ImageDraw:
    ciz = ImageDraw.Draw(img)
    ciz.rounded_rectangle((KART_X1, y1, KART_X2, y2), radius=26, fill=tema.kart)
    return ciz


def _alt_yazilar(img: Image.Image, tema: Tema, kart_alt: int, dilek: list[str], dipnot: str) -> None:
    ciz = ImageDraw.Draw(img)
    y = kart_alt + 58 + 30                     # ilk satırın taban çizgisi
    for satir in dilek:
        _ortala(ciz, y, satir, font("medium", 40), tema.beyaz)
        y += 52
    if dipnot:
        _ortala(ciz, DIPNOT_TABAN, dipnot, font("regular", 23), tema.soluk)


def _dilek_yuksekligi(satir_sayisi: int) -> int:
    return 58 + satir_sayisi * 52 if satir_sayisi else 0


# --------------------------------------------------------------------------- vefat
# Liste her zaman TEK story'dir: kayıt sayısı arttıkça satırlar küçülür, gerekirse iki sütuna geçilir.
VEFAT_DILEK = ["Allah rahmet eylesin,", "mekânları cennet olsun."]
VEFAT_UST, VEFAT_ALT = 10, 23                 # kart içi üst / alt boşluk


def _vefat_adaylari():
    """Büyükten küçüğe denenecek düzenler: (kompakt başlık, sütun, satır yüksekliği)."""
    for satir in range(64, 49, -2):           # tek sütun, şablondaki boyuttan başlayarak
        yield False, 1, satir
    for satir in range(64, 53, -2):           # iki sütun (ad üstte, mezarlık altta)
        yield False, 2, satir
    for satir in range(58, 45, -2):           # iki sütun + küçük başlık (çok kalabalık günler)
        yield True, 2, satir


def vefat_duzeni(adet: int) -> tuple[bool, int, int, int]:
    """(kompakt, sütun, satır yüksekliği, kapasite): bütün kayıtları tek sayfaya sığdıran en büyük düzen.
    Hiçbiri yetmezse en küçük düzen döner; sığmayanlar son hücrede "+N kişi daha" olarak yazılır."""
    sinir = DIPNOT_TABAN - 40 - _dilek_yuksekligi(len(VEFAT_DILEK))      # kartın inebileceği en alt nokta
    duzen = (False, 1, 64, 0)
    for kompakt, sutun, satir in _vefat_adaylari():
        y0 = KOMPAKT_Y0 if kompakt else LISTE_Y0
        kapasite = sutun * ((sinir - y0 - VEFAT_UST - VEFAT_ALT) // satir)
        duzen = (kompakt, sutun, satir, kapasite)
        if adet <= kapasite:
            break
    return duzen


def vefat_edenler(tema: Tema, kayitlar: list[dict], tarih_yazisi: str, cikti: Path,
                  dosya_on_ek: str = "vefat") -> list[Path]:
    """kayitlar: [{ad, defin}] — ad 'Hatice Muratoğlu', defin 'Seyit Şahin (Kurtuluş)'. Tek görsel üretir."""
    kompakt, sutun, satir, kapasite = vefat_duzeni(len(kayitlar))
    gosterilen, tasan = list(kayitlar), 0
    if len(gosterilen) > kapasite:
        gosterilen = gosterilen[:max(0, kapasite - 1)]
        tasan = len(kayitlar) - len(gosterilen)
    hucre = len(gosterilen) + (1 if tasan else 0)
    satir_sayisi = max(1, math.ceil(hucre / sutun))

    img = _isiltili_zemin(tema, kompakt)
    y0 = _liste_basligi(img, tema, "Vefat Edenler", tarih_yazisi, kompakt=kompakt)
    ust0 = y0 + VEFAT_UST
    kart_alt = ust0 + satir_sayisi * satir + VEFAT_ALT
    ciz = _kart(img, tema, y0, kart_alt)
    for r in range(1, satir_sayisi, 2):                       # şablondaki gibi açık yeşil ara satırlar
        ciz.rectangle((KART_X1, ust0 + r * satir, KART_X2, ust0 + (r + 1) * satir), fill=tema.kart_alt)

    if sutun == 1:
        f_ad, f_yer = font("semibold", round(36 * satir / 64)), font("regular", round(29 * satir / 64))
        taban = round(44 * satir / 64)
        for i, k in enumerate(gosterilen):
            ust = ust0 + i * satir
            yer = kisalt(k.get("defin", ""), f_yer, 380)
            ciz.text((IC_X2, ust + taban), yer, font=f_yer, fill=tema.mezarlik, anchor="rs")
            ad = kisalt(k.get("ad", ""), f_ad, IC_X2 - IC_X1 - genislik(yer, f_yer) - 24)
            ciz.text((IC_X1, ust + taban), ad, font=f_ad, fill=tema.koyu_metin, anchor="ls")
    else:
        aralik = 40
        sutun_gen = (IC_X2 - IC_X1 - aralik) / 2
        f_ad, f_yer = font("semibold", round(0.43 * satir)), font("regular", round(0.33 * satir))
        t_ad, t_yer = round(0.42 * satir), round(0.84 * satir)
        orta = (IC_X1 + IC_X2) / 2
        ciz.line((orta, ust0 + 10, orta, ust0 + satir_sayisi * satir - 10), fill=tema.ayrac, width=2)

        def hucre_yaz(sira: int, ust_yazi: str, alt_yazi: str, renk) -> None:
            s_no, r = divmod(sira, satir_sayisi)                # önce sol sütun dolar
            x, ust = IC_X1 + s_no * (sutun_gen + aralik), ust0 + r * satir
            ciz.text((x, ust + t_ad), kisalt(ust_yazi, f_ad, sutun_gen), font=f_ad, fill=renk, anchor="ls")
            ciz.text((x, ust + t_yer), kisalt(alt_yazi, f_yer, sutun_gen), font=f_yer, fill=tema.mezarlik,
                     anchor="ls")

        for i, k in enumerate(gosterilen):
            hucre_yaz(i, k.get("ad", ""), k.get("defin", ""), tema.koyu_metin)
        if tasan:
            hucre_yaz(len(gosterilen), f"+{tasan} kişi daha", "mezarlik.konya.bel.tr", tema.yesil)

    _alt_yazilar(img, tema, kart_alt, VEFAT_DILEK, "Kaynak: Konya Büyükşehir Belediyesi Mezarlık Bilgi Sistemi")
    return [_kaydet(img, cikti / f"{dosya_on_ek}.jpg", tema.jpeg_kalite)]


# --------------------------------------------------------------------------- nöbetçi eczane
# Liste her zaman TEK story'dir: eczane sayısı arttıkça satırlar küçülür; çok kalabalıkta tarif satırı
# düşer, en son iki sütuna geçilir.
ECZ_DILEK = ["Geçmiş olsun, sağlıklı günler."]
ECZ_DIPNOT = "Nöbet listesi değişebilir, gitmeden önce telefonla teyit edin."
ECZ_UST, ECZ_ALT, ECZ_ARA = 20, 20, 10        # kart içi üst / alt boşluk, ilçeler arası boşluk


@dataclass(frozen=True)
class EczDuzen:
    kompakt: bool        # küçük başlık
    sutun: int           # 1 veya 2
    tip: str             # "tarifli": ad + tel / tarif · "tek": ad + tel · "cift": ad / tel (iki sütunda)
    satir: int           # eczane satırı yüksekliği
    bolum: int           # ilçe başlığı (yeşil bant) yüksekliği


def _ecz_adaylari():
    for satir in range(75, 61, -1):
        yield EczDuzen(False, 1, "tarifli", satir, 44)       # şablondaki boyuttan başlayarak
    for satir in range(75, 61, -1):
        yield EczDuzen(True, 1, "tarifli", satir, 44)
    for satir in range(52, 39, -2):
        yield EczDuzen(True, 1, "tek", satir, 40)
    for satir in range(62, 45, -2):
        yield EczDuzen(True, 2, "cift", satir, 38)


def _ecz_ogeler(gruplar: list[tuple[str, list[dict]]]) -> list[tuple[str, object]]:
    ogeler: list[tuple[str, object]] = []
    for ilce, eczaneler in gruplar:
        if eczaneler:
            ogeler.append(("bolum", ilce))
            ogeler.extend(("eczane", e) for e in eczaneler)
    return ogeler


def _sutun_yuksekligi(ogeler: list[tuple[str, object]], d: EczDuzen) -> int:
    y = 0
    for i, (tur, _) in enumerate(ogeler):
        if tur == "bolum":
            y += (ECZ_ARA if i else 0) + d.bolum
        else:
            y += d.satir
    return y


def _sutunlara_bol(ogeler: list[tuple[str, object]], d: EczDuzen) -> list[list[tuple[str, object]]]:
    if d.sutun == 1 or len(ogeler) < 2:
        return [ogeler]
    en_iyi = None
    for k in range(1, len(ogeler)):
        sol, sag = ogeler[:k], ogeler[k:]
        if sol[-1][0] == "bolum":                 # sütun ilçe başlığıyla bitmesin
            continue
        if sag[0][0] != "bolum":                  # ilçe ikinci sütuna taşıyorsa başlığı tekrarla
            onceki = next(o[1] for o in reversed(sol) if o[0] == "bolum")
            sag = [("bolum", f"{onceki} (devam)")] + sag
        yuk = max(_sutun_yuksekligi(sol, d), _sutun_yuksekligi(sag, d))
        if en_iyi is None or yuk < en_iyi[0]:
            en_iyi = (yuk, [sol, sag])
    return en_iyi[1] if en_iyi else [ogeler]


def eczane_duzeni(gruplar: list[tuple[str, list[dict]]]) -> tuple[EczDuzen, list[list[tuple[str, object]]], int]:
    """(düzen, sütunlar, sığmayan eczane sayısı): bütün listeyi tek sayfaya sığdıran en büyük düzen."""
    sinir = DIPNOT_TABAN - 40 - _dilek_yuksekligi(len(ECZ_DILEK))
    ogeler = _ecz_ogeler(gruplar)

    def sigar(d, sutunlar):
        y0 = KOMPAKT_Y0 if d.kompakt else LISTE_Y0
        return y0 + ECZ_UST + max(_sutun_yuksekligi(s, d) for s in sutunlar) + ECZ_ALT <= sinir

    d = None
    for d in _ecz_adaylari():
        sutunlar = _sutunlara_bol(ogeler, d)
        if sigar(d, sutunlar):
            return d, sutunlar, 0
    # Hiçbir düzen yetmedi (çok olağan dışı): sondan eczane eksilt, son satıra "+N eczane daha" yaz.
    toplam = sum(1 for t, _ in ogeler if t == "eczane")
    while ogeler:
        ogeler = ogeler[:-1]
        while ogeler and ogeler[-1][0] == "bolum":
            ogeler = ogeler[:-1]
        tasan = toplam - sum(1 for t, _ in ogeler if t == "eczane")
        aday = ogeler + [("not", f"+{tasan} eczane daha · konyanobetcieczaneleri.com")]
        sutunlar = _sutunlara_bol(aday, d)
        if sigar(d, sutunlar):
            return d, sutunlar, tasan
    return d, [[]], toplam


def nobetci_eczaneler(tema: Tema, gruplar: list[tuple[str, list[dict]]], tarih_yazisi: str,
                      cikti: Path) -> list[Path]:
    """gruplar: [("Selçuklu", [{ad, tel, tarif}]), ...] — tek görsel üretir."""
    d, sutunlar, _ = eczane_duzeni(gruplar)
    img = _isiltili_zemin(tema, d.kompakt)
    y0 = _liste_basligi(img, tema, "Nöbetçi Eczaneler", tarih_yazisi, kompakt=d.kompakt)
    kart_alt = y0 + ECZ_UST + max([_sutun_yuksekligi(s, d) for s in sutunlar] + [0]) + ECZ_ALT
    ciz = _kart(img, tema, y0, kart_alt)

    o = d.satir / 75
    if d.tip == "tarifli":
        f_ad, f_tel, f_tarif = font("semibold", round(30 * o)), font("bold", round(26 * o)), font("regular", round(23 * o))
        t_ad, t_alt, ayrac_y = round(38 * o), round(70 * o), round(7 * o)
    elif d.tip == "tek":
        f_ad, f_tel, f_tarif = font("semibold", min(30, round(0.6 * d.satir))), font("bold", min(26, round(0.52 * d.satir))), None
        t_ad, t_alt, ayrac_y = round(0.64 * d.satir), 0, 2
    else:
        f_ad, f_tel, f_tarif = font("semibold", round(0.43 * d.satir)), font("bold", round(0.34 * d.satir)), None
        t_ad, t_alt, ayrac_y = round(0.42 * d.satir), round(0.86 * d.satir), 2
    f_bolum = font("bold", round(26 * d.bolum / 44))

    if d.sutun == 1:
        bantlar = [(KART_X1, KART_X2)]
    else:
        bantlar = [(KART_X1, W / 2 - 6), (W / 2 + 6, KART_X2)]
    for (b1, b2), sutun in zip(bantlar, sutunlar):
        x1, x2 = (IC_X1, IC_X2) if d.sutun == 1 else (b1 + 30, b2 - 30)
        y = y0 + ECZ_UST
        onceki = None
        for i, (tur, deger) in enumerate(sutun):
            if tur == "bolum":
                y += ECZ_ARA if i else 0
                ciz.rectangle((b1, y, b2, y + d.bolum), fill=tema.yesil)
                ciz.text((x1, y + d.bolum / 2 + 1), tr_buyuk(str(deger)), font=f_bolum, fill=(255, 255, 255), anchor="lm")
                y += d.bolum
            elif tur == "not":
                ciz.text((x1, y + t_ad), kisalt(str(deger), f_ad, x2 - x1), font=f_ad, fill=tema.yesil, anchor="ls")
                y += d.satir
            else:
                e = deger
                if onceki == "eczane":
                    ciz.line((x1, y + ayrac_y, x2, y + ayrac_y), fill=tema.ayrac, width=2)
                tel = e.get("tel", "")
                if d.tip == "cift":
                    ciz.text((x1, y + t_ad), kisalt(e.get("ad", ""), f_ad, x2 - x1), font=f_ad,
                             fill=tema.koyu_metin, anchor="ls")
                    if tel:
                        ciz.text((x1, y + t_alt), tel, font=f_tel, fill=tema.telefon, anchor="ls")
                else:
                    tel_gen = genislik(tel, f_tel) if tel else 0
                    ciz.text((x1, y + t_ad), kisalt(e.get("ad", ""), f_ad, x2 - x1 - tel_gen - 24), font=f_ad,
                             fill=tema.koyu_metin, anchor="ls")
                    if tel:
                        ciz.text((x2, y + t_ad), tel, font=f_tel, fill=tema.telefon, anchor="rs")
                    if f_tarif is not None and e.get("tarif"):
                        ciz.text((x1, y + t_alt), kisalt(e.get("tarif", ""), f_tarif, x2 - x1), font=f_tarif,
                                 fill=tema.tarif, anchor="ls")
                y += d.satir
            onceki = tur
    _alt_yazilar(img, tema, kart_alt, ECZ_DILEK, ECZ_DIPNOT)
    return [_kaydet(img, cikti / "nobetci-eczane.jpg", tema.jpeg_kalite)]


# --------------------------------------------------------------------------- günün sözü
def gunun_sozu(tema: Tema, soz: str, kaynak: str, tarih_yazisi: str, cikti: Path) -> list[Path]:
    img = _isiltili_zemin(tema)
    _liste_basligi(img, tema, "Günün Sözü", tarih_yazisi)
    f, satirlar = sigdir(soz, "semibold", 74, 40, IC_X2 - IC_X1, 9)
    pay = int(f.size * 1.32)
    kart_yuk = 60 + 120 + len(satirlar) * pay + 40 + 50 + 50
    blok = kart_yuk + _dilek_yuksekligi(1)
    y0 = 590 + max(0, (1780 - 590 - blok) // 2)          # tek söz olduğu için dikeyde ortala
    kart_alt = y0 + kart_yuk
    ciz = _kart(img, tema, y0, kart_alt)
    ciz.text((IC_X1 - 6, y0 + 40), "“", font=font("black", 170), fill=tema.yesil, anchor="la")
    y = y0 + 60 + 120
    for s in satirlar:
        ciz.text((IC_X1, y + f.size), s, font=f, fill=tema.koyu_metin, anchor="ls")
        y += pay
    ciz.text((IC_X1, y + 40 + 30), f"— {kaynak}", font=font("semibold", 32), fill=tema.yesil, anchor="ls")
    _alt_yazilar(img, tema, kart_alt, ["Hayırlı sabahlar Konya."], f"@{tema.instagram}")
    return [_kaydet(img, cikti / "gunun-sozu.jpg", tema.jpeg_kalite)]


# --------------------------------------------------------------------------- haber
def _etiket(ciz: ImageDraw.ImageDraw, x: int, y: int, metin: str, dolgu, yazi_rengi, f, yukseklik: int,
            yaricap: int, cerceve=None, ic_bosluk: int = 22) -> int:
    g = genislik(metin, f)
    x2 = x + g + 2 * ic_bosluk
    if cerceve:
        ciz.rounded_rectangle((x, y, x2, y + yukseklik), radius=yaricap, outline=cerceve, width=2)
    else:
        ciz.rounded_rectangle((x, y, x2, y + yukseklik), radius=yaricap, fill=dolgu)
    ciz.text((x + ic_bosluk, y + yukseklik / 2 + 1), metin, font=f, fill=yazi_rengi, anchor="lm")
    return int(x2)


def _fotograf_katmani(foto: Path, yukseklik: int, tema: Tema) -> Image.Image:
    with Image.open(foto) as im:
        im = ImageOps.exif_transpose(im).convert("RGB")
        im = ImageOps.fit(im, (W, yukseklik), Image.LANCZOS, centering=(0.5, 0.45))
    katman = Image.new("RGBA", (W, H), (*tema.zemin, 255))
    katman.paste(im, (0, 0))
    # alt kısmı zemine doğru yumuşakça karart
    gecis = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gc = ImageDraw.Draw(gecis)
    bas = max(0, yukseklik - 260)
    for y in range(bas, yukseklik):
        a = int(255 * ((y - bas) / max(1, yukseklik - bas)) ** 1.4)
        gc.line((0, y, W, y), fill=(*tema.zemin, a))
    katman.alpha_composite(gecis)
    return katman


def _foto_notu(img: Image.Image, metin: str, y_alt: int) -> None:
    """Fotoğrafın sağ alt köşesine 'Foto: İHA' / 'Temsili görsel' notu."""
    f = font("medium", 22)
    g = genislik(metin, f)
    x2, x1 = W - 70, W - 70 - g - 28
    katman = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ciz = ImageDraw.Draw(katman)
    ciz.rounded_rectangle((x1, y_alt - 38, x2, y_alt), radius=19, fill=(0, 0, 0, 150))
    ciz.text((x1 + 14, y_alt - 19), metin, font=f, fill=(255, 255, 255, 235), anchor="lm")
    img.alpha_composite(katman)


def haber(tema: Tema, konum: str, kategori: str, baslik_metin: str, etiketler: list[str], metin: str,
          kapanis: str, tarih_yazisi: str, cikti: Path, foto: Path | None = None,
          dosya_adi: str = "haber.jpg", foto_notu: str = "") -> list[Path]:
    ic_gen = W - 2 * 70
    f_et, f_cerceve = font("bold", 29), font("semibold", 30)
    f_kap = font("semibold", 32)

    def yerlesim(b_boyut: int, g_boyut: int, en_fazla_govde: int):
        f_b = font("bold", b_boyut)
        b_sat = satirlara_bol(baslik_metin, f_b, ic_gen)
        if len(b_sat) > 4:
            b_sat = b_sat[:4]
            b_sat[-1] = kisalt(b_sat[-1] + " …", f_b, ic_gen)
        f_g = font("regular", g_boyut)
        g_sat = satirlara_bol(metin, f_g, ic_gen)
        if len(g_sat) > en_fazla_govde:
            g_sat = g_sat[:en_fazla_govde]
            g_sat[-1] = kisalt(g_sat[-1] + " …", f_g, ic_gen)
        k_sat = satirlara_bol(kapanis, f_kap, ic_gen)[:2] if kapanis else []
        b_pay, g_pay = int(b_boyut * 1.28), int(g_boyut * 1.42)
        yuk = 60 + 30                                   # etiket satırı + boşluk
        yuk += (len(b_sat) - 1) * b_pay + int(b_boyut * 1.18)
        yuk += (38 + 55) if etiketler else 0
        yuk += 36 + (len(g_sat) - 1) * g_pay + int(g_boyut * 1.2) if g_sat else 0
        yuk += (46 + (len(k_sat) - 1) * 44 + 36) if k_sat else 0
        return f_b, b_sat, b_pay, f_g, g_sat, g_pay, k_sat, yuk

    alt_sinir = 1772
    ust_sinir = 470 if foto else 380
    for b_boyut, g_boyut, govde_satir in ((61, 31, 12), (56, 29, 12), (52, 27, 11), (48, 26, 9)):
        f_b, b_sat, b_pay, f_g, g_sat, g_pay, k_sat, yuk = yerlesim(b_boyut, g_boyut, govde_satir)
        if alt_sinir - yuk >= ust_sinir:
            break
    if foto:
        y_etiket = max(ust_sinir, min(1150, alt_sinir - yuk))       # fotoğraf büyük kalsın: içerik alta
    else:
        y_etiket = max(ust_sinir, ust_sinir + (alt_sinir - ust_sinir - yuk) // 2)   # fotoğrafsız: ortala

    if foto:
        img = _fotograf_katmani(foto, y_etiket + 100, tema)
        logo_yapistir(img, tema, 890, 170, 130)
        if foto_notu:
            _foto_notu(img, foto_notu, y_etiket - 20)
    else:
        img = _isiltili_zemin(tema)
        logo_yapistir(img, tema, (W - 230) // 2, 80, 230)
    ciz = ImageDraw.Draw(img)

    x = _etiket(ciz, 70, y_etiket, tr_buyuk(konum or "Konya"), tema.kirmizi, (255, 255, 255), f_et, 60, 10)
    _etiket(ciz, x + 14, y_etiket, tr_buyuk(kategori), tema.yesil, (255, 255, 255), f_et, 60, 10)
    y = y_etiket + 60 + 30
    taban = y + int(f_b.size * 0.97)
    for s in b_sat:
        ciz.text((70, taban), s, font=f_b, fill=tema.beyaz, anchor="ls")
        taban += b_pay
    son_taban = taban - b_pay
    y = son_taban + int(f_b.size * 0.21)
    if etiketler:
        y += 38 - int(f_b.size * 0.21)
        x = 70
        for et in etiketler[:2]:
            et = kisalt(et, f_cerceve, 420)
            if x + genislik(et, f_cerceve) + 40 > W - 70:
                break
            x = _etiket(ciz, x, y, et, None, tema.acik_yesil, f_cerceve, 55, 28, cerceve=tema.acik_yesil, ic_bosluk=20) + 14
        y += 55
    if g_sat:
        taban = y + 36 + int(f_g.size * 0.97)
        for s in g_sat:
            ciz.text((70, taban), s, font=f_g, fill=tema.govde, anchor="ls")
            taban += g_pay
        y = taban - g_pay
    if k_sat:
        taban = y + 46 + int(f_kap.size * 0.97) - 10
        for s in k_sat:
            ciz.text((70, taban), s, font=f_kap, fill=tema.acik_yesil, anchor="ls")
            taban += 44
    f_alt = font("regular", 30)
    ciz.text((70, 1840), tarih_yazisi, font=f_alt, fill=tema.altbilgi, anchor="ls")
    ciz.text((W - 70, 1840), f"@{tema.instagram}", font=f_alt, fill=tema.altbilgi, anchor="rs")
    return [_kaydet(img, cikti / dosya_adi, tema.jpeg_kalite)]
