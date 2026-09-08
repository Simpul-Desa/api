"""Logika Peta Peran Desa: proyeksi baris ringkas dan penyaringan.

Fungsi murni — tanpa FastAPI, tanpa I/O.
"""

from typing import Any

from src.peta_peran.constants import KOLOM_RINGKAS


def proyeksi_ringkas(baris: dict[str, Any]) -> dict[str, Any] | None:
    """Proyeksikan satu baris `peta_peran.json` penuh ke 12 kolom ringkas
    sesuai kontrak `GET /api/model/peta-peran` — kolom mutu data lain (mis.
    `alasan_belum_terpetakan`) tidak ikut di daftar; lihat rute detail untuk
    baris penuh.

    `None` bila salah satu dari 12 kolom itu TIDAK ADA di baris. Sengaja tidak
    memakai `.get()` berdefault: `keyakinan` dan `sumber_dominan` adalah kolom
    mutu (PRD §8), dan `None` yang dikarang di sini tidak bisa dibedakan
    pembaca dari nilai kosong yang memang sah. Pemanggil yang melewati baris
    ini WAJIB mencatatnya — hilang tanpa jejak lebih buruk daripada 500.
    """
    if any(kolom not in baris for kolom in KOLOM_RINGKAS):
        return None
    return {kolom: baris[kolom] for kolom in KOLOM_RINGKAS}
