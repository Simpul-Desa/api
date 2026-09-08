"""Uji unit untuk skema modul admin (`src/admin/schemas.py`, Tugas 5)."""

import pytest
from pydantic import ValidationError

from src.admin.constants import MAKS_DESA_SEGARKAN
from src.admin.schemas import PermintaanSegarkan, PermintaanUbahPeran

IDDESA_SAH = "1801042001"
IDDESA_POLA_SALAH = "180104200"  # 9 digit


@pytest.mark.unit
def test_permintaan_segarkan_daftar_kosong_ditolak() -> None:
    with pytest.raises(ValidationError):
        PermintaanSegarkan(iddesa=[])


@pytest.mark.unit
def test_permintaan_segarkan_daftar_51_anggota_ditolak() -> None:
    daftar = [IDDESA_SAH] * (MAKS_DESA_SEGARKAN + 1)

    with pytest.raises(ValidationError):
        PermintaanSegarkan(iddesa=daftar)


@pytest.mark.unit
def test_permintaan_segarkan_batas_maks_diterima() -> None:
    daftar = [IDDESA_SAH] * MAKS_DESA_SEGARKAN

    hasil = PermintaanSegarkan(iddesa=daftar)

    assert len(hasil.iddesa) == MAKS_DESA_SEGARKAN


@pytest.mark.unit
def test_permintaan_segarkan_iddesa_9_digit_ditolak() -> None:
    with pytest.raises(ValidationError):
        PermintaanSegarkan(iddesa=[IDDESA_POLA_SALAH])


@pytest.mark.unit
def test_permintaan_ubah_peran_nilai_tak_dikenal_ditolak() -> None:
    with pytest.raises(ValidationError):
        PermintaanUbahPeran(peran="raja")


@pytest.mark.unit
@pytest.mark.parametrize("peran", ["tamu", "pemerintah", "swasta", "admin"])
def test_permintaan_ubah_peran_nilai_sah_diterima(peran: str) -> None:
    hasil = PermintaanUbahPeran(peran=peran)

    assert hasil.peran == peran
