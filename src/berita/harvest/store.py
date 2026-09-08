"""Tahap 5 panen Berita Desa: hitung baru/duplikat dan upsert ke PostgREST.

Klien sinkron (`httpx.Client`) karena panen berjalan di threadpool; rute
baca memakai `AsyncClient` milik `app.state`. Pola header service key
mengikuti `src/autentikasi.py` — kunci tidak pernah masuk log.
"""

import logging
from typing import Any

import httpx

from src.berita.schemas import BarisBerita
from src.config import Pengaturan

logger = logging.getLogger(__name__)

# Batas baris yang diminta saat membaca berita tersimpan satu desa. Diminta
# EKSPLISIT: tanpa `limit`, batasnya ditentukan konfigurasi max-rows PostgREST
# di luar kendali kode ini, dan pemotongan senyap membuat penjaga
# anti-downgrade (`orchestrator._jaga_dari_downgrade`) buta pada baris yang
# tidak terbaca — ringkasan gemini lama bisa tertimpa walau penjaganya aktif.
# Satu panen mengambil paling banyak `rss.MAKS_ITEM` (10) artikel, jadi 2.000
# baris menampung arsip desa yang sangat panjang sekalipun; `berita_desa`
# sengaja tanpa batas retensi (PRD §5), karena itu pemotongan tetap dideteksi.
MAKS_BARIS_TERSIMPAN = 2_000


def _header(pengaturan: Pengaturan) -> dict[str, str]:
    kunci = pengaturan.supabase_service_role_key.get_secret_value()
    return {"apikey": kunci, "Authorization": f"Bearer {kunci}"}


def url_tersimpan(
    klien: httpx.Client, pengaturan: Pengaturan, iddesa: str
) -> dict[str, dict[str, Any]]:
    """Baris tersimpan untuk `iddesa`, per URL: `rangkuman`/`kategori`/`perangkum`.

    Dahulu hanya set URL (untuk hitung `n_baru`/`n_duplikat`). Diperluas
    supaya orchestrator.py bisa membandingkan mutu ringkasan lama vs baru
    sebelum upsert — `merge-duplicates` mengganti seluruh baris, jadi tanpa
    info ini re-panen yang gagal scraping/Gemini diam-diam menimpa ringkasan
    gemini lama dengan `judul-rss` kosong (lihat FIX 1).
    """
    respons = klien.get(
        f"{pengaturan.supabase_url}/rest/v1/berita_desa",
        params={
            "iddesa": f"eq.{iddesa}",
            "select": "url,rangkuman,kategori,perangkum",
            "limit": str(MAKS_BARIS_TERSIMPAN),
        },
        headers=_header(pengaturan),
    )
    respons.raise_for_status()
    baris_json = respons.json()
    if len(baris_json) >= MAKS_BARIS_TERSIMPAN:
        # Cacah pas di batas = hasilnya PASTI tidak lengkap. Diam di sini
        # berarti `n_baru` menggelembung, `n_duplikat` menyusut, dan penjaga
        # anti-downgrade kehilangan baris yang seharusnya ia lindungi.
        logger.warning(
            "berita tersimpan desa %s terpotong di batas %d baris — "
            "hitungan baru/duplikat dan penjaga downgrade tidak lengkap",
            iddesa,
            MAKS_BARIS_TERSIMPAN,
        )
    return {baris["url"]: baris for baris in baris_json}


def simpan_berita(
    klien: httpx.Client, pengaturan: Pengaturan, baris: list[BarisBerita]
) -> None:
    """Upsert `baris` (unik `iddesa`+`url`); duplikat diperbarui `dipanen_pada`-nya.

    `merge-duplicates` membuat `max(dipanen_pada)` per desa selalu mencerminkan
    penyegaran terakhir (status penyegaran PRD §4). Daftar kosong = tanpa
    panggilan jaringan.
    """
    if not baris:
        return
    respons = klien.post(
        f"{pengaturan.supabase_url}/rest/v1/berita_desa",
        params={"on_conflict": "iddesa,url"},
        headers={**_header(pengaturan), "Prefer": "resolution=merge-duplicates"},
        json=[b.model_dump(mode="json") for b in baris],
    )
    respons.raise_for_status()
