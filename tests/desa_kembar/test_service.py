"""Uji unit logika dan pembaca data Desa Kembar (`src/desa_kembar/service.py`)."""

import json
from collections.abc import Iterator
from pathlib import Path

import pytest

from src.config import ambil_pengaturan
from src.desa_kembar.schemas import TetanggaKembar
from src.desa_kembar.service import (
    baca_kembar_kab,
    potong_tetangga,
    tetangga_terjoin,
)

IDKAB = "1801"


@pytest.fixture(autouse=True)
def _bersihkan_cache_lru() -> Iterator[None]:
    """Bersihkan cache LRU `baca_kembar_kab` sebelum & sesudah tiap uji."""
    baca_kembar_kab.cache_clear()
    yield
    baca_kembar_kab.cache_clear()


def _kembar_kab_sintetis(dir_data: Path) -> None:
    """Tulis `desa-kembar/<IDKAB>.json` minimal — satu desa, satu tetangga."""
    path = dir_data / "desa-kembar" / f"{IDKAB}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "idkab": IDKAB,
                "k": 1,
                "p95_jarak": 1.0,
                "desa": {"1801000001": [{"iddesa": "1801000002", "persen": 50.0}]},
            }
        ),
        encoding="utf-8",
    )


@pytest.mark.unit
def test_potong_tetangga_memotong_daftar_lebih_besar() -> None:
    """Uji langsung logika pemotongan `k` dengan >1 tetangga (fixture data
    hanya sediakan 1 tetangga per desa, tak cukup membuktikan pemotongan
    sungguhan) — verifikasi `potong_tetangga` benar memotong dari 3 ke 2."""
    tetangga = [
        TetanggaKembar(
            iddesa=f"180104000{n}",
            nmdesa=None,
            nmkec=None,
            idkab=None,
            nmkab=None,
            persen=float(n),
        )
        for n in range(1, 4)
    ]

    dipotong = potong_tetangga(tetangga, 2)

    assert len(dipotong) == 2
    assert dipotong == tetangga[:2]


@pytest.mark.unit
def test_potong_tetangga_k_none_kembalikan_seluruhnya() -> None:
    tetangga = [
        TetanggaKembar(
            iddesa="1801040001",
            nmdesa=None,
            nmkec=None,
            idkab=None,
            nmkab=None,
            persen=1.0,
        )
    ]

    assert potong_tetangga(tetangga, None) == tetangga


@pytest.mark.unit
def test_tetangga_terjoin_identitas_hilang_isi_none_tanpa_crash() -> None:
    """`iddesa` tetangga yang tak ada di indeks tak boleh membuat fungsi crash."""
    baris_tetangga = [{"iddesa": "0000000000", "persen": 12.5}]

    hasil = tetangga_terjoin(baris_tetangga, indeks_per_desa={})

    assert hasil == [
        TetanggaKembar(
            iddesa="0000000000",
            nmdesa=None,
            nmkec=None,
            idkab=None,
            nmkab=None,
            persen=12.5,
        )
    ]


@pytest.mark.unit
def test_baca_kembar_kab_kembalikan_isi_apa_adanya(tmp_path: Path) -> None:
    _kembar_kab_sintetis(tmp_path)

    hasil = baca_kembar_kab(str(tmp_path), IDKAB)

    assert hasil is not None
    assert hasil["idkab"] == IDKAB
    assert hasil["desa"]["1801000001"] == [{"iddesa": "1801000002", "persen": 50.0}]


@pytest.mark.unit
def test_baca_kembar_kab_lru_hit_kembalikan_objek_identik(tmp_path: Path) -> None:
    _kembar_kab_sintetis(tmp_path)

    hasil_pertama = baca_kembar_kab(str(tmp_path), IDKAB)
    hasil_kedua = baca_kembar_kab(str(tmp_path), IDKAB)

    assert hasil_pertama is hasil_kedua


@pytest.mark.unit
def test_maxsize_cache_mengikuti_pengaturan() -> None:
    """`maxsize` pembaca desa kembar dibaca dari `Pengaturan`, bukan literal."""
    assert baca_kembar_kab.cache_info().maxsize == ambil_pengaturan().maks_cache_kembar
