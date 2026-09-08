"""Tahap 1 panen Berita Desa: kueri Google News RSS dan parse item.

Google News RSS menang uji banding sumber 7 September 2026 (relevansi
tertinggi, murni berita, tanpa kunci API/kuota, ada pubDate + source).
Jebakan: `link` tiap item adalah redirect `news.google.com`, bukan URL
penerbit — didekode di tahap 2 (`dekode.py`).
"""

import logging
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime

import requests

from src.berita.schemas import ItemRSS

logger = logging.getLogger(__name__)

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/127.0 Safari/537.36"
)
MAKS_ITEM = 10
_TIMEOUT_RSS = 20.0


def kueri_desa(nmdesa: str, nmkab: str) -> str:
    """Kueri PRD akar §4 — nama desa + kabupaten (varian teruji)."""
    return f"desa {nmdesa} {nmkab}"


def _parse_terbit(pub_date: str) -> datetime | None:
    """Parse pubDate RFC 822; gagal parse = None, bukan galat.

    RFC 822 mengizinkan zona ditiadakan, dan stdlib lalu mengembalikan
    datetime NAIVE — Google News selalu mengirim GMT, tapi ini jaga-jaga
    kalau tidak. Anggap UTC (bukan zona lokal server): itu asumsi baku
    email/feed RFC-822 saat zona kosong. Tanpa ini nilai naive mengalir ke
    `model_dump(mode="json")`, serialize tanpa offset, lalu Postgres
    menafsirkannya memakai zona server sendiri untuk kolom timestamptz —
    menggeser waktu baris itu diam-diam.
    """
    try:
        hasil = parsedate_to_datetime(pub_date)
    except (TypeError, ValueError):
        return None
    return hasil if hasil.tzinfo is not None else hasil.replace(tzinfo=UTC)


def cari_rss(kueri: str, maks: int = MAKS_ITEM) -> list[ItemRSS]:
    """Ambil maksimum `maks` item berita Google News RSS untuk `kueri`."""
    q = urllib.parse.quote(kueri)
    url = f"https://news.google.com/rss/search?q={q}&hl=id&gl=ID&ceid=ID:id"
    r = requests.get(url, headers={"User-Agent": UA}, timeout=_TIMEOUT_RSS)
    r.raise_for_status()
    # fromstring menerima bytes supaya deklarasi encoding XML yang menang.
    root = ET.fromstring(r.content)
    items: list[ItemRSS] = []
    for it in root.iter("item"):
        src = it.find("source")
        items.append(
            ItemRSS(
                judul=(it.findtext("title") or "").strip(),
                link=(it.findtext("link") or "").strip(),
                terbit_pada=_parse_terbit((it.findtext("pubDate") or "").strip()),
                sumber=(src.text.strip() if src is not None and src.text else ""),
            )
        )
        if len(items) >= maks:
            break
    return items
