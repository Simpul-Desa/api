"""Tahap 2 panen Berita Desa: dekode link news.google.com ke URL penerbit.

Terbukti 21/21 sukses pada putaran uji 7 September 2026. Tiap dekode
memakan ±1 request ke Google — `interval` jangan dihilangkan; penyegaran
massal (fase 7) bergantung pada jeda ini.
"""

import logging

from googlenewsdecoder import gnewsdecoder

logger = logging.getLogger(__name__)

JEDA_DEKODE = 1  # detik, jeda internal gnewsdecoder per link


def dekode_link(link: str, interval: int = JEDA_DEKODE) -> str | None:
    """URL penerbit dari link `news.google.com`; None bila dekode gagal."""
    try:
        d = gnewsdecoder(link, interval=interval)
    except Exception:
        logger.warning("dekode link Google News gagal: %s", link, exc_info=True)
        return None
    if isinstance(d, dict) and d.get("status"):
        return str(d["decoded_url"])
    return None
