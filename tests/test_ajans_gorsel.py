"""Ajans/kurum haberleri ve haber fotoğrafı testleri."""

import base64
import io
from datetime import datetime

import pytest
from PIL import Image

from kt import gorsel_kaynak, render
from kt.config import yukle
from kt.kaynaklar import ajans, haber
from kt.tarih import TZ

SIMDI = datetime(2026, 11, 10, 12, 0, tzinfo=TZ)


def _jpeg(gen=1200, yuk=800, renk=(80, 120, 160)) -> bytes:
    b = io.BytesIO()
    Image.new("RGB", (gen, yuk), renk).save(b, "JPEG")
    return b.getvalue()


class Yanit:
    def __init__(self, govde=b"", kod=200, tur="text/html", js=None):
        self.content = govde if isinstance(govde, bytes) else govde.encode("utf-8")
        self.text = self.content.decode("utf-8", "ignore")
        self.status_code, self.ok = kod, kod < 400
        self.headers = {"content-type": tur}
        self._js = js

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._js


class Oturum:
    def __init__(self, sayfalar: dict, post_yaniti=None):
        self.sayfalar, self.post_yaniti, self.istekler = sayfalar, post_yaniti, []

    def get(self, url, **kw):
        self.istekler.append(url)
        return self.sayfalar.get(url, Yanit("", 404))

    def post(self, url, **kw):
        self.istekler.append(url)
        return self.post_yaniti


AA_RSS = """<?xml version="1.0"?><rss><channel>
<item><guid>1</guid><link>https://www.aa.com.tr/tr/yasam/konyada-ornek-haber/1</link>
<title>Konya'da örnek haber</title><description>Selçuklu ilçesinde örnek bir gelişme yaşandı.</description>
<pubDate>Tue, 10 Nov 2026 09:30:00 +0300</pubDate><image>https://cdnuploads.aa.com.tr/ornek1.jpg</image></item>
<item><guid>2</guid><link>https://www.aa.com.tr/tr/dunya/baska/2</link><title>Başka şehirden haber</title>
<description>Ankara'da toplantı.</description><pubDate>Tue, 10 Nov 2026 10:00:00 +0300</pubDate>
<image>https://cdnuploads.aa.com.tr/ornek2.jpg</image></item>
<item><guid>3</guid><link>https://www.aa.com.tr/tr/yasam/eski-konya/3</link><title>Konya'da eski haber</title>
<description>Eski.</description><pubDate>Fri, 06 Nov 2026 10:00:00 +0300</pubDate></item>
</channel></rss>"""

IHA_LISTE = """<html><body>
<a href="/konya-haberleri/kamyona-carpan-otomobil-513623592">Haber 1</a>
<a href="/konya-haberleri/kamyona-carpan-otomobil-513623592">Haber 1 tekrar</a>
<a href="/konya-haberleri/kelebek-bahcesi-tanitildi-513536287">Haber 2</a>
<a href="/ankara-haberleri/baska-513000000">Başka</a></body></html>"""

IHA_MAKALE = """<html><head>
<meta property="og:title" content="Kamyona arkadan çarpan otomobilin sürücüsü yaralandı İhlas Haber Ajansı">
<meta property="og:description" content="Konya'da otomobil kamyona arkadan çarptı.">
<meta property="og:image" content="https://cdn.iha.com.tr/Contents/images/2026/11/10/ornek-0.jpg">
<script type="application/ld+json">{"@type":"NewsArticle","datePublished": "2026-11-10T08:14:46+03:00"}</script>
</head><body><p>Kaza, Konya-Ankara kara yolunun 15. kilometresinde sabah saatlerinde meydana geldi ve trafik bir süre aksadı.</p></body></html>"""

IHA_MAKALE_ESKI = IHA_MAKALE.replace("2026-11-10T08:14:46", "2026-11-05T08:14:46").replace("Kamyona", "Eski")

SELCUKLU_MAKALE = """<html><head>
<meta property="og:title" content="Kelebek Bahçesi Tanıtıldı | Selçuklu">
<meta property="og:description" content="Selçuklu Belediyesi kelebek bahçesini tanıttı…">
</head><body><img src="/logo.png"><div class="rounded-xl"><img class="object-cover"
src="https://cdn0.selcuklu.bel.tr/selcuklu.bel.tr/News/2026/11/10/26c4-cover_image.jpg"></div></body></html>"""


def test_rss_okuma_ve_filtre():
    haberler = ajans.akis_coz(AA_RSS, "AA", "Foto: AA")
    assert len(haberler) == 3
    assert haberler[0].gorsel == "https://cdnuploads.aa.com.tr/ornek1.jpg"
    assert haberler[0].tarih == datetime(2026, 11, 10, 9, 30, tzinfo=TZ)
    o = Oturum({"https://aa/rss": Yanit(AA_RSS, tur="application/xml")})
    uygun = ajans.kaynak_haberleri(o, {"ad": "AA", "tur": "rss", "adresler": ["https://aa/rss"]}, SIMDI)
    assert [h.baslik for h in uygun] == ["Konya'da örnek haber"]          # başka şehir ve eski haber elendi


def test_liste_ve_makale_okuma():
    m = ajans.makale_coz(IHA_MAKALE, "https://www.iha.com.tr/konya-haberleri/x-1")
    assert m["baslik"] == "Kamyona arkadan çarpan otomobilin sürücüsü yaralandı"
    assert m["gorsel"].startswith("https://cdn.iha.com.tr/") and m["tarih"].day == 10
    s = ajans.makale_coz(SELCUKLU_MAKALE, "https://www.selcuklu.bel.tr/p/haber/1/x/")
    assert s["baslik"] == "Kelebek Bahçesi Tanıtıldı"
    assert s["gorsel"].endswith("cover_image.jpg")
    assert s["tarih"].date().isoformat() == "2026-11-10"                    # fotoğraf adresindeki tarihten

    kaynak = {"ad": "İHA", "kredi": "Foto: İHA", "liste": "https://www.iha.com.tr/konya-haberleri",
              "makale_deseni": r"/konya-haberleri/[a-z0-9-]+-\d+", "hepsi_konya": True}
    o = Oturum({
        "https://www.iha.com.tr/konya-haberleri": Yanit(IHA_LISTE),
        "https://www.iha.com.tr/konya-haberleri/kamyona-carpan-otomobil-513623592": Yanit(IHA_MAKALE),
        "https://www.iha.com.tr/konya-haberleri/kelebek-bahcesi-tanitildi-513536287": Yanit(IHA_MAKALE_ESKI),
    })
    hepsi = ajans.getir(o, [kaynak], SIMDI)
    assert len(hepsi) == 1 and hepsi[0].kredi == "Foto: İHA" and hepsi[0].ajans == "İHA"
    assert "/ankara-haberleri/" not in " ".join(o.istekler)
    # daha önce paylaşılan bağlantı aday olmaz
    assert ajans.getir(o, [kaynak], SIMDI, gorulen_linkler={hepsi[0].link}) == []


def _api(json_metin):
    return Yanit(js={"stop_reason": "end_turn", "content": [{"type": "text", "text": json_metin}]})


def test_haber_ajans_adayindan_secilir():
    aday = ajans.AjansHaberi(ajans="İHA", baslik="Kamyona çarpan otomobil", ozet="Konya'da kaza.",
                             link="https://www.iha.com.tr/konya-haberleri/x-1", tarih=SIMDI,
                             gorsel="https://cdn.iha.com.tr/a.jpg", kredi="Foto: İHA")
    j = ('{"atla": false, "ajans_no": 1, "konum": "Selçuklu", "kategori": "KAZA", "baslik": "Kamyona arkadan '
         'çarpan otomobilde 2 yaralı", "etiketler": ["2 yaralı"], "metin": "Kaza sabah saatlerinde oldu.", '
         '"kapanis": "Yaralılara acil şifalar dileriz.", "gorsel_tarifi": "a car crash scene, no people", '
         '"kaynak_adi": "", "kaynak_url": ""}')
    o = Oturum({}, post_yaniti=_api(j))
    h = haber.haber_yaz(o, "anahtar", "claude-sonnet-5-5", "trafik", SIMDI, [], adaylar=[aday])
    assert h["kaynak_url"] == aday.link and h["kaynak_adi"] == "İHA"
    assert h["ajans"] == {"ad": "İHA", "gorsel": "https://cdn.iha.com.tr/a.jpg", "kredi": "Foto: İHA", "resmi": False}
    assert h["gorsel_tarifi"].startswith("a car crash")
    with pytest.raises(haber.HaberHatasi):
        haber.haber_yaz(Oturum({}, post_yaniti=_api(j.replace('"ajans_no": 1', '"ajans_no": 7'))),
                        "k", "m", "genel", SIMDI, [], adaylar=[aday])


def test_foto_sirasi(tmp_path, monkeypatch):
    cfg = yukle()
    o = Oturum({"https://cdn.iha.com.tr/a.jpg": Yanit(_jpeg(), tur="image/jpeg")})
    h = {"baslik": "B", "kategori": "KAZA", "konum": "Selçuklu", "kaynak_url": "https://www.iha.com.tr/x",
         "kaynak_adi": "İHA", "gorsel_tarifi": "a street",
         "ajans": {"ad": "İHA", "gorsel": "https://cdn.iha.com.tr/a.jpg", "kredi": "Foto: İHA", "resmi": False}}
    yol, notu = gorsel_kaynak.foto_bul(h, cfg, o, tmp_path)
    assert notu == "Foto: İHA" and yol.exists()

    # resmi kurum sayfasının fotoğrafı
    assert gorsel_kaynak.resmi_mi("https://www.konya.bel.tr/haber/1") and not gorsel_kaynak.resmi_mi("https://x.com")
    o2 = Oturum({"https://www.konya.bel.tr/haber/1": Yanit(IHA_MAKALE.replace("cdn.iha.com.tr", "www.konya.bel.tr")),
                 "https://www.konya.bel.tr/Contents/images/2026/11/10/ornek-0.jpg": Yanit(_jpeg(), tur="image/jpeg")})
    h2 = dict(h, ajans=None, kaynak_url="https://www.konya.bel.tr/haber/1", kaynak_adi="Konya Büyükşehir Belediyesi")
    yol, notu = gorsel_kaynak.foto_bul(h2, cfg, o2, tmp_path)
    assert notu == "Foto: Konya Büyükşehir Belediyesi"

    # hiçbir fotoğraf yoksa yapay zekâ temsili görsel (Cloudflare)
    monkeypatch.setenv("CF_ACCOUNT_ID", "hesap")
    monkeypatch.setenv("CF_API_TOKEN", "token")
    monkeypatch.setattr(gorsel_kaynak.fotograf, "DIZIN", tmp_path / "bos")
    cf = Yanit(js={"success": True, "result": {"image": base64.b64encode(_jpeg(1024, 1024)).decode()}},
               tur="application/json")
    h3 = dict(h, ajans=None, kaynak_url="https://www.ornekhaber.com/a")
    o3 = Oturum({}, post_yaniti=cf)
    yol, notu = gorsel_kaynak.foto_bul(h3, cfg, o3, tmp_path)
    assert notu == "Temsili görsel" and yol.exists()
    assert "/ai/run/@cf/black-forest-labs/flux-1-schnell" in o3.istekler[-1]

    # yapay zekâ anahtarı da yoksa fotoğrafsız
    monkeypatch.delenv("CF_API_TOKEN")
    assert gorsel_kaynak.foto_bul(h3, cfg, Oturum({}), tmp_path) == (None, "")


def test_haber_foto_notu_basilir(tmp_path):
    tema = render.Tema.configden(yukle())
    foto = tmp_path / "f.jpg"
    foto.write_bytes(_jpeg())
    yol = render.haber(tema, "Kulu", "KAZA", "Başlık", ["Etiket"], "Metin.", "", "10 Kasım 2026", tmp_path,
                       foto=foto, foto_notu="Foto: İHA")[0]
    with Image.open(yol) as im:
        assert im.size == (1080, 1920)
