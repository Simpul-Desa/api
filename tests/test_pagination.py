"""Uji unit untuk helper paginasi seragam."""

from typing import get_args

import pytest

from src.models import Meta
from src.pagination import (
    BATAS_BAWAAN,
    BATAS_MAKS,
    HAL_MAKS,
    ParamBatas,
    ParamHal,
    potong,
)


@pytest.mark.unit
def test_hal_1_bawaan() -> None:
    daftar = list(range(10))

    potongan, meta = potong(daftar, hal=1, batas=BATAS_BAWAAN)

    assert potongan == list(range(10))
    assert meta == Meta(total=10, hal=1, batas=BATAS_BAWAAN)


@pytest.mark.unit
def test_hal_melebihi_total_potongan_kosong_tapi_total_benar() -> None:
    daftar = list(range(5))

    potongan, meta = potong(daftar, hal=99, batas=10)

    assert potongan == []
    assert meta == Meta(total=5, hal=99, batas=10)


@pytest.mark.unit
def test_batas_maksimum_diterima() -> None:
    daftar = list(range(600))

    potongan, meta = potong(daftar, hal=1, batas=BATAS_MAKS)

    assert len(potongan) == BATAS_MAKS
    assert potongan == list(range(BATAS_MAKS))
    assert meta == Meta(total=600, hal=1, batas=BATAS_MAKS)


@pytest.mark.unit
def test_potongan_benar_di_halaman_tengah() -> None:
    daftar = list(range(25))

    potongan, meta = potong(daftar, hal=2, batas=10)

    assert potongan == list(range(10, 20))
    assert meta == Meta(total=25, hal=2, batas=10)


@pytest.mark.unit
def test_daftar_kosong() -> None:
    potongan, meta = potong([], hal=1, batas=BATAS_BAWAAN)

    assert potongan == []
    assert meta == Meta(total=0, hal=1, batas=BATAS_BAWAAN)


@pytest.mark.unit
def test_potong_tidak_memutasi_daftar_asal() -> None:
    daftar = [1, 2, 3, 4, 5]
    asal = list(daftar)

    potongan, _ = potong(daftar, hal=1, batas=2)

    assert daftar == asal
    assert potongan is not daftar


def _ambil_ge_le(anotasi: object) -> tuple[int | None, int | None]:
    """Ambil batas `ge`/`le` dari metadata `annotated_types` sebuah `Annotated[int, Query(...)]`."""
    _, info = get_args(anotasi)
    ge = next((m.ge for m in info.metadata if hasattr(m, "ge")), None)
    le = next((m.le for m in info.metadata if hasattr(m, "le")), None)
    return ge, le


@pytest.mark.unit
def test_hal_maks_bernilai_10_000() -> None:
    """500.000 baris (batas bawaan 50 x HAL_MAKS) tetap di bawah cacah desa
    terbesar di proyek ini (kartu index, 17.467 desa) — tak ada pemanggil sah
    yang bisa menyentuh batas ini."""
    assert HAL_MAKS == 10_000


@pytest.mark.unit
def test_param_hal_punya_batas_bawah_dan_atas() -> None:
    ge, le = _ambil_ge_le(ParamHal)

    assert ge == 1
    assert le == HAL_MAKS


@pytest.mark.unit
def test_param_batas_batas_bawah_dan_atas_tidak_berubah() -> None:
    """`ParamBatas` sudah bertutup atas sebelum FIX 3 - pastikan tetap begitu."""
    ge, le = _ambil_ge_le(ParamBatas)

    assert ge == 1
    assert le == BATAS_MAKS


@pytest.mark.unit
def test_potong_di_hal_maks_menghasilkan_halaman_kosong_total_benar() -> None:
    daftar = list(range(100))

    potongan, meta = potong(daftar, hal=HAL_MAKS, batas=BATAS_BAWAAN)

    assert potongan == []
    assert meta == Meta(total=100, hal=HAL_MAKS, batas=BATAS_BAWAAN)
