"""Story görsellerini herkese açık bir adrese koyma.

Instagram API görseli bir internet adresinden kendisi indirir. Görseller bu deponun
'gorseller' dalına tek commit olarak (her seferinde yenisiyle değiştirilerek) gönderilir
ve raw.githubusercontent.com adresi Instagram'a verilir. Instagram görseli paylaşım
anında kopyaladığı için eski görsellerin saklanmasına gerek yoktur; böylece depo büyümez.
"""

from __future__ import annotations

import os
import subprocess
import tempfile
import time
from pathlib import Path

import requests


class DepoHatasi(Exception):
    pass


def _git(*arglar: str, cwd: Path, env: dict | None = None) -> str:
    r = subprocess.run(["git", *arglar], cwd=cwd, env=env, capture_output=True, text=True)
    if r.returncode != 0:
        raise DepoHatasi(f"git {' '.join(arglar[:2])} başarısız: {r.stderr.strip()[:300]}")
    return r.stdout.strip()


class GorselDepo:
    def __init__(self, depo_dizini: Path, dal: str = "gorseller", repo: str | None = None, log=print):
        self.dizin = depo_dizini
        self.dal = dal
        self.repo = repo or os.environ.get("GITHUB_REPOSITORY", "")
        if not self.repo:
            raise DepoHatasi("GITHUB_REPOSITORY bilinmiyor; görseller yüklenemez.")
        self.log = log

    def yukle(self, dosyalar: list[Path], klasor: str) -> list[str]:
        with tempfile.TemporaryDirectory() as tmp:
            env = os.environ.copy()
            env["GIT_INDEX_FILE"] = str(Path(tmp) / "index")
            _git("read-tree", "--empty", cwd=self.dizin, env=env)
            for f in dosyalar:
                blob = _git("hash-object", "-w", str(f), cwd=self.dizin, env=env)
                _git("update-index", "--add", "--cacheinfo", f"100644,{blob},{klasor}/{f.name}",
                     cwd=self.dizin, env=env)
            agac = _git("write-tree", cwd=self.dizin, env=env)
            commit = _git("commit-tree", agac, "-m", f"Story görselleri: {klasor}", cwd=self.dizin, env=env)
        _git("push", "--force", "origin", f"{commit}:refs/heads/{self.dal}", cwd=self.dizin)
        urller = [f"https://raw.githubusercontent.com/{self.repo}/{commit}/{klasor}/{f.name}" for f in dosyalar]
        for u in urller:
            self._erisilebilir_mi(u)
        return urller

    @staticmethod
    def yedek_adres(raw_url: str) -> str:
        """raw.githubusercontent.com adresini jsDelivr CDN adresine çevirir."""
        parca = raw_url.replace("https://raw.githubusercontent.com/", "").split("/", 3)
        sahip, depo, commit, yol = parca
        return f"https://cdn.jsdelivr.net/gh/{sahip}/{depo}@{commit}/{yol}"

    def _erisilebilir_mi(self, url: str, sure: int = 90) -> None:
        bitis = time.time() + sure
        while time.time() < bitis:
            try:
                r = requests.head(url, timeout=15, allow_redirects=True)
                if r.status_code == 200:
                    return
            except requests.RequestException:
                pass
            time.sleep(4)
        self.log(f"  Uyarı: görsel adresi {sure} sn içinde erişilebilir olmadı: {url}")
