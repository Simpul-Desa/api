"""Uji integrasi untuk GET /api/model/desa-kembar/{iddesa} (Tugas 8)."""

import json
from pathlib import Path

import httpx
import pytest

from src.desa_kembar.constants import KETERANGAN_TANPA_VEKTOR
from src.desa_kembar.service import baca_kembar_kab
from tests.conftest import D1, D2, D3

pytestmark = pytest.mark.anyio

IDDESA_TAK_DIKENAL = "9999999999"
IDDESA_POLA_SALAH = "180104000"  # 9 digit


@pytest.mark.integration
async def test_desa_tanpa_vektor_kembalikan_tetangga_kosong_dan_keterangan(
    dir_data_lengkap: Path, klien: httpx.AsyncClient
) -> None:
    """D3 sah di indeks tapi SENGAJA absen dari desa-kembar/1801.json."""
    respons = await klien.get(f"/api/model/desa-kembar/{D3}")

    assert respons.status_code == 200
    body = respons.json()
    assert body["sukses"] is True
    assert body["data"] == {
        "iddesa": D3,
        "tetangga": [],
        "keterangan": KETERANGAN_TANPA_VEKTOR,
    }


@pytest.mark.integration
async def test_tetangga_membawa_identitas_hasil_join_dari_indeks(
    dir_data_lengkap: Path, klien: httpx.AsyncClient
) -> None:
    """D1 punya 1 tetangga (D2) di desa-kembar/1801.json — identitas di-join."""
    respons = await klien.get(f"/api/model/desa-kembar/{D1}")

    assert respons.status_code == 200
    body = respons.json()
    assert body["data"]["iddesa"] == D1
    assert body["data"]["tetangga"] == [
        {
            "iddesa": D2,
            "nmdesa": "DESA A2",
            "nmkec": "KEC ALFA",
            "idkab": "1801",
            "nmkab": "KAB SATU",
            "persen": 50.0,
        }
    ]
    assert body["data"]["keterangan"] is None


@pytest.mark.integration
async def test_k_satu_kembalikan_maksimal_satu_tetangga(
    dir_data_lengkap: Path, klien: httpx.AsyncClient
) -> None:
    respons = await klien.get(f"/api/model/desa-kembar/{D1}", params={"k": 1})

    assert respons.status_code == 200
    assert len(respons.json()["data"]["tetangga"]) == 1


@pytest.mark.integration
async def test_k_lebih_besar_dari_jumlah_tetangga_kembalikan_semua(
    dir_data_lengkap: Path, klien: httpx.AsyncClient
) -> None:
    respons = await klien.get(f"/api/model/desa-kembar/{D1}", params={"k": 999})

    assert respons.status_code == 200
    assert len(respons.json()["data"]["tetangga"]) == 1


@pytest.mark.integration
async def test_k_nol_kembalikan_422(
    dir_data_lengkap: Path, klien: httpx.AsyncClient
) -> None:
    respons = await klien.get(f"/api/model/desa-kembar/{D1}", params={"k": 0})

    assert respons.status_code == 422
    assert respons.json()["galat"]["kode"] == "PARAMETER_TIDAK_VALID"


@pytest.mark.integration
async def test_iddesa_pola_salah_kembalikan_422(
    dir_data_lengkap: Path, klien: httpx.AsyncClient
) -> None:
    respons = await klien.get(f"/api/model/desa-kembar/{IDDESA_POLA_SALAH}")

    assert respons.status_code == 422
    assert respons.json()["galat"]["kode"] == "PARAMETER_TIDAK_VALID"


@pytest.mark.integration
async def test_iddesa_tak_dikenal_kembalikan_404_desa_tidak_ada(
    dir_data_lengkap: Path, klien: httpx.AsyncClient
) -> None:
    respons = await klien.get(f"/api/model/desa-kembar/{IDDESA_TAK_DIKENAL}")

    assert respons.status_code == 404
    body = respons.json()
    assert body["sukses"] is False
    assert body["galat"]["kode"] == "DESA_TIDAK_ADA"


@pytest.mark.integration
async def test_berkas_kembar_tanpa_kunci_desa_jalur_anggun(
    dir_data_lengkap: Path, klien: httpx.AsyncClient
) -> None:
    """Berkas kembar tanpa kunci `desa` = sama dengan desa tanpa vektor.

    Rute ini SENGAJA tidak 503: kontraknya (keputusan desain fase 3 butir 6)
    adalah 200 + `keterangan`, dan jalur anggun itu sudah ada.
    """
    (dir_data_lengkap / "desa-kembar" / "1801.json").write_text(
        json.dumps({"idkab": "1801", "k": 5}), encoding="utf-8"
    )
    baca_kembar_kab.cache_clear()

    respons = await klien.get(f"/api/model/desa-kembar/{D1}")

    assert respons.status_code == 200
    assert respons.json()["data"]["keterangan"] == KETERANGAN_TANPA_VEKTOR
