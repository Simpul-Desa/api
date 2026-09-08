"""Orkestrator panen Berita Desa per desa (dipanggil rute admin fase 7).

Validasi `iddesa` ke indeks kartu adalah tanggung jawab PEMANGGIL —
`panen_desa` menerima identitas desa yang sudah sah. Satu artikel yang gagal
total tidak menggagalkan panen desa: dicatat warning lalu lanjut ke artikel
berikutnya. Hanya artikel lolos saring/verifikasi yang disimpan (retensi
tanpa batas — tabel tidak boleh penuh sampah).
"""

import logging
import time
from datetime import UTC, datetime
from typing import Any

import httpx

from src.berita.constants import MIN_PANJANG_TEKS
from src.berita.harvest.content import (
    ambil_html,
    rangkum_ekstraktif,
    teks_dari_html,
    verifikasi,
)
from src.berita.harvest.decode import dekode_link
from src.berita.harvest.filter import saring_gemini
from src.berita.harvest.rss import cari_rss, kueri_desa
from src.berita.harvest.store import simpan_berita, url_tersimpan
from src.berita.schemas import BarisBerita, HasilPanen, ItemRSS
from src.config import Pengaturan

logger = logging.getLogger(__name__)

JEDA_ANTAR_ARTIKEL = 1.0  # detik; jaga sopan ke penerbit dan Google

# Mutu perangkum, dari yang paling tepercaya. Dipakai HANYA di sini (bukan
# constants.py) — satu-satunya pemakainya adalah penjaga downgrade di bawah.
_PERINGKAT_PERANGKUM = {"gemini": 2, "ekstraktif": 1, "judul-rss": 0}


def _baris_judul_rss(
    item: ItemRSS, iddesa: str, url: str, nmdesa: str, nmkab: str, kini: datetime
) -> BarisBerita | None:
    """Jalur fallback: isi tak terbaca — verifikasi pindah ke judul RSS."""
    if not verifikasi(item.judul, nmdesa, nmkab):
        return None
    return BarisBerita(
        iddesa=iddesa,
        judul=item.judul,
        url=url,
        sumber=item.sumber,
        terbit_pada=item.terbit_pada,
        dipanen_pada=kini,
        rangkuman=None,
        kategori=[],
        perangkum="judul-rss",
    )


def _olah_item(
    item: ItemRSS, iddesa: str, nmdesa: str, nmkab: str, kunci_gemini: str
) -> BarisBerita | None:
    """Satu item RSS menjadi baris siap simpan, atau None bila dibuang."""
    kini = datetime.now(UTC)

    url = dekode_link(item.link)
    if url is None:
        # Tanpa URL penerbit isi tak mungkin diambil — simpan link Google
        # apa adanya; browser pengguna yang mengikuti redirect-nya.
        return _baris_judul_rss(item, iddesa, item.link, nmdesa, nmkab, kini)

    html, _cara = ambil_html(url)
    teks = teks_dari_html(html) if html else ""
    if len(teks) < MIN_PANJANG_TEKS:
        return _baris_judul_rss(item, iddesa, url, nmdesa, nmkab, kini)

    if kunci_gemini:
        try:
            hasil = saring_gemini(teks, nmdesa, nmkab, kunci_gemini)
        except Exception:
            logger.warning(
                "saring Gemini gagal total; turun ke ekstraktif: %s",
                url,
                exc_info=True,
            )
        else:
            if not (hasil.relevan and hasil.desa_benar):
                return None
            return BarisBerita(
                iddesa=iddesa,
                judul=item.judul,
                url=url,
                sumber=item.sumber,
                terbit_pada=item.terbit_pada,
                dipanen_pada=kini,
                rangkuman=hasil.rangkuman,
                kategori=hasil.kategori,
                perangkum="gemini",
            )

    if not verifikasi(teks, nmdesa, nmkab):
        return None
    return BarisBerita(
        iddesa=iddesa,
        judul=item.judul,
        url=url,
        sumber=item.sumber,
        terbit_pada=item.terbit_pada,
        dipanen_pada=kini,
        rangkuman=rangkum_ekstraktif(teks, nmdesa),
        kategori=[],
        perangkum="ekstraktif",
    )


def _jaga_dari_downgrade(
    baris: BarisBerita, tersimpan: dict[str, dict[str, Any]]
) -> BarisBerita:
    """Cegah re-panen menurunkan mutu ringkasan yang sudah tersimpan.

    `simpan_berita` upsert `merge-duplicates` — PostgREST mengganti SELURUH
    baris dari payload, bukan menggabung per kolom. Tanpa penjagaan ini,
    penerbit yang mendadak memblokir scraping (atau Gemini yang gagal)
    membuat `_olah_item` jatuh ke `judul-rss` kosong, menimpa ringkasan
    gemini lama, dan tercatat sebagai `n_duplikat` biasa — tak terlihat
    siapa pun. `dipanen_pada` pada `baris` SENGAJA tidak disentuh (tetap
    stempel baru) supaya status penyegaran `/api/admin/status` tetap maju
    walau kontennya dipertahankan.
    """
    lama = tersimpan.get(baris.url)
    if lama is None:
        return baris
    peringkat_baru = _PERINGKAT_PERANGKUM.get(baris.perangkum, 0)
    peringkat_lama = _PERINGKAT_PERANGKUM.get(lama["perangkum"], 0)
    if peringkat_baru >= peringkat_lama:
        return baris
    return baris.model_copy(
        update={
            "rangkuman": lama["rangkuman"],
            "kategori": lama["kategori"],
            "perangkum": lama["perangkum"],
        }
    )


def panen_desa(
    klien: httpx.Client,
    pengaturan: Pengaturan,
    iddesa: str,
    nmdesa: str,
    nmkab: str,
) -> HasilPanen:
    """Panen berita satu desa: RSS -> dekode -> isi -> saring -> simpan."""
    kunci_gemini = pengaturan.gemini_api_key.get_secret_value()
    items = cari_rss(kueri_desa(nmdesa, nmkab))

    kandidat: list[BarisBerita] = []
    n_dibuang = 0
    n_gagal = 0
    for item in items:
        try:
            baris = _olah_item(item, iddesa, nmdesa, nmkab, kunci_gemini)
        except Exception:
            # Galat teknis (exception) — beda dari penolakan editorial di
            # bawah, lihat docstring HasilPanen.n_gagal (FIX 1).
            logger.warning("artikel gagal diolah: %s", item.link, exc_info=True)
            n_gagal += 1
        else:
            if baris is None:
                n_dibuang += 1
            else:
                kandidat.append(baris)
        time.sleep(JEDA_ANTAR_ARTIKEL)

    # RSS bisa memuat URL sama dua kali; upsert satu permintaan tidak boleh
    # menyentuh baris yang sama dua kali (galat ON CONFLICT Postgres).
    unik: dict[str, BarisBerita] = {}
    for b in kandidat:
        unik.setdefault(b.url, b)
    kandidat = list(unik.values())

    if not kandidat:
        return HasilPanen(
            iddesa=iddesa,
            n_baru=0,
            n_duplikat=0,
            n_dibuang=n_dibuang,
            n_gagal=n_gagal,
        )

    lama = url_tersimpan(klien, pengaturan, iddesa)
    n_baru = sum(1 for b in kandidat if b.url not in lama)
    kandidat = [_jaga_dari_downgrade(b, lama) for b in kandidat]
    simpan_berita(klien, pengaturan, kandidat)
    return HasilPanen(
        iddesa=iddesa,
        n_baru=n_baru,
        n_duplikat=len(kandidat) - n_baru,
        n_dibuang=n_dibuang,
        n_gagal=n_gagal,
    )
