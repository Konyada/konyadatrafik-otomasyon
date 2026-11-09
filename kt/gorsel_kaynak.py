"""Haber story'sinin fotoğrafını bulma.

Sıra (config.yaml > haber.gorsel_sirasi ile değiştirilebilir):
  ajans        Haber abone olunan ajanstan (İHA, DHA, AA) ya da resmi kurumdan geldiyse onun fotoğrafı
  resmi        Web'den bulunan haber resmi bir kurum sitesindeyse (.bel.tr, .gov.tr…) o sayfanın fotoğrafı
  arsiv        Sayfanın kendi arşivi: ilçe ya da kategori klasörü (assets/fotograflar)
  yapay_zeka   Konuya uygun yapay zekâ görseli (Cloudflare Workers AI, ücretsiz kota) — "Temsili görsel"
  arsiv_genel  Arşivdeki "genel" klasörü
Hiçbiri yoksa haber fotoğrafsız tasarımla basılır.
"""

from __future__ import annotations

import base64
import io
import os
from pathlib import Path
from urllib.parse import urlparse

from PIL import Image

from . import fotograf
from .kaynaklar.ajans import makale_coz

VARSAYILAN_SIRA = ["ajans", "resmi", "arsiv", "yapay_zeka", "arsiv_genel"]
RESMI_SONEKLER = (".bel.tr", ".gov.tr", ".edu.tr", ".pol.tr", ".tsk.tr")
YZ_MODEL = "@cf/black-forest-labs/flux-1-schnell"
EN_BUYUK = 15 * 1024 * 1024


def resmi_mi(url: str) -> bool:
    try:
        alan = urlparse(url).netloc.lower().split(":")[0]
    except ValueError:
        return False
    return any(alan.endswith(s) for s in RESMI_SONEKLER)


def _gorsel_kaydet(veri: bytes, hedef: Path, en_az_genislik: int = 500) -> Path | None:
    try:
        with Image.open(io.BytesIO(veri)) as im:
            im = im.convert("RGB")
            if im.width < en_az_genislik:
                return None
            hedef.parent.mkdir(parents=True, exist_ok=True)
            im.save(hedef, "JPEG", quality=92)
            return hedef
    except Exception:  # noqa: BLE001
        return None


def indir(oturum, url: str, hedef: Path) -> Path | None:
    if not url:
        return None
    r = oturum.get(url, timeout=40, headers={"Referer": f"{urlparse(url).scheme}://{urlparse(url).netloc}/"})
    r.raise_for_status()
    if len(r.content) > EN_BUYUK:
        return None
    return _gorsel_kaydet(r.content, hedef)


def resmi_sayfa_gorseli(oturum, sayfa_url: str) -> str:
    r = oturum.get(sayfa_url, timeout=30)
    r.raise_for_status()
    return makale_coz(r.text, sayfa_url).get("gorsel", "")


def yapay_zeka_gorseli(oturum, tarif: str, hedef: Path, hesap: str, token: str, model: str = YZ_MODEL) -> Path | None:
    if not (tarif and hesap and token):
        return None
    istem = (f"{tarif}. Realistic news photograph, natural light, Konya, Turkey. "
             "No text, no letters, no logos, no watermark, no identifiable faces, no blood, no children.")
    r = oturum.post(f"https://api.cloudflare.com/client/v4/accounts/{hesap}/ai/run/{model}",
                    headers={"Authorization": f"Bearer {token}"}, json={"prompt": istem[:2000], "steps": 6},
                    timeout=120)
    if r.headers.get("content-type", "").startswith("image/"):
        return _gorsel_kaydet(r.content, hedef, en_az_genislik=256)
    if r.status_code >= 400:
        raise RuntimeError(f"Cloudflare AI hatası {r.status_code}: {r.text[:200]}")
    veri = r.json()
    b64 = (veri.get("result") or {}).get("image") or veri.get("image")
    if not b64:
        raise RuntimeError("Cloudflare AI yanıtında görsel yok.")
    return _gorsel_kaydet(base64.b64decode(b64), hedef, en_az_genislik=256)


def foto_bul(h: dict, cfg: dict, oturum, cikti: Path, log=print) -> tuple[Path | None, str]:
    """(fotoğraf yolu, fotoğraf notu) döndürür. Not: 'Foto: İHA', 'Temsili görsel' ya da ''."""
    sira = (cfg.get("haber") or {}).get("gorsel_sirasi") or VARSAYILAN_SIRA
    ajans = h.get("ajans") or {}
    anahtar = h.get("baslik", "")
    for adim in sira:
        try:
            if adim == "ajans" and ajans.get("gorsel"):
                yol = indir(oturum, ajans["gorsel"], cikti / "foto-ajans.jpg")
                if yol:
                    return yol, ajans.get("kredi") or f"Foto: {ajans.get('ad', '')}"
            elif adim == "resmi" and not ajans and resmi_mi(h.get("kaynak_url", "")):
                yol = indir(oturum, resmi_sayfa_gorseli(oturum, h["kaynak_url"]), cikti / "foto-resmi.jpg")
                if yol:
                    return yol, f"Foto: {h.get('kaynak_adi', '')}".strip()
            elif adim == "arsiv":
                yol = fotograf.sec(h.get("kategori", ""), h.get("konum", ""), anahtar, genel=False)
                if yol:
                    return yol, ""
            elif adim == "yapay_zeka":
                yol = yapay_zeka_gorseli(oturum, h.get("gorsel_tarifi", ""), cikti / "foto-yz.jpg",
                                         os.environ.get("CF_ACCOUNT_ID", ""), os.environ.get("CF_API_TOKEN", ""),
                                         (cfg.get("haber") or {}).get("yapay_zeka_modeli", YZ_MODEL))
                if yol:
                    return yol, "Temsili görsel"
            elif adim == "arsiv_genel":
                yol = fotograf.sec_genel(anahtar)
                if yol:
                    return yol, ""
        except Exception as e:  # noqa: BLE001
            log(f"  Fotoğraf ({adim}) alınamadı: {type(e).__name__}: {str(e)[:150]}")
    return None, ""
