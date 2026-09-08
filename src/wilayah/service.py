"""Penjaga keberadaan kode wilayah pada `wilayah.json`.

Dipakai lintas modul: `wilayah`, `geo`, dan `peta_peran` semuanya perlu
menolak kode provinsi/kabupaten yang bentuknya sah tapi tidak dikenal.
Sebelum dipusatkan di sini, pola `any(...)`-nya ditulis ulang di lima baris
pada tiga berkas router.

Modul ini sengaja tidak mengimpor modul domain lain — hanya `src.exceptions` —
supaya modul yang memakainya tidak pernah membentuk impor sirkular.
"""

from typing import Any

from src.exceptions import DATA_BELUM_SIAP, WILAYAH_TIDAK_ADA, GalatAPI


def _daftar(wilayah: dict[str, Any], kunci: str) -> list[dict[str, Any]]:
    """Ambil daftar `kunci` dari `wilayah.json`; 503 bila kuncinya hilang.

    `muat_json_atau_none` tidak memvalidasi isi artefak, jadi penjaga ini
    dipanggil dari rute mana pun yang menerima kode wilayah — termasuk
    `peta_peran` dan `geo` yang tidak pernah menyentuh daftarnya sendiri.
    `GalatAPI` dilempar langsung, bukan lewat `datastore.wajib()`, supaya
    modul ini tetap hanya bergantung pada `src.exceptions` (lihat docstring
    modul: menjaga impornya sempit mencegah impor sirkular).
    """
    nilai = wilayah.get(kunci)
    if nilai is None:
        raise GalatAPI(
            DATA_BELUM_SIAP, f"data daftar {kunci} wilayah belum dimuat di server", 503
        )
    hasil: list[dict[str, Any]] = nilai
    return hasil


def prov_dikenal(wilayah: dict[str, Any], idprov: str) -> bool:
    """True bila `idprov` ada di daftar provinsi `wilayah.json`."""
    return any(p.get("idprov") == idprov for p in _daftar(wilayah, "provinsi"))


def kab_dikenal(wilayah: dict[str, Any], idkab: str) -> bool:
    """True bila `idkab` ada di daftar kabupaten `wilayah.json`."""
    return any(k.get("idkab") == idkab for k in _daftar(wilayah, "kabupaten"))


def wajib_prov_dikenal(wilayah: dict[str, Any], idprov: str) -> None:
    """Lempar 404 `WILAYAH_TIDAK_ADA` bila `idprov` tak dikenal."""
    if not prov_dikenal(wilayah, idprov):
        raise GalatAPI(WILAYAH_TIDAK_ADA, f"provinsi {idprov} tidak dikenal", 404)


def wajib_kab_dikenal(wilayah: dict[str, Any], idkab: str) -> None:
    """Lempar 404 `WILAYAH_TIDAK_ADA` bila `idkab` tak dikenal."""
    if not kab_dikenal(wilayah, idkab):
        raise GalatAPI(WILAYAH_TIDAK_ADA, f"kabupaten {idkab} tidak dikenal", 404)
