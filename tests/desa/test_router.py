"""Uji integrasi untuk GET /api/desa/cari (`src/desa/router.py`, Tugas 5)."""

from pathlib import Path

import httpx
import pytest

from src.desa.service import kunci_urutan, peringkat_kecocokan
from tests.conftest import D1, D2, D3, IDKAB_SATU

pytestmark = pytest.mark.anyio

BARIS_D1 = {
    "iddesa": D1,
    "nmdesa": "DESA A1",
    "nmkec": "KEC ALFA",
    "idkab": IDKAB_SATU,
    "nmkab": "KAB SATU",
    "zona": "Zona Mitra",
    "keyakinan": "normal",
    "potensi_dominan": "Simpul Logistik",
    "desil_sp": 9,
    "desil_sk": 10,
    "n_program": 0,
}


@pytest.mark.integration
async def test_cari_sukses_amplop_dan_meta_total(
    dir_data_lengkap: Path, klien: httpx.AsyncClient
) -> None:
    """`q=DESA` cocok di keenam desa (semua nama berawalan "DESA ")."""
    respons = await klien.get("/api/desa/cari", params={"q": "DESA"})

    assert respons.status_code == 200
    body = respons.json()
    assert body["sukses"] is True
    assert body["meta"]["total"] == 6
    assert len(body["data"]) == 6
    assert BARIS_D1 in body["data"]


@pytest.mark.integration
async def test_cari_q_kurang_dari_2_huruf_kembalikan_422(
    dir_data_lengkap: Path, klien: httpx.AsyncClient
) -> None:
    respons = await klien.get("/api/desa/cari", params={"q": "A"})

    assert respons.status_code == 422
    assert respons.json()["galat"]["kode"] == "PARAMETER_TIDAK_VALID"


@pytest.mark.integration
async def test_cari_tidak_peka_kapital(
    dir_data_lengkap: Path, klien: httpx.AsyncClient
) -> None:
    respons = await klien.get("/api/desa/cari", params={"q": "desa a1"})

    assert respons.status_code == 200
    body = respons.json()
    assert body["meta"]["total"] == 1
    assert body["data"][0]["iddesa"] == D1


@pytest.mark.integration
async def test_cari_filter_kab_menyaring_ke_satu_kabupaten(
    dir_data_lengkap: Path, klien: httpx.AsyncClient
) -> None:
    respons = await klien.get("/api/desa/cari", params={"q": "DESA", "kab": IDKAB_SATU})

    assert respons.status_code == 200
    body = respons.json()
    assert body["meta"]["total"] == 3
    assert {baris["idkab"] for baris in body["data"]} == {IDKAB_SATU}


@pytest.mark.integration
async def test_cari_kab_bentuk_salah_kembalikan_422(
    dir_data_lengkap: Path, klien: httpx.AsyncClient
) -> None:
    respons = await klien.get("/api/desa/cari", params={"q": "DESA", "kab": "18"})

    assert respons.status_code == 422
    assert respons.json()["galat"]["kode"] == "PARAMETER_TIDAK_VALID"


@pytest.mark.integration
async def test_cari_paginasi_batas_memotong_hasil(
    dir_data_lengkap: Path, klien: httpx.AsyncClient
) -> None:
    respons = await klien.get("/api/desa/cari", params={"q": "DESA", "batas": 2})

    assert respons.status_code == 200
    body = respons.json()
    assert len(body["data"]) == 2
    assert body["meta"] == {"total": 6, "hal": 1, "batas": 2, "parameter": None}


@pytest.mark.integration
async def test_cari_seri_urut_iddesa_menaik_dalam_satu_kabupaten(
    dir_data_lengkap: Path, klien: httpx.AsyncClient
) -> None:
    """Ketiga desa kab 1801 sama-sama cocok awalan "DESA" — seri lewat `iddesa`."""
    respons = await klien.get("/api/desa/cari", params={"q": "DESA", "kab": IDKAB_SATU})

    assert [baris["iddesa"] for baris in respons.json()["data"]] == [D1, D2, D3]


@pytest.mark.unit
def test_peringkat_kecocokan_awalan_dapat_peringkat_lebih_tinggi() -> None:
    """`peringkat_kecocokan` — 0 (awalan) < 1 (sekadar mengandung substring).

    Fixture `dir_data_lengkap` memakai nama desa berpola seragam ("DESA
    <huruf><angka>") sehingga tidak ada query tunggal yang menghasilkan
    campuran awalan+substring lewat HTTP (semua nama berbagi awalan "DESA "
    yang sama persis) — logika peringkat diuji langsung di sini alih-alih
    lewat endpoint.
    """
    assert peringkat_kecocokan("desa sukamaju", "desa") == 0
    assert peringkat_kecocokan("suka desa indah", "desa") == 1


@pytest.mark.unit
def test_kunci_urutan_awalan_menang_atas_substring_walau_iddesa_lebih_besar() -> None:
    """Baris substring dengan `iddesa` lebih kecil tidak boleh menang dari
    baris awalan dengan `iddesa` lebih besar — peringkat kecocokan
    didahulukan sebelum seri urut `iddesa`."""
    baris_substring = {"nmdesa": "Suka Desa Indah", "iddesa": "1801040001"}
    baris_awalan = {"nmdesa": "Desa Sukamaju", "iddesa": "1801040002"}

    terurut = sorted(
        [baris_substring, baris_awalan],
        key=lambda b: kunci_urutan(b, "desa"),
    )

    assert terurut == [baris_awalan, baris_substring]
