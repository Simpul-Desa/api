"""Uji unit pembaca berkas kartu ekonomi per kabupaten (`src/kartu/service.py`)."""

import json
import logging
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from src.config import ambil_pengaturan
from src.kartu.service import baca_kartu_kab

IDKAB = "1801"
D1 = "1801000001"
D2 = "1801000002"


@pytest.fixture(autouse=True)
def _bersihkan_cache_lru() -> Iterator[None]:
    """Bersihkan cache LRU sebelum & sesudah tiap uji.

    `baca_kartu_kab` di-cache lewat `functools.lru_cache` pada level modul —
    tanpa pembersihan ini hasil satu uji bocor ke uji lain walau memakai
    `tmp_path` (dan `dir_data_str`) yang berbeda.
    """
    baca_kartu_kab.cache_clear()
    yield
    baca_kartu_kab.cache_clear()


def _tulis_kartu_kab(dir_data: Path, isi: Any) -> None:
    """Tulis `kartu-ekonomi/kartu/<IDKAB>.json` berisi `isi`."""
    path = dir_data / "kartu-ekonomi" / "kartu" / f"{IDKAB}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(isi), encoding="utf-8")


def _kartu_kab_sintetis(dir_data: Path) -> None:
    """Bangun satu berkas kartu kabupaten minimal — dua desa, identitas saja."""
    _tulis_kartu_kab(
        dir_data,
        {
            "idkab": IDKAB,
            "kartu": [
                {"identitas": {"iddesa": D1, "nama": "DESA A1"}},
                {"identitas": {"iddesa": D2, "nama": "DESA A2"}},
            ],
        },
    )


@pytest.mark.unit
def test_baca_kartu_kab_kembalikan_dict_terindeks_per_iddesa(tmp_path: Path) -> None:
    _kartu_kab_sintetis(tmp_path)

    hasil = baca_kartu_kab(str(tmp_path), IDKAB)

    assert hasil is not None
    assert set(hasil.keys()) == {D1, D2}
    assert hasil[D1]["identitas"]["nama"] == "DESA A1"
    assert hasil[D2]["identitas"]["nama"] == "DESA A2"


@pytest.mark.unit
def test_baca_kartu_kab_idkab_tak_dikenal_kembalikan_none(tmp_path: Path) -> None:
    _kartu_kab_sintetis(tmp_path)

    hasil = baca_kartu_kab(str(tmp_path), "9999")

    assert hasil is None


@pytest.mark.unit
def test_baca_kartu_kab_lru_hit_kembalikan_objek_identik(tmp_path: Path) -> None:
    _kartu_kab_sintetis(tmp_path)

    hasil_pertama = baca_kartu_kab(str(tmp_path), IDKAB)
    hasil_kedua = baca_kartu_kab(str(tmp_path), IDKAB)

    assert hasil_pertama is hasil_kedua


@pytest.mark.unit
def test_berkas_tanpa_kunci_kartu_kembalikan_none(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Berkas ada tapi tanpa kunci `kartu` = bukan berkas kartu.

    `None` di sini menjadi 503 DATA_BELUM_SIAP lewat `wajib()` di rutenya,
    sejalur dengan berkas yang hilang atau korup — bukan 500 KeyError.
    """
    _tulis_kartu_kab(tmp_path, {"idkab": IDKAB, "nmkab": "KAB SATU"})

    with caplog.at_level(logging.WARNING):
        hasil = baca_kartu_kab(str(tmp_path), IDKAB)

    assert hasil is None
    assert IDKAB in caplog.text


@pytest.mark.unit
def test_kartu_tanpa_identitas_iddesa_dilewati_bukan_menjatuhkan_kabupaten(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Satu kartu cacat kehilangan SATU desa, bukan 200-an desa sekabupaten."""
    _tulis_kartu_kab(
        tmp_path,
        {
            "idkab": IDKAB,
            "kartu": [
                {"identitas": {"iddesa": D1, "nama": "DESA A1"}},
                {"identitas": {"nama": "TANPA IDDESA"}},
                {"potensi": {}},
            ],
        },
    )

    with caplog.at_level(logging.WARNING):
        hasil = baca_kartu_kab(str(tmp_path), IDKAB)

    assert hasil is not None
    assert set(hasil.keys()) == {D1}
    assert caplog.text.count("tanpa identitas.iddesa") == 2


@pytest.mark.unit
def test_maxsize_cache_mengikuti_pengaturan() -> None:
    """`maxsize` pembaca kartu dibaca dari `Pengaturan`, bukan literal.

    Satu entri cache kartu terukur ±13 MB RAM; `maxsize` yang dipatok mati
    membuat tombol memori produksi (`MAKS_CACHE_KARTU` di `render.yaml`)
    tidak berpengaruh apa pun.
    """
    assert baca_kartu_kab.cache_info().maxsize == ambil_pengaturan().maks_cache_kartu
