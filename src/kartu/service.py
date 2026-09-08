"""Akses data Kartu Ekonomi Desa: pembaca berkas kartu per kabupaten.

Pembaca ini di-cache LRU dan dipanggil per permintaan endpoint detail kartu.
`dir_data` diterima sebagai `str` (bukan `Path`) supaya argumennya hashable
untuk `lru_cache`.
"""

import logging
from functools import lru_cache
from pathlib import Path
from typing import Any

from src.config import ambil_pengaturan
from src.datastore import muat_json_atau_none

logger = logging.getLogger(__name__)


@lru_cache(maxsize=ambil_pengaturan().maks_cache_kartu)
def baca_kartu_kab(dir_data_str: str, idkab: str) -> dict[str, dict[str, Any]] | None:
    """Baca `kartu-ekonomi/kartu/<idkab>.json`, kembalikan `{iddesa: kartu}`.

    Hasil di-cache LRU (`MAKS_CACHE_KARTU`, bawaan 16) berkunci
    `(dir_data_str, idkab)`.
    Pengindeksan per `identitas.iddesa` dilakukan sekali di sini — bukan per
    permintaan endpoint. None bila berkas hilang/korup.
    """
    path = Path(dir_data_str) / "kartu-ekonomi" / "kartu" / f"{idkab}.json"
    isi = muat_json_atau_none(path, f"kartu ekonomi kab {idkab}")
    if isi is None:
        return None

    daftar_kartu = isi.get("kartu")
    if daftar_kartu is None:
        # Berkas ada tapi tanpa kunci `kartu` = bukan berkas kartu. None di
        # sini menjadi 503 DATA_BELUM_SIAP lewat `wajib()` di rutenya
        # (`src/kartu/router.py` dan `src/laporan/router.py`), sejalur dengan
        # berkas yang hilang atau korup.
        logger.warning("berkas kartu kab %s tanpa kunci 'kartu'", idkab)
        return None

    # Satu kartu tanpa `identitas.iddesa` DILEWATI, tidak menjatuhkan seluruh
    # kabupaten: 17.467 kartu nyata semuanya punya kunci itu, jadi kalau satu
    # hilang yang benar adalah kehilangan satu desa dan mencatatnya, bukan
    # kehilangan 200-an desa sekabupaten.
    hasil: dict[str, dict[str, Any]] = {}
    for kartu in daftar_kartu:
        iddesa = (kartu.get("identitas") or {}).get("iddesa")
        if iddesa is None:
            logger.warning("kartu tanpa identitas.iddesa di kab %s dilewati", idkab)
            continue
        hasil[iddesa] = kartu
    return hasil
