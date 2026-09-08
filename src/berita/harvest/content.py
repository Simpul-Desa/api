"""Tahap 3 panen Berita Desa: ambil HTML, ekstrak teks, verifikasi, ekstraktif.

Logika teruji putaran uji 7 September 2026: dua cara pengambilan berurutan
(requests lalu cloudscraper), deteksi halaman blokir dari ISI (halaman
blokir ber-status 200 nyata ada), retry berjeda acak menaik hanya untuk
galat transien — sinyal anti-bot langsung ganti cara karena mengulang tidak
akan menolong. Rangkuman ekstraktif adalah fallback tanpa LLM.
"""

import logging
import random
import re
import time
from typing import Any

import cloudscraper
import requests
from bs4 import BeautifulSoup
from bs4.element import Comment

logger = logging.getLogger(__name__)

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/127.0 Safari/537.36"
)
MIN_PANJANG_HTML = 2000  # respons lebih pendek bukan halaman artikel
MAKS_RANGKUMAN = 600
_STATUS_ANTI_BOT = (401, 403, 429, 503)

# Elemen yang teksnya bukan isi artikel (port terverifikasi, jangan dipangkas).
BLACKLIST = [
    "style",
    "label",
    "[document]",
    "embed",
    "img",
    "object",
    "noscript",
    "header",
    "html",
    "iframe",
    "audio",
    "picture",
    "meta",
    "title",
    "aside",
    "footer",
    "svg",
    "base",
    "figure",
    "form",
    "nav",
    "head",
    "link",
    "button",
    "source",
    "canvas",
    "br",
    "input",
    "script",
    "wbr",
    "video",
    "param",
    "hr",
    "ul",
    "li",
    "a",
]

TANDA_BLOKIR = [
    "just a moment",
    "checking your browser",
    "verify you are human",
    "enable javascript and cookies",
    "captcha",
    "attention required",
    "access denied",
    "cf-browser-verification",
    "akses ditolak",
    "are you a robot",
]


def kena_blokir(html: str) -> bool:
    """Deteksi halaman blokir/tantangan anti-bot dari isi (bukan kode status)."""
    cuplikan = html[:5000].lower()
    return any(t in cuplikan for t in TANDA_BLOKIR)


def ambil_html(url: str) -> tuple[str | None, str | None]:
    """Ambil HTML `url`: (html, cara) atau (None, None) bila kedua cara gagal.

    Dua cara berurutan — requests lalu cloudscraper. Galat transien dicoba
    ulang dengan jeda acak menaik; status anti-bot atau halaman blokir
    langsung pindah cara tanpa mengulang.
    """
    for cara, ulang in (("requests", 3), ("cloudscraper", 2)):
        for i in range(ulang):
            try:
                if cara == "requests":
                    r = requests.get(url, headers={"User-Agent": UA}, timeout=15)
                else:
                    # `cloudscraper.create_scraper()` mewarisi `requests.Session`
                    # (context manager, `__exit__` memanggil `close()`); tanpa
                    # `with` sesi baru tiap percobaan menumpuk sampai
                    # garbage collector sempat membereskannya.
                    with cloudscraper.create_scraper() as scraper:
                        r = scraper.get(url, timeout=20)
                if (
                    r.status_code == 200
                    and len(r.text) > MIN_PANJANG_HTML
                    and not kena_blokir(r.text)
                ):
                    return r.text, cara
                if r.status_code in _STATUS_ANTI_BOT or kena_blokir(r.text):
                    break
            except Exception:
                # WARNING (bukan debug): produksi berjalan level INFO
                # (src/main.py) — DNS/TLS/cloudscraper gagal harus terlihat,
                # kalau tidak scraper yang rusak total tak beda dari desa yang
                # memang minim berita.
                logger.warning("galat transien %s pada %s", cara, url, exc_info=True)
            time.sleep(random.uniform(1.5, 3.5) * (i + 1))
    return None, None


def teks_dari_html(html: str) -> str:
    """Teks polos artikel dari HTML; string kosong bila halaman tak terbaca."""

    def tampak(el: Any) -> bool:
        if el.parent.name in BLACKLIST:
            return False
        return not isinstance(el, Comment)

    try:
        soup = BeautifulSoup(html, "lxml")
        for b in soup(["nav", "ul", "li", "a", "span"]):
            try:
                b.decompose()
            except Exception:
                # Tetap debug (sengaja, BEDA dari except di bawah): ini
                # jalan sekali per elemen yang cocok, bukan sekali per
                # artikel — menaikkannya ke warning membanjiri log dengan
                # ratusan baris per artikel dan menenggelamkan sinyal yang
                # berguna.
                logger.debug("decompose elemen gagal", exc_info=True)
        badan = soup.body
        if badan is None:
            return ""
        teks = badan.find_all(string=True)
        data = " ".join(t.strip() for t in filter(tampak, teks) if t.strip())
        return re.sub(r"\s+", " ", data)
    except Exception:
        # WARNING (bukan debug): sekali per artikel, dan produksi berjalan
        # level INFO (src/main.py) — HTML tak terbaca harus terlihat di log
        # nyata, bukan menghilang seperti "desa ini memang minim berita".
        logger.warning("HTML tak terbaca sebagai artikel", exc_info=True)
        return ""


def verifikasi(teks: str, desa: str, kab: str) -> bool:
    """Benarkah `teks` menyebut nama desa DAN kabupaten (tak peka kapital)."""
    t = teks.lower()
    return desa.lower() in t and kab.lower() in t


def rangkum_ekstraktif(teks: str, desa: str, maks: int = 3) -> str:
    """Maks `maks` kalimat yang menyebut desa (fallback: kalimat-kalimat awal)."""
    kalimat = re.split(r"(?<=[.!?]) +", teks)
    pilih = [k for k in kalimat if desa.lower() in k.lower()][:maks]
    if not pilih:
        pilih = kalimat[:maks]
    return " ".join(pilih)[:MAKS_RANGKUMAN]
