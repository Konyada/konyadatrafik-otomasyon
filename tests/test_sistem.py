"""Temel testler: python -m pytest -q"""

from datetime import date, datetime
from pathlib import Path

import pytest
from PIL import Image

from kt import render, tarih
from kt.__main__ import slot_kimligi, zamani_gelenler
from kt.config import yukle
from kt.durum import Durum
from kt.kaynaklar import eczane, haber, soz, vefat

FX = Path(__file__).parent / "fixtures"


# ------------------------------------------------------------------ tarih
def test_turkce_buyuk_kucuk_baslik():
    assert tarih.tr_buyuk("büyükşehir") == "BÜYÜKŞEHİR"
    assert tarih.tr_baslik("SARI CAMİİ") == "Sarı Camii"
    assert tarih.tr_baslik("İKİNDİ NAMAZI") == "İkindi Namazı"


def test_yilsiz_tarih_yil_donumu():
    assert tarih.gun_ay_coz(31, "Aralık", date(2027, 1, 1)) == date(2026, 12, 31)
    assert tarih.gun_ay_coz(1, "Ocak", date(2026, 12, 31)) == date(2027, 1, 1)
    assert tarih.gun_ay_coz(10, "Kasım", date(2026, 11, 10)) == date(2026, 11, 10)


# ------------------------------------------------------------------ eczane
def test_eczane_resmi_site():
    liste = eczane.resmi_coz((FX / "eczane_resmi.html").read_text(encoding="utf-8"), date(2026, 11, 10))
    assert liste.baslangic == date(2026, 11, 10)
    assert liste.pencere == "10 Kasım 08:30 – 11 Kasım 08:30"
    assert [e.ad for e in liste.eczaneler] == ["Örnek Eczanesi", "Deneme Eczanesi", "Yeşil Eczanesi"]
    ilk = liste.eczaneler[0]
    assert ilk.kapsam == "Selçuklu"
    assert ilk.adres.startswith("Ferhuniye Mh.") and ilk.adres.endswith("Selçuklu")
    assert ilk.tarif == "Örnek Hastanesi Karşısı"
    assert liste.eczaneler[1].tel == "0332 000 00 02"      # +90 biçimi düzeltildi
    assert liste.eczaneler[1].tarif == ""
    # story satırı: tarif yoksa ilçe eki atılmış adres
    assert liste.eczaneler[1].story() == {"ad": "Deneme Eczanesi", "tel": "0332 000 00 02",
                                          "tarif": "Hocacihan Mh. Deneme Sk. No:2"}
    gruplar = eczane.ilceye_gore(liste.eczaneler)
    assert [g for g, _ in gruplar] == ["Selçuklu", "Meram", "Karatay"]


def test_eczane_resmi_site_ilceler_dahil():
    html = (FX / "eczane_resmi.html").read_text(encoding="utf-8")
    liste = eczane.resmi_coz(html, date(2026, 11, 10), ("merkez", "ilceler"))
    assert len(liste.eczaneler) == 4 and liste.eczaneler[-1].ilce == "Akşehir"


class _EczaneOturumu:
    """GET: sayfa HTML'i (veya yedek), POST: veri.php yanıtı. Hata vermesi istenen adresler için istisna atar."""

    def __init__(self, sayfa, veri=None, yedek=None, veri_hatasi=None):
        self.sayfa, self.veri, self.yedek, self.veri_hatasi = sayfa, veri, yedek, veri_hatasi
        self.postlar = []

    class _Yanit:
        def __init__(self, metin="", veri=None, kod=200):
            self.text, self._veri, self.status_code = metin, veri, kod

        def raise_for_status(self):
            if self.status_code >= 400:
                raise RuntimeError(f"HTTP {self.status_code}")

        def json(self):
            return self._veri

    def get(self, url, **kw):
        if url == eczane.RESMI_URL:
            return self._Yanit(self.sayfa)
        if url == eczane.YEDEK_URL and self.yedek is not None:
            return self._Yanit(self.yedek)
        return self._Yanit(kod=503)

    def post(self, url, **kw):
        self.postlar.append((url, kw))
        if self.veri_hatasi:
            return self._Yanit(kod=self.veri_hatasi)
        return self._Yanit(veri=self.veri)


def _canli():
    import json
    return ((FX / "eczane_resmi_canli.html").read_text(encoding="utf-8"),
            json.loads((FX / "eczane_veri.json").read_text(encoding="utf-8")))


def test_eczane_canli_yapi_veri_php():
    html, veri = _canli()
    o = _EczaneOturumu(html, veri)
    liste = eczane.getir(o, date(2026, 11, 10), log=lambda *_: None)
    url, kw = o.postlar[0]
    assert url == "https://www.konyanobetcieczaneleri.com/nobet/onyuz/veri.php"
    assert kw["data"]["j"] == "TEST-ANAHTAR" and kw["data"]["cf"] == "" and kw["headers"]["Accept"] == "application/json"
    assert liste.kaynak == eczane.RESMI_AD and liste.baslangic == date(2026, 11, 10)
    assert [e.tel for e in liste.eczaneler] == ["0332 000 00 01", "0332 000 00 02", "0332 000 00 03", "0332 000 00 04"]
    yesil = liste.eczaneler[2]
    assert yesil.kapsam == "Karatay - Meram" and yesil.ilce == "Karatay" and yesil.tarif == "Ticaret Borsası Yanı"
    # gruplar nöbet bölgesine göre değil eczanenin bulunduğu ilçeye göre: 3 başlık
    gruplar = eczane.ilceye_gore(liste.eczaneler)
    assert [(g, [e["ad"] for e in es]) for g, es in gruplar] == [
        ("Selçuklu", ["Örnek Eczanesi", "Deneme Eczanesi"]), ("Meram", ["Mavi Eczanesi"]), ("Karatay", ["Yeşil Eczanesi"])]
    assert gruplar[0][1][1]["tarif"] == "Hocacihan Mh. Deneme Sk. No: 2"        # tarif yoksa adres


def test_eczane_ayrinti_alinamazsa_yedek_sonra_telefonsuz():
    html, _ = _canli()
    yedek = (FX / "eczane_posta.html").read_text(encoding="utf-8")
    liste = eczane.getir(_EczaneOturumu(html, veri_hatasi=403, yedek=yedek), date(2026, 11, 10),
                         yedek_ilceler=["Selçuklu", "Meram", "Karatay"], log=lambda *_: None)
    assert liste.kaynak == eczane.YEDEK_AD and liste.eczaneler[0].tel == "0332 000 00 01"
    liste = eczane.getir(_EczaneOturumu(html, veri_hatasi=403), date(2026, 11, 10), log=lambda *_: None)
    assert liste.kaynak == eczane.RESMI_AD and len(liste.eczaneler) == 4 and not any(e.tel for e in liste.eczaneler)
    assert liste.eczaneler[0].adres == ""                                        # "Yükleniyor…" alınmadı


def test_eczane_yedek_kaynak():
    liste = eczane.yedek_coz((FX / "eczane_posta.html").read_text(encoding="utf-8"), ["Selçuklu", "Meram", "Karatay"])
    assert liste.baslangic == date(2026, 11, 10)
    assert len(liste.eczaneler) == 1
    e = liste.eczaneler[0]
    assert e.ad == "Örnek Eczanesi" and e.adres == "Ferhuniye Mh. Örnek Cd. No: 1" and e.tel == "0332 000 00 01"


# ------------------------------------------------------------------ vefat
def test_vefat_tablosu():
    kayitlar = vefat.tablo_coz((FX / "vefat.html").read_text(encoding="utf-8"))
    assert len(kayitlar) == 4
    bugun = vefat.gune_gore(kayitlar, date(2026, 11, 10))
    assert len(bugun) == 3
    s = [k.story() for k in bugun]
    assert s[0] == {"ad": "Örnek Kişi Bir", "defin": "Musalla", "baba": "Ahmet",
                    "cenaze": "Sarı Camii – Öğle Namazı"}
    assert s[1]["cenaze"] == "Mezarlıkta – Saat 17:00"
    assert s[1]["defin"] == "Seyit Şahin (Kurtuluş)"
    assert s[2]["defin"] == "Üçler"
    assert s[2]["cenaze"] == "Hacı Veyis Camii (Üçler Mezarlığı Yanı) – İkindi Namazı"
    assert len({k.anahtar() for k in kayitlar}) == 4


# ------------------------------------------------------------------ zamanlama
def test_zamani_gelen_gorevler(tmp_path):
    d = Durum(tmp_path / "durum.json")
    plan = [{"saat": "08:00", "gorev": "soz"}, {"saat": "08:45", "gorev": "eczane"},
            {"saat": "13:30", "gorev": "haber", "tur": "buyuksehir"}]
    simdi = datetime(2026, 11, 10, 9, 7, tzinfo=tarih.TZ)
    assert [slot_kimligi(s) for s in zamani_gelenler(plan, simdi, d, 150)] == ["08:00-soz", "08:45-eczane"]
    d.slot_kaydet(simdi.date(), "08:00-soz", durum="paylasildi")
    d.slot_kaydet(simdi.date(), "08:45-eczane", durum="tekrar")
    assert [slot_kimligi(s) for s in zamani_gelenler(plan, simdi, d, 150)] == ["08:45-eczane"]
    gec = datetime(2026, 11, 10, 11, 30, tzinfo=tarih.TZ)       # eczane toleransı geçti
    assert zamani_gelenler(plan, gec, d, 150) == []
    assert slot_kimligi(plan[2]) == "13:30-haber-buyuksehir"


# ------------------------------------------------------------------ haber
class _SahteYanit:
    def __init__(self, veri, kod=200):
        self._veri, self.status_code, self.text = veri, kod, str(veri)

    def json(self):
        return self._veri


class _SahteOturum:
    def __init__(self, yanitlar):
        self.yanitlar, self.cagrilar = list(yanitlar), []

    def post(self, url, **kw):
        self.cagrilar.append(kw)
        return self.yanitlar.pop(0)


def _api_yaniti(json_metin, url="https://www.ornekhaber.com/konya/yol-calismasi-123"):
    return _SahteYanit({"stop_reason": "end_turn", "content": [
        {"type": "server_tool_use", "id": "srvtoolu_1", "name": "web_search", "input": {"query": "konya"}},
        {"type": "web_search_tool_result", "tool_use_id": "srvtoolu_1",
         "content": [{"type": "web_search_result", "url": url, "title": "Yol çalışması"}]},
        {"type": "text", "text": json_metin},
    ]})


def test_haber_dogru_cikti():
    j = ('{"atla": false, "konum": "Selçuklu", "kategori": "trafik", '
         '"baslik": "Mevlana Caddesi\'nde tek şerit kapalı", "etiketler": ["18.00\'e kadar", "Alternatif güzergâh var"], '
         '"metin": "Çalışma nedeniyle cadde bugün 18.00\'e kadar tek şeritten akacak.", "kapanis": "", '
         '"kaynak_adi": "Örnek Haber", "kaynak_url": "https://www.ornekhaber.com/konya/yol-calismasi-123"}')
    o = _SahteOturum([_api_yaniti(j)])
    h = haber.haber_yaz(o, "anahtar", "claude-sonnet-5-5", "trafik", datetime(2026, 11, 10, 11, 30), [])
    assert h["kategori"] == "TRAFİK" and h["baslik"].startswith("Mevlana")
    assert h["konum"] == "Selçuklu" and h["etiketler"] == ["18.00'e kadar", "Alternatif güzergâh var"]
    assert h["kapanis"] == ""
    istek = o.cagrilar[0]["json"]
    assert istek["tools"][0]["type"] == "web_search_20250305"
    assert istek["tools"][0]["user_location"]["city"] == "Konya"


def test_haber_uydurma_kaynak_reddedilir():
    j = ('{"atla": false, "kategori": "GÜNDEM", "baslik": "Başlık", "metin": "Metin.", '
         '"kaynak_adi": "X", "kaynak_url": "https://uydurma-site.com/haber"}')
    with pytest.raises(haber.HaberHatasi):
        haber.haber_yaz(_SahteOturum([_api_yaniti(j)]), "k", "m", "genel", datetime(2026, 11, 10, 9, 30), [])


def test_haber_atla_ve_tekrar():
    o = _SahteOturum([_api_yaniti('{"atla": true, "neden": "yok"}')])
    assert haber.haber_yaz(o, "k", "m", "genel", datetime(2026, 11, 10, 9, 30), []) is None
    j = ('{"atla": false, "kategori": "GÜNDEM", "baslik": "Mevlana Caddesi tek şerit kapalı", "metin": "M.", '
         '"kaynak_adi": "X", "kaynak_url": "https://www.ornekhaber.com/konya/yol-calismasi-123"}')
    gecmis = [{"tarih": "2026-11-10", "baslik": "Mevlana Caddesi tek şerit kapalı", "url": "https://baska.com/a"}]
    assert haber.haber_yaz(_SahteOturum([_api_yaniti(j)]), "k", "m", "genel",
                           datetime(2026, 11, 10, 15, 30), gecmis) is None


def test_kategori_esleme():
    assert haber.kategori_esle("Büyükşehir") == "BÜYÜKŞEHİR"
    assert haber.kategori_esle("BUYUKSEHIR") == "BÜYÜKŞEHİR"
    assert haber.kategori_esle("bilinmeyen") == "GÜNDEM"


# ------------------------------------------------------------------ tasarım
def test_sozler_listesi():
    tum = soz.tum_sozler()
    assert len(tum) >= 100 and all(s["soz"] and s["kaynak"] for s in tum)
    assert soz.gunun_sozu(date(2026, 11, 10)) in tum


def test_fotograf_secimi(tmp_path):
    from kt import fotograf
    assert fotograf.klasor_adi("HAVA DURUMU") == "hava-durumu"
    assert fotograf.klasor_adi("BÜYÜKŞEHİR") == "buyuksehir"
    assert fotograf.sec("TRAFİK", "KULU", "x", dizin=tmp_path) is None
    (tmp_path / "trafik").mkdir(); (tmp_path / "trafik" / "a.jpg").write_bytes(b"x")
    (tmp_path / "kulu").mkdir(); (tmp_path / "kulu" / "k.jpg").write_bytes(b"x")
    assert fotograf.sec("TRAFİK", "KULU", "x", dizin=tmp_path).name == "k.jpg"      # önce ilçe
    assert fotograf.sec("TRAFİK", "MERAM", "x", dizin=tmp_path).name == "a.jpg"     # sonra kategori


def test_gorseller_instagram_uygun(tmp_path):
    tema = render.Tema.configden(yukle())
    yollar = render.gunun_sozu(tema, "Damlaya damlaya göl olur.", "Atasözü", "10 Kasım 2026 Salı", tmp_path)
    kayitlar = [k.story() for k in vefat.tablo_coz((FX / "vefat.html").read_text(encoding="utf-8"))] * 6
    v = render.vefat_edenler(tema, kayitlar, "10 Kasım 2026 Salı", tmp_path)
    assert len(v) == 1                                     # 24 kayıt -> yine tek story
    liste = eczane.resmi_coz((FX / "eczane_resmi.html").read_text(encoding="utf-8"), date(2026, 11, 10))
    cok = [("Selçuklu", [liste.eczaneler[0].story()] * 14), ("Meram", [liste.eczaneler[1].story()] * 5)]
    e = render.nobetci_eczaneler(tema, cok, "10 Kasım 2026 Salı", tmp_path)
    assert len(e) == 1                                     # 19 eczane -> yine tek story
    foto = tmp_path / "foto.jpg"
    Image.new("RGB", (1600, 900), (90, 120, 160)).save(foto)
    h1 = render.haber(tema, "Kulu", "SORUŞTURMA", "Başlık " * 30, ["Bir", "İki"], "Uzun metin " * 120,
                      "Allah rahmet eylesin.", "10 Kasım 2026", tmp_path, foto=foto, dosya_adi="h1.jpg")
    h2 = render.haber(tema, "", "GÜNDEM", "Kısa başlık", [], "Kısa metin.", "", "10 Kasım 2026", tmp_path,
                      dosya_adi="h2.jpg")
    yollar += v + e + h1 + h2
    assert len(yollar) == 5                                # söz + vefat + eczane + 2 haber
    for y in yollar:
        with Image.open(y) as im:
            assert im.size == (1080, 1920) and im.format == "JPEG" and im.mode == "RGB"
        assert y.stat().st_size < 8 * 1024 * 1024


def test_nobet_penceresi():
    from kt.gorevler import nobet_gecerli_mi
    tz = tarih.TZ
    dun, bugun = date(2026, 11, 9), date(2026, 11, 10)
    assert nobet_gecerli_mi(dun, datetime(2026, 11, 10, 3, 15, tzinfo=tz))        # gece: dünkü nöbet geçerli
    assert not nobet_gecerli_mi(dun, datetime(2026, 11, 10, 8, 45, tzinfo=tz))    # 08:30'dan sonra eski liste
    assert nobet_gecerli_mi(bugun, datetime(2026, 11, 10, 8, 45, tzinfo=tz))
    assert not nobet_gecerli_mi(bugun, datetime(2026, 11, 10, 8, 0, tzinfo=tz))   # henüz başlamadı


# ------------------------------------------------------------------ tek sayfa düzenleri
def test_vefat_her_zaman_tek_sayfa(tmp_path):
    tema = render.Tema.configden(yukle())
    onceki = None
    for adet in (1, 15, 16, 20, 21, 30, 31, 50):
        kompakt, sutun, satir, kapasite = render.vefat_duzeni(adet)
        assert adet <= kapasite, adet                      # 50 kişiye kadar hepsi sığar
        boyut = (sutun, -satir, kompakt)
        assert onceki is None or boyut >= onceki           # kalabalıklaştıkça düzen küçülür, büyümez
        onceki = boyut
    assert render.vefat_duzeni(15)[:3] == (False, 1, 64)   # 15 kişiye kadar şablondaki boyut
    assert render.vefat_duzeni(25)[1] == 2                 # kalabalıkta iki sütun
    kayitlar = [{"ad": f"Kişi {i}", "defin": "Musalla"} for i in range(80)]
    yollar = render.vefat_edenler(tema, kayitlar, "10 Kasım 2026 Salı", tmp_path)
    assert len(yollar) == 1                                # aşırı kalabalıkta da tek story (+N kişi daha)


def test_eczane_her_zaman_tek_sayfa(tmp_path):
    tema = render.Tema.configden(yukle())
    e = {"ad": "Örnek Eczanesi", "tel": "0332 000 00 01", "tarif": "Örnek Hastanesi Karşısı"}
    d, sutunlar, tasan = render.eczane_duzeni([("Selçuklu", [e] * 6), ("Meram", [e] * 2), ("Karatay", [e] * 3)])
    assert (d.kompakt, d.sutun, d.tip, d.satir, tasan) == (False, 1, "tarifli", 75, 0)   # olağan gün: şablon boyutu
    for dagilim in ([7, 4, 4], [9, 6, 5], [12, 9, 9], [3] * 12):
        gruplar = [(f"İlçe {i}", [e] * n) for i, n in enumerate(dagilim)]
        d, sutunlar, tasan = render.eczane_duzeni(gruplar)
        assert tasan == 0, dagilim
        yerlesen = sum(1 for s in sutunlar for t, _ in s if t == "eczane")
        assert yerlesen == sum(dagilim)
        assert len(render.nobetci_eczaneler(tema, gruplar, "10 Kasım", tmp_path)) == 1
    d, sutunlar, tasan = render.eczane_duzeni([("Konya", [e] * 200)])
    assert tasan > 0 and len(render.nobetci_eczaneler(tema, [("Konya", [e] * 200)], "10 Kasım", tmp_path)) == 1
