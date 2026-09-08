"""Akses data Citra Potensi Desa: pembaca berkas skor per sel.

Pembaca di-cache LRU dan menolak path yang keluar dari `dir_data`
(path traversal lewat `../`). `dir_data` diterima sebagai `str` supaya
argumennya hashable untuk `lru_cache`.
"""

from functools import lru_cache
from pathlib import Path
from typing import Any

from src.config import ambil_pengaturan
from src.datastore import muat_json_atau_none


@lru_cache(maxsize=ambil_pengaturan().maks_cache_citra)
def baca_sel_citra(dir_data_str: str, berkas_rel: str) -> dict[str, Any] | None:
    """Baca `citra-potensi/<berkas_rel>`; tolak path yang keluar dari `dir_data`.

    Hasil di-cache LRU (`MAKS_CACHE_CITRA`, bawaan 16) berkunci
    `(dir_data_str, berkas_rel)`.
    Melempar `ValueError` bila `berkas_rel`, setelah digabung dan di-resolve,
    keluar dari batas direktori `dir_data` (path traversal lewat `../`). None
    (bukan exception) bila path sah tapi berkasnya hilang/korup.
    """
    dir_data = Path(dir_data_str).resolve()
    path = (dir_data / "citra-potensi" / berkas_rel).resolve()

    if not path.is_relative_to(dir_data):
        raise ValueError(f"path di luar batas dir_data ditolak: {berkas_rel}")

    return muat_json_atau_none(path, f"sel citra potensi {berkas_rel}")
