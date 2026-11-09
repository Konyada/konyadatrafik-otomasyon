"""Yapay zekâ ile haber story'si: Claude API.

Önce abone olunan ajansların (İHA, DHA, AA) ve resmi kurumların son Konya haberleri modele
aday olarak verilir; uygun olan seçilir ve story metnine dönüştürülür. Listede uygun haber yoksa
model web araması yapar; bu durumda yalnızca arama sonuçlarında gerçekten geçen bir kaynağı
gösterebilir, aksi halde haber paylaşılmaz.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from urllib.parse import urlparse

from ..tarih import tarih_yazi, tr_buyuk

API_URL = "https://api.anthropic.com/v1/messages"
API_SURUM = "2023-06-01"

KATEGORILER = ["SON DAKİKA", "TRAFİK", "KAZA", "SORUŞTURMA", "ASAYİŞ", "YANGIN", "BÜYÜKŞEHİR",
               "BELEDİYE", "GÜNDEM", "KONYASPOR", "EKONOMİ", "EĞİTİM", "SAĞLIK", "HAVA DURUMU"]

TURLER = {
    "genel": ("Konya'da son 24 saatte yaşanan ve şehir halkını ilgilendiren en önemli yerel haber "
              "(ulaşım, yol çalışması, hava durumu uyarısı, eğitim, sağlık, şehir gündemi vb.)."),
    "trafik": ("Konya'da son 24 saatteki trafik, yol durumu, yol çalışması, kapanan yollar, kaza, "
               "toplu taşıma veya ulaşımla ilgili en önemli haber."),
    "buyuksehir": ("Konya Büyükşehir Belediyesi'nin son günlerdeki bir kararı, zammı, ihalesi, projesi, "
                   "hizmet aksaklığı veya açıklaması."),
    "konyaspor": ("Konyaspor ile ilgili son 24 saatteki en güncel haber (maç, transfer, sakatlık, açıklama). "
                  "Konyaspor haberi yoksa Konya'dan genel bir yerel haber seç."),
    "selcuklu": ("Selçuklu Belediyesi'nin son günlerdeki bir haberi, hizmeti, projesi ya da etkinliği. "
                 "Uygun Selçuklu haberi yoksa Konya'dan genel bir yerel haber seç."),
}

VARSAYILAN_EDITORYAL = """\
- Konya ve Konyaspor haberlerinde sıcak, yerel ve sahiplenici bir dil kullan ("şehrimiz", "Konyaspor'umuz").
- Büyükşehir Belediyesi ve siyasi kararlarla ilgili haberlerde vatandaşın gözünden, sorgulayıcı ve
  eleştirel bir dil kullan; zamları, aksaklıkları ve kararların vatandaşa etkisini öne çıkar.
  Eleştirini her zaman kaynakta geçen somut bilgilere dayandır.
- Trafik ve ulaşım haberlerinde pratik bilgi ver: hangi yol, ne zamana kadar, varsa alternatif güzergâh.
"""

KURALLAR = """\
1. Yalnızca aday listesindeki ya da web aramasında gerçekten bulduğun, son 24 saat içinde yayımlanmış
   haberleri kullan (Büyükşehir ve belediye türlerinde son 3 gün olabilir). Tarihi belirsizse kullanma.
2. Kaynakta olmayan hiçbir bilgi, rakam, alıntı veya iddia ekleme. Emin olmadığın şeyi yazma.
3. Eleştiri yapabilirsin ama hakaret, aşağılama, iftira ya da kesinleşmemiş suçlama yok;
   kişileri değil kararları ve uygulamaları eleştir.
4. Kaza, suç ve olaylarda ölen, yaralanan, şüpheli veya mağdur kişilerin adını yazma; çocukların
   kimliğini asla belirtme; kanlı veya korkutucu ayrıntı verme.
5. Kaynaktan cümle kopyalama; kendi cümlelerinle, sade ve anlaşılır Türkçe yaz.
6. Haber doğrudan Konya ile ilgili olmalı.
7. Daha önce paylaşılan haberleri ve aynı konunun tekrarını seçme.
8. Uygun haber bulamazsan atla.
"""

CIKTI_BICIMI = """\
Yanıtını YALNIZCA şu JSON biçiminde ver, başka hiçbir şey yazma:
{"atla": false, "ajans_no": null, "konum": "...", "kategori": "...", "baslik": "...", "etiketler": ["...", "..."],
 "metin": "...", "kapanis": "...", "gorsel_tarifi": "...", "kaynak_adi": "...", "kaynak_url": "..."}
- ajans_no: aday listesinden seçtiysen haberin numarası (ör. 3), web aramasından bulduysan null
- konum: haberin geçtiği ilçe ya da semt (ör. KULU, SELÇUKLU, MERAM, KARATAY); belli değilse KONYA
- kategori: şunlardan biri: """ + ", ".join(KATEGORILER) + """
- baslik: en fazla 80 karakter, dikkat çekici ama abartısız
- etiketler: haberin 0-2 kısa bilgi notu, her biri en fazla 24 karakter
  (ör. "Yol 18.00'e kadar kapalı", "Otopsi bekleniyor"); yoksa boş liste
- metin: 3-5 cümle, 300-520 karakter; ne, nerede, ne zaman, sonuç ne
- kapanis: isteğe bağlı tek kısa cümle. Vefat haberinde "Allah rahmet eylesin. Mekânı cennet olsun.",
  yaralanmalı olayda "Yaralılara acil şifalar dileriz.", trafik uyarısında kısa bir dikkat çağrısı;
  uygun değilse boş bırak
- gorsel_tarifi: haberin fotoğrafı yoksa kullanılacak temsili görselin İngilizce tarifi (en fazla 300
  karakter): gerçekçi bir haber fotoğrafı sahnesi; tanınabilir yüz, yazı, logo, kan, yaralı ve çocuk olmasın
  (ör. "a white ambulance on a wet city street at dusk in Konya, Turkey, photojournalism")
- kaynak_adi ve kaynak_url: web aramasından bulduysan haberin sitesinin adı ve tam adresi
  (aday listesinden seçtiysen boş bırakabilirsin)
Uygun haber yoksa: {"atla": true, "neden": "..."}
"""


class HaberHatasi(Exception):
    pass


def _alan(url: str) -> str:
    try:
        return urlparse(url).netloc.lower().removeprefix("www.")
    except ValueError:
        return ""


def _json_bul(metin: str) -> dict:
    metin = metin.strip()
    metin = re.sub(r"^```(?:json)?\s*|\s*```$", "", metin)
    bas, son = metin.find("{"), metin.rfind("}")
    if bas == -1 or son == -1:
        raise HaberHatasi(f"Model JSON döndürmedi: {metin[:200]!r}")
    return json.loads(metin[bas:son + 1])


def _kisalt(metin: str, sinir: int) -> str:
    metin = re.sub(r"\s+", " ", metin or "").strip()
    if len(metin) <= sinir:
        return metin
    kes = metin[:sinir].rsplit(" ", 1)[0]
    return kes.rstrip(" ,;:-–") + "…"


def _katla(s: str) -> str:
    s = tr_buyuk(s.strip())
    for a, b in zip("İŞĞÜÖÇ", "ISGUOC"):
        s = s.replace(a, b)
    return re.sub(r"\s+", " ", s)


def kategori_esle(kategori: str) -> str:
    k = _katla(kategori)
    for aday in KATEGORILER:
        if _katla(aday) == k:
            return aday
    return "GÜNDEM"


def _benzer(a: str, b: str) -> float:
    ka = set(re.findall(r"\w{3,}", a.lower()))
    kb = set(re.findall(r"\w{3,}", b.lower()))
    if not ka or not kb:
        return 0.0
    return len(ka & kb) / len(ka | kb)


def istem_olustur(tur: str, simdi: datetime, gecmis: list[dict], editoryal: str | None,
                  adaylar: list | None = None) -> tuple[str, str]:
    sistem = (
        "Sen 'Konya'da Trafik' adlı yerel haber Instagram sayfasının haber editörüsün. "
        "Görevin: Konya'dan tek bir güncel haber seçmek ve onu tek sayfalık bir Instagram story "
        "metnine dönüştürmek.\n\n"
        "EDİTORYAL ÇİZGİ:\n" + (editoryal or VARSAYILAN_EDITORYAL).strip() + "\n\n"
        "DEĞİŞMEZ KURALLAR:\n" + KURALLAR + "\n" + CIKTI_BICIMI
    )
    gecmis_yazi = "\n".join(f"- {h['tarih']}: {h['baslik']}" for h in gecmis[-40:]) or "- (henüz yok)"
    aday_yazi = ""
    if adaylar:
        satirlar = []
        for i, a in enumerate(adaylar, 1):
            zaman = f"{a.tarih:%d.%m %H:%M}" if a.tarih else "tarih yok"
            icerik = (a.metin or a.ozet or "")[:600]
            satirlar.append(f"[{i}] ({a.ajans}, {zaman}) {a.baslik}\n    {icerik}")
        aday_yazi = (
            "ABONE OLDUĞUMUZ AJANSLARIN VE RESMİ KURUMLARIN SON KONYA HABERLERİ (önce bunlardan seç; "
            "uygun olanı seçersen web araması yapma ve ajans_no'ya numarasını yaz):\n"
            + "\n".join(satirlar) + "\n\nListede bu türe uygun haber yoksa web araması yap.\n\n"
        )
    kullanici = (
        f"Şu an {tarih_yazi(simdi.date())}, saat {simdi:%H:%M} (İstanbul).\n"
        f"Aranan haber türü: {TURLER.get(tur, TURLER['genel'])}\n\n"
        f"{aday_yazi}"
        f"Daha önce paylaşılan haberler:\n{gecmis_yazi}\n\n"
        "Yalnızca JSON'u ver."
    )
    return sistem, kullanici


def haber_yaz(oturum, api_anahtari: str, model: str, tur: str, simdi: datetime, gecmis: list[dict],
              editoryal: str | None = None, en_fazla_arama: int = 3, adaylar: list | None = None) -> dict | None:
    """Haber sözlüğü döndürür; uygun haber yoksa None."""
    if not api_anahtari:
        raise HaberHatasi("ANTHROPIC_API_KEY tanımlı değil.")
    adaylar = adaylar or []
    sistem, kullanici = istem_olustur(tur, simdi, gecmis, editoryal, adaylar)
    mesajlar = [{"role": "user", "content": kullanici}]
    araclar = [{
        "type": "web_search_20250305", "name": "web_search", "max_uses": en_fazla_arama,
        "user_location": {"type": "approximate", "city": "Konya", "region": "Konya",
                          "country": "TR", "timezone": "Europe/Istanbul"},
    }]
    gorulen_urller: set[str] = set()
    yanit = {}
    for _ in range(4):
        r = oturum.post(API_URL, timeout=240, headers={
            "x-api-key": api_anahtari, "anthropic-version": API_SURUM, "content-type": "application/json",
        }, json={"model": model, "max_tokens": 1800, "system": sistem, "tools": araclar, "messages": mesajlar})
        if r.status_code >= 400:
            raise HaberHatasi(f"Claude API hatası {r.status_code}: {r.text[:300]}")
        yanit = r.json()
        for blok in yanit.get("content", []):
            if blok.get("type") == "web_search_tool_result" and isinstance(blok.get("content"), list):
                for sonuc in blok["content"]:
                    if sonuc.get("url"):
                        gorulen_urller.add(sonuc["url"])
            for alinti in blok.get("citations", []) or []:
                if alinti.get("url"):
                    gorulen_urller.add(alinti["url"])
        if yanit.get("stop_reason") == "pause_turn":
            mesajlar.append({"role": "assistant", "content": yanit["content"]})
            continue
        break

    metin = "".join(b.get("text", "") for b in yanit.get("content", []) if b.get("type") == "text")
    veri = _json_bul(metin)
    if veri.get("atla"):
        return None
    for alan in ("kategori", "baslik", "metin"):
        if not str(veri.get(alan, "")).strip():
            raise HaberHatasi(f"Model çıktısında '{alan}' eksik.")

    secilen = None
    try:
        no = int(veri.get("ajans_no")) if veri.get("ajans_no") not in (None, "", "null") else None
    except (TypeError, ValueError):
        no = None
    if no is not None:
        if not 1 <= no <= len(adaylar):
            raise HaberHatasi(f"Model geçersiz bir aday numarası verdi: {no}")
        secilen = adaylar[no - 1]
        url, kaynak_adi = secilen.link, secilen.ajans
    else:
        url = str(veri.get("kaynak_url", "")).strip()
        kaynak_adi = str(veri.get("kaynak_adi", "")).strip()
        if not url or not kaynak_adi:
            raise HaberHatasi("Model web haberinin kaynağını vermedi.")
        alanlar = {_alan(u) for u in gorulen_urller}
        if url not in gorulen_urller and _alan(url) not in alanlar:
            raise HaberHatasi(f"Kaynak adresi arama sonuçlarında yok, haber paylaşılmadı: {url}")

    for h in gecmis:
        if h.get("url") == url or _benzer(h.get("baslik", ""), veri["baslik"]) >= 0.6:
            return None

    etiketler = veri.get("etiketler") or []
    if isinstance(etiketler, str):
        etiketler = [etiketler]
    return {
        "konum": _kisalt(str(veri.get("konum") or "KONYA"), 24),
        "kategori": kategori_esle(str(veri["kategori"])),
        "baslik": _kisalt(veri["baslik"], 100),
        "etiketler": [_kisalt(str(e), 28) for e in etiketler if str(e).strip()][:2],
        "metin": _kisalt(veri["metin"], 560),
        "kapanis": _kisalt(str(veri.get("kapanis") or ""), 90),
        "gorsel_tarifi": _kisalt(str(veri.get("gorsel_tarifi") or ""), 400),
        "kaynak_adi": _kisalt(kaynak_adi, 60),
        "kaynak_url": url,
        "ajans": ({"ad": secilen.ajans, "gorsel": secilen.gorsel, "kredi": secilen.kredi, "resmi": secilen.resmi}
                  if secilen else None),
    }
