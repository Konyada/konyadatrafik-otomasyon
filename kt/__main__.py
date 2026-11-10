"""Komut satırı.

  python -m kt calistir     # zamanı gelen görevleri çalıştırır (GitHub bunu 15 dk'da bir çağırır)
  python -m kt onizleme     # internete çıkmadan örnek story görselleri üretir (cikti/onizleme)
  python -m kt kontrol      # token, Instagram hesabı ve veri kaynaklarını kontrol eder

Ortam değişkenleri:
  IG_ACCESS_TOKEN    Meta sistem kullanıcısı token'ı (GitHub Secret)
  ANTHROPIC_API_KEY  Claude API anahtarı (GitHub Secret)
  EDITORIAL_GUIDE    (isteğe bağlı) haber üslubu talimatı
  KT_GOREV           elle çalıştırılacak görev: soz | eczane | vefat | haber[:tur]
  KT_DENEME          1/true ise Instagram'a paylaşmaz, sadece görselleri üretip yükler
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import traceback
from datetime import timedelta
from pathlib import Path

from . import render, tarih
from .config import KOK, yukle
from .durum import Durum
from .gorevler import GOREVLER, Baglam, Sonuc
from .kaynaklar import oturum as yeni_oturum

DOGRU = {"1", "true", "yes", "evet", "on"}
KALICI = {"paylasildi", "atlandi", "hata_kalici"}
EN_FAZLA_HATA = 3


def slot_kimligi(slot: dict) -> str:
    k = f"{slot['saat']}-{slot['gorev']}"
    return f"{k}-{slot['tur']}" if slot.get("tur") else k


def zamani_gelenler(zamanlama: list[dict], simdi, durum: Durum, tolerans_dk: int) -> list[dict]:
    gelen = []
    for slot in sorted(zamanlama, key=lambda s: s["saat"]):
        ss, dd = (int(x) for x in slot["saat"].split(":"))
        vakit = simdi.replace(hour=ss, minute=dd, second=0, microsecond=0)
        if simdi < vakit or simdi - vakit > timedelta(minutes=tolerans_dk):
            continue
        if durum.slot(simdi.date(), slot_kimligi(slot)).get("durum") in KALICI:
            continue
        gelen.append(slot)
    return gelen


class Yayinci:
    """Görselleri herkese açık adrese yükler, sırayla Instagram'a ve Facebook sayfasına story olarak paylaşır."""

    def __init__(self, cfg: dict, durum: Durum, deneme: bool, log=print):
        self.deneme, self.log, self.durum = deneme, log, durum
        self.depo = None
        if os.environ.get("GITHUB_ACTIONS") == "true":
            from .gorsel_depo import GorselDepo
            self.depo = GorselDepo(KOK, log=log)
        self.ig = self.fb = None
        if not deneme:
            from .instagram import FacebookSayfa, Instagram
            ayar = cfg.get("instagram", {})
            token = os.environ.get("IG_ACCESS_TOKEN", "")
            sayfa_id = str(cfg.get("sayfa", {}).get("facebook_sayfa_id", ""))
            surum = ayar.get("graph_api_surum", "v23.0")
            self.ig = Instagram(token, surum=surum, sayfa_id=sayfa_id, log=log,
                                hesap_id=ayar.get("instagram_hesap_id") or durum.ayar("instagram_hesap_id"))
            if (cfg.get("facebook") or {}).get("story_paylas", True):
                self.fb = FacebookSayfa(token, sayfa_id, surum=surum, log=log)

    def __call__(self, yollar: list[Path], etiket: str) -> tuple[list[str], list[str]]:
        simdi = tarih.simdi()
        klasor = f"{simdi:%Y/%m/%d}/{simdi:%H%M%S}-{etiket}"
        if self.depo:
            adresler = self.depo.yukle(yollar, klasor)
        elif self.deneme:
            adresler = [str(p) for p in yollar]
        else:
            raise RuntimeError("Görselleri barındıracak bir yer yok (sistem GitHub Actions dışında çalışıyor).")
        if self.deneme:
            return ["DENEME"] * len(adresler), adresler
        medya = []
        for adres in adresler:
            try:
                medya.append("ig:" + self.ig.story_paylas(adres))
            except Exception as ilk_hata:  # noqa: BLE001
                if self.depo and "raw.githubusercontent.com" in adres:
                    self.log(f"  raw adresi reddedildi ({ilk_hata}); jsDelivr adresiyle yeniden deneniyor.")
                    adres = self.depo.yedek_adres(adres)
                    medya.append("ig:" + self.ig.story_paylas(adres))
                else:
                    raise
            if self.fb:                       # Facebook sayfası: hata Instagram paylaşımını durdurmaz
                try:
                    medya.append("fb:" + self.fb.story_paylas(adres))
                except Exception as e:  # noqa: BLE001
                    self.log(f"  Uyarı: Facebook story paylaşılamadı: {e}")
                    medya.append("fb:hata")
        self.durum.ayar_kaydet("instagram_hesap_id", self.ig.hesap_id())
        return medya, adresler


def _ozet_yaz(satirlar: list[str]) -> None:
    yol = os.environ.get("GITHUB_STEP_SUMMARY")
    if yol:
        with open(yol, "a", encoding="utf-8") as f:
            f.write("\n".join(satirlar) + "\n")


def _durumu_gonder(mesaj: str) -> None:
    if os.environ.get("GITHUB_ACTIONS") != "true":
        return
    def git(*a):
        return subprocess.run(["git", *a], cwd=KOK, capture_output=True, text=True)
    git("add", "data/durum.json")
    if git("diff", "--cached", "--quiet").returncode == 0:
        return
    git("commit", "-m", mesaj)
    dal = os.environ.get("GITHUB_REF_NAME") or "main"
    for _ in range(3):
        if git("push", "origin", f"HEAD:refs/heads/{dal}").returncode == 0:
            return
        git("pull", "--rebase", "origin", dal)
    print("Uyarı: durum dosyası depoya gönderilemedi.")


def calistir() -> int:
    cfg = yukle()
    durum = Durum()
    simdi = tarih.simdi()
    deneme = os.environ.get("KT_DENEME", "").strip().lower() in DOGRU
    elle = os.environ.get("KT_GOREV", "").strip()

    if elle:
        gorev, _, tur = elle.partition(":")
        if gorev not in GOREVLER:
            print(f"Bilinmeyen görev: {gorev}. Seçenekler: {', '.join(GOREVLER)}")
            return 2
        slotlar = [{"saat": f"{simdi:%H:%M}", "gorev": gorev, **({"tur": tur} if tur else {}), "elle": True}]
    else:
        slotlar = zamani_gelenler(cfg.get("zamanlama", []), simdi, durum, int(cfg.get("tolerans_dakika", 150)))
    if not slotlar:
        print(f"{simdi:%H:%M} — zamanı gelen görev yok.")
        return 0

    print(f"{simdi:%d.%m.%Y %H:%M} — {len(slotlar)} görev{' (DENEME MODU)' if deneme else ''}")
    baglam = Baglam(cfg=cfg, tema=render.Tema.configden(cfg), durum=durum, simdi=simdi, deneme=deneme,
                    cikti=KOK / "cikti" / f"{simdi:%Y%m%d-%H%M%S}", oturum=yeni_oturum(),
                    yayinla=Yayinci(cfg, durum, deneme))
    ozet = [f"## Konya'da Trafik — {simdi:%d.%m.%Y %H:%M}{' (deneme)' if deneme else ''}", "",
            "| Görev | Durum | Açıklama |", "|---|---|---|"]
    hata_var = False
    for slot in slotlar:
        sid = slot_kimligi(slot)
        print(f"▶ {sid}")
        try:
            sonuc = GOREVLER[slot["gorev"]](baglam, slot)
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            sonuc = Sonuc("hata", f"{type(e).__name__}: {e}")
        etiket = "deneme (paylaşılmadı)" if deneme and sonuc.durum == "paylasildi" else sonuc.durum
        print(f"  {etiket}: {sonuc.mesaj}")
        for a in sonuc.adresler:
            print(f"  görsel: {a}")

        if not deneme and not slot.get("elle"):
            onceki = durum.slot(simdi.date(), sid)
            kayit_durum = sonuc.durum
            if sonuc.durum == "hata":
                sayi = int(onceki.get("hata_sayisi", 0)) + 1
                kayit_durum = "hata_kalici" if sayi >= EN_FAZLA_HATA else "hata"
                durum.slot_kaydet(simdi.date(), sid, hata_sayisi=sayi)
            durum.slot_kaydet(simdi.date(), sid, durum=kayit_durum, mesaj=sonuc.mesaj[:300], medya=sonuc.medya)
        if sonuc.durum == "hata":
            hata_var = True
        gorsel = " ".join(f"[görsel {i}]({a})" for i, a in enumerate(sonuc.adresler, 1) if a.startswith("http"))
        ozet.append(f"| {sid} | {etiket} | {sonuc.mesaj[:160].replace('|', '/')} {gorsel} |")

    _ozet_yaz(ozet)
    if not deneme:
        durum.buda(simdi.date())
        if durum.degisti:
            durum.kaydet()
            _durumu_gonder(f"durum: {simdi:%d.%m %H:%M} ({', '.join(slot_kimligi(s) for s in slotlar)})")
    return 1 if hata_var else 0


def _ornek_foto(yol: Path) -> Path:
    """Önizleme için basit, telifsiz bir örnek 'şehir' görseli çizer."""
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (1080, 1100))
    d = ImageDraw.Draw(img)
    for y in range(1100):
        t = y / 1100
        d.line((0, y, 1080, y), fill=(int(90 + 80 * t), int(140 + 60 * t), int(200 + 30 * t)))
    for i, (x, w, h) in enumerate([(-20, 260, 620), (230, 200, 760), (420, 300, 540), (700, 220, 820), (900, 220, 600)]):
        renk = (200 - i * 12, 170 - i * 8, 140 - i * 6)
        d.rectangle((x, 1100 - h, x + w, 1100), fill=renk)
        for wy in range(1100 - h + 40, 1060, 70):
            for wx in range(x + 25, x + w - 30, 55):
                d.rectangle((wx, wy, wx + 28, wy + 38), fill=(235, 238, 240))
    d.rectangle((0, 980, 1080, 1100), fill=(70, 72, 75))
    for x in range(0, 1080, 160):
        d.rectangle((x + 30, 1035, x + 110, 1045), fill=(245, 245, 245))
    yol.parent.mkdir(parents=True, exist_ok=True)
    img.save(yol, quality=90)
    return yol


def onizleme() -> int:
    from .kaynaklar import eczane as ek, soz as sk, vefat as vk
    cfg = yukle()
    tema = render.Tema.configden(cfg)
    bugun = tarih.bugun()
    cikti = KOK / "cikti" / "onizleme"
    fx = KOK / "tests" / "fixtures"
    s = sk.gunun_sozu(bugun)
    yollar = render.gunun_sozu(tema, s["soz"], s.get("kaynak", "Atasözü"), tarih.tarih_yazi(bugun), cikti)
    liste = ek.resmi_coz((fx / "eczane_resmi.html").read_text(encoding="utf-8"), bugun, ("merkez", "ilceler"))
    yollar += render.nobetci_eczaneler(tema, ek.ilceye_gore(liste.eczaneler), tarih.tarih_yazi(bugun), cikti)
    kayitlar = vk.tablo_coz((fx / "vefat.html").read_text(encoding="utf-8"))
    yollar += render.vefat_edenler(tema, [k.story() for k in kayitlar], tarih.tarih_yazi(bugun), cikti)
    ornek = dict(
        konum="Selçuklu", kategori="TRAFİK",
        baslik_metin="Örnek başlık: Mevlana Caddesi'nde çalışma nedeniyle tek şerit kapalı",
        etiketler=["Çalışma 18.00'e kadar", "Alternatif: Ankara Cd."],
        metin=("Bu bir önizleme metnidir. Gerçek haberler her gün web aramasıyla bulunur ve yapay zekâ "
               "tarafından sayfanın üslubuyla bu alana yazılır. Metin üç ila beş cümle uzunluğundadır; "
               "ne olduğu, nerede ve ne zaman olduğu ve sonucun ne olduğu anlatılır."),
        kapanis="Sürücülerin dikkatli olması rica olunur.",
        tarih_yazisi=tarih.tarih_yazi(bugun, gun_adi=False),
    )
    yollar += render.haber(tema, **ornek, cikti=cikti, foto=_ornek_foto(cikti / "ornek-foto.jpg"),
                           dosya_adi="haber-fotografli.jpg")
    yollar += render.haber(tema, **ornek, cikti=cikti, foto=None, dosya_adi="haber-fotografsiz.jpg")
    for y in yollar:
        print(y.relative_to(KOK))
    return 0


def kontrol() -> int:
    from .instagram import Instagram
    from .kaynaklar import eczane as ek, vefat as vk
    cfg = yukle()
    sorun = 0
    oturum = yeni_oturum()
    print("— Veri kaynakları")
    for ad, url in (("Eczacı Odası", ek.RESMI_URL), ("Eczane yedek", ek.YEDEK_URL), ("Vefat listesi", vk.ANA_URL)):
        try:
            r = oturum.get(url, timeout=30)
            print(f"  {ad}: HTTP {r.status_code}")
            sorun += r.status_code != 200
        except Exception as e:  # noqa: BLE001
            print(f"  {ad}: ulaşılamadı ({type(e).__name__})")
            sorun += 1
    print("— Ajans ve kurum haberleri")
    from .kaynaklar import ajans as ak
    for kaynak in (cfg.get("ajans") or {}).get("kaynaklar", []):
        try:
            haberler = ak.kaynak_haberleri(oturum, kaynak, tarih.simdi(), 72, 4, log=lambda *_: None)
            fotolu = sum(1 for h in haberler if h.gorsel)
            print(f"  {kaynak['ad']}: son 3 günde {len(haberler)} Konya haberi ({fotolu} tanesi fotoğraflı)")
            sorun += not haberler
        except Exception as e:  # noqa: BLE001
            print(f"  {kaynak['ad']}: okunamadı ({type(e).__name__})")
            sorun += 1
    print("— Claude API anahtarı: " + ("tanımlı" if os.environ.get("ANTHROPIC_API_KEY")
                                        else "tanımlı değil (haber story'leri atlanır)"))
    cf = os.environ.get("CF_ACCOUNT_ID") and os.environ.get("CF_API_TOKEN")
    print("— Yapay zekâ görseli (Cloudflare): " + ("tanımlı" if cf else "tanımlı değil (temsili görsel üretilmez)"))
    from .instagram import FacebookSayfa
    ayar = cfg.get("instagram", {})
    token = os.environ.get("IG_ACCESS_TOKEN", "")
    sayfa_id = str(cfg.get("sayfa", {}).get("facebook_sayfa_id", ""))
    surum = ayar.get("graph_api_surum", "v23.0")
    print("— Instagram")
    try:
        ig = Instagram(token, surum=surum, hesap_id=ayar.get("instagram_hesap_id") or None, sayfa_id=sayfa_id)
        bilgi = ig.hesap_bilgisi()
        print(f"  Hesap: @{bilgi.get('username')} (kimlik {ig.hesap_id()}, takipçi {bilgi.get('followers_count')})")
        limit = ig.paylasim_limiti()
        print(f"  Son 24 saatte API ile paylaşım: {limit.get('quota_usage')} / {limit.get('config', {}).get('quota_total')}")
        if os.environ.get("GITHUB_ACTIONS") == "true":
            from .gorsel_depo import GorselDepo
            from .kaynaklar import soz as sk
            s = sk.gunun_sozu(tarih.bugun())
            yol = render.gunun_sozu(render.Tema.configden(cfg), s["soz"], s.get("kaynak", "Atasözü"),
                                    tarih.tarih_yazi(tarih.bugun()), KOK / "cikti" / "kontrol")[0]
            adres = GorselDepo(KOK).yukle([yol], f"kontrol/{tarih.simdi():%Y%m%d-%H%M%S}")[0]
            durum = ig.konteyner_dene(adres)
            print(f"  Deneme görseli: {adres}")
            print(f"  Instagram görseli {'kabul etti (paylaşılmadı)' if durum == 'FINISHED' else 'kabul etmedi: ' + durum}")
            sorun += durum != "FINISHED"
    except Exception as e:  # noqa: BLE001
        print(f"  HATA: {e}")
        sorun += 1
    if (cfg.get("facebook") or {}).get("story_paylas", True):
        print("— Facebook sayfası")
        try:
            print(f"  Sayfa: {FacebookSayfa(token, sayfa_id, surum=surum).kontrol()} — story paylaşımına hazır")
        except Exception as e:  # noqa: BLE001
            print(f"  HATA: {e}")
            sorun += 1
    print("Sonuç: " + ("her şey hazır." if not sorun else f"{sorun} sorun var."))
    return 1 if sorun else 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m kt", description="Konya'da Trafik story otomasyonu")
    p.add_argument("komut", nargs="?", default="calistir", choices=["calistir", "onizleme", "kontrol"])
    a = p.parse_args(argv)
    return {"calistir": calistir, "onizleme": onizleme, "kontrol": kontrol}[a.komut]()


if __name__ == "__main__":
    sys.exit(main())
