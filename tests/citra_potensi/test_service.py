"""Uji unit pembaca berkas skor sel Citra Potensi (`src/citra_potensi/service.py`)."""

import json
from collections.abc import Iterator
from pathlib import Path

import pytest

from src.citra_potensi.service import baca_sel_citra
from src.config import ambil_pengaturan

BERKAS_SEL = "produksi/18/kom_prov_horti_01.json"


@pytest.fixture(autouse=True)
def _bersihkan_cache_lru() -> Iterator[None]:
    """Bersihkan cache LRU `baca_sel_citra` sebelum & sesudah tiap uji."""
    baca_sel_citra.cache_clear()
    yield
    baca_sel_citra.cache_clear()


def _sel_citra_sintetis(dir_data: Path) -> None:
    """Tulis satu berkas skor sel minimal di `citra-potensi/<BERKAS_SEL>`."""
    path = dir_data / "citra-potensi" / BERKAS_SEL
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "format_skor": ["sp", "sk", "desil_sp", "desil_sk"],
                "skor": {"1801000001": [80.0, 90.0, 1, 2]},
            }
        ),
        encoding="utf-8",
    )


@pytest.mark.unit
def test_baca_sel_citra_kembalikan_isi_berkas_produksi(tmp_path: Path) -> None:
    _sel_citra_sintetis(tmp_path)

    hasil = baca_sel_citra(str(tmp_path), BERKAS_SEL)

    assert hasil is not None
    assert hasil["skor"]["1801000001"] == [80.0, 90.0, 1, 2]


@pytest.mark.unit
def test_baca_sel_citra_lru_hit_kembalikan_objek_identik(tmp_path: Path) -> None:
    _sel_citra_sintetis(tmp_path)

    hasil_pertama = baca_sel_citra(str(tmp_path), BERKAS_SEL)
    hasil_kedua = baca_sel_citra(str(tmp_path), BERKAS_SEL)

    assert hasil_pertama is hasil_kedua


@pytest.mark.unit
def test_baca_sel_citra_tolak_path_traversal(tmp_path: Path) -> None:
    """Path yang keluar dari batas `dir_data` ditolak, bukan dibaca."""
    _sel_citra_sintetis(tmp_path)

    # "../../rahasia.json" dari citra-potensi/ keluar dari batas dir_data
    with pytest.raises(ValueError):
        baca_sel_citra(str(tmp_path), "../../rahasia.json")


@pytest.mark.unit
def test_maxsize_cache_mengikuti_pengaturan() -> None:
    """`maxsize` pembaca sel citra dibaca dari `Pengaturan`, bukan literal."""
    assert baca_sel_citra.cache_info().maxsize == ambil_pengaturan().maks_cache_citra
