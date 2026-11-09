"""Instagram Graph API ile story paylaşımı (Facebook Login yolu, sistem kullanıcısı token'ı).

Akış: konteyner oluştur (media_type=STORIES, image_url) -> durum FINISHED olana kadar bekle
-> media_publish. Token URL'ye değil Authorization başlığına konur, böylece loglara düşmez.
"""

from __future__ import annotations

import time

import requests


class InstagramHatasi(Exception):
    pass


GECICI_KODLAR = {1, 2, 4, 17, 32, 341, 9004, 9007, 2207001, 2207008, 2207051}


class Instagram:
    def __init__(self, token: str, surum: str = "v23.0", hesap_id: str | None = None,
                 sayfa_id: str | None = None, oturum: requests.Session | None = None, log=print):
        if not token:
            raise InstagramHatasi("IG_ACCESS_TOKEN tanımlı değil (GitHub > Settings > Secrets).")
        self.taban = f"https://graph.facebook.com/{surum}"
        self.hesap_id_ = hesap_id or None
        self.sayfa_id = sayfa_id
        self.s = oturum or requests.Session()
        self.s.headers.update({"Authorization": f"Bearer {token}"})
        self.log = log

    # ------------------------------------------------------------------ temel istek
    def _istek(self, yontem: str, yol: str, deneme: int = 3, **veri) -> dict:
        url = f"{self.taban}/{yol.lstrip('/')}"
        son_hata = None
        for i in range(deneme):
            try:
                if yontem == "GET":
                    r = self.s.get(url, params=veri, timeout=60)
                else:
                    r = self.s.post(url, data=veri, timeout=60)
            except requests.RequestException as e:
                son_hata = InstagramHatasi(f"Bağlantı hatası: {type(e).__name__}")
                time.sleep(5 * (i + 1))
                continue
            try:
                govde = r.json()
            except ValueError:
                govde = {}
            if r.ok and "error" not in govde:
                return govde
            hata = govde.get("error", {})
            kod = hata.get("code")
            alt = hata.get("error_subcode")
            mesaj = hata.get("error_user_msg") or hata.get("message") or r.text[:200]
            son_hata = InstagramHatasi(f"Graph API hatası (HTTP {r.status_code}, kod {kod}/{alt}): {mesaj}")
            if hata.get("is_transient") or kod in GECICI_KODLAR or alt in GECICI_KODLAR or r.status_code >= 500:
                time.sleep(8 * (i + 1))
                continue
            break
        raise son_hata

    # ------------------------------------------------------------------ hesap
    def hesap_id(self) -> str:
        if self.hesap_id_:
            return self.hesap_id_
        if not self.sayfa_id:
            raise InstagramHatasi("Instagram hesap kimliği ya da Facebook sayfa kimliği gerekli.")
        veri = self._istek("GET", self.sayfa_id, fields="instagram_business_account,name")
        hesap = (veri.get("instagram_business_account") or {}).get("id")
        if not hesap:
            raise InstagramHatasi(f"'{veri.get('name', self.sayfa_id)}' sayfasına bağlı Instagram hesabı bulunamadı.")
        self.hesap_id_ = hesap
        return hesap

    def hesap_bilgisi(self) -> dict:
        return self._istek("GET", self.hesap_id(), fields="username,name,followers_count")

    def paylasim_limiti(self) -> dict:
        veri = self._istek("GET", f"{self.hesap_id()}/content_publishing_limit", fields="config,quota_usage")
        return (veri.get("data") or [{}])[0]

    # ------------------------------------------------------------------ story
    def story_paylas(self, gorsel_url: str) -> str:
        ig = self.hesap_id()
        konteyner = self._istek("POST", f"{ig}/media", media_type="STORIES", image_url=gorsel_url)["id"]
        durum = ""
        for i in range(20):
            veri = self._istek("GET", konteyner, fields="status_code,status")
            durum = veri.get("status_code", "")
            if durum == "FINISHED":
                break
            if durum in ("ERROR", "EXPIRED"):
                raise InstagramHatasi(f"Görsel Instagram tarafından işlenemedi ({durum}): {veri.get('status', '')}")
            time.sleep(3 if i < 5 else 10)
        else:
            raise InstagramHatasi(f"Görsel işleme zaman aşımına uğradı (son durum: {durum}).")
        medya = self._istek("POST", f"{ig}/media_publish", creation_id=konteyner)["id"]
        self.log(f"  Instagram'a story paylaşıldı (medya {medya}).")
        return medya
