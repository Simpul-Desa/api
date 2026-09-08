"""Uji integrasi untuk rute kartu (`src/kartu/router.py`, Tugas 6)."""

from dataclasses import replace
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI

from tests.conftest import D1, PembuatKlien

pytestmark = pytest.mark.anyio

IDDESA_POLA_SALAH = "180104000"  # 9 digit
IDDESA_TAK_DIKENAL = "1801049999"  # 10 digit, tak ada di indeks kartu


@pytest.mark.integration
async def test_kartu_iddesa_pola_salah_kembalikan_422(
    dir_data_lengkap: Path, klien: httpx.AsyncClient
) -> None:
    respons = await klien.get(f"/api/model/kartu/{IDDESA_POLA_SALAH}")

    assert respons.status_code == 422
    assert respons.json()["galat"]["kode"] == "PARAMETER_TIDAK_VALID"


@pytest.mark.integration
async def test_kartu_iddesa_tak_dikenal_kembalikan_404(
    dir_data_lengkap: Path, klien: httpx.AsyncClient
) -> None:
    respons = await klien.get(f"/api/model/kartu/{IDDESA_TAK_DIKENAL}")

    assert respons.status_code == 404
    body = respons.json()
    assert body["sukses"] is False
    assert body["galat"]["kode"] == "DESA_TIDAK_ADA"


@pytest.mark.integration
async def test_kartu_desa_hilang_dari_berkas_kartu_kembalikan_404(
    dir_data_lengkap: Path,
    aplikasi: FastAPI,
    buat_klien: PembuatKlien,
) -> None:
    """Desa terdaftar di indeks tetapi tidak ada di berkas kartu kabupatennya.

    Cabang 404 kedua rute ini — indeks dan berkas kartu adalah dua artefak
    terpisah, jadi keduanya bisa tidak sinkron. Kondisinya dibuat dengan
    menambah satu entri indeks di `app.state`, bukan dengan mengubah
    fixture bersama. Teknik sama seperti
    `tests/laporan/test_router.py::test_laporan_desa_hilang_dari_berkas_kartu_kembalikan_404`.
    """
    klien = await buat_klien(aplikasi, lifespan=True)
    simpanan = aplikasi.state.simpanan
    iddesa_hantu = "1801049998"
    aplikasi.state.simpanan = replace(
        simpanan,
        indeks_per_desa={
            **(simpanan.indeks_per_desa or {}),
            iddesa_hantu: {"iddesa": iddesa_hantu, "idkab": "1801"},
        },
    )

    respons = await klien.get(f"/api/model/kartu/{iddesa_hantu}")

    assert respons.status_code == 404
    body = respons.json()
    assert body["sukses"] is False
    assert body["galat"]["kode"] == "DESA_TIDAK_ADA"


@pytest.mark.integration
async def test_kartu_sukses_berisi_blok_identitas_peta_peran_mutu_data(
    dir_data_lengkap: Path, klien: httpx.AsyncClient
) -> None:
    respons = await klien.get(f"/api/model/kartu/{D1}")

    assert respons.status_code == 200
    body = respons.json()
    assert body["sukses"] is True
    assert body["meta"] is None

    data = body["data"]
    assert set(data.keys()) >= {"identitas", "peta_peran", "mutu_data"}
    assert data["identitas"]["iddesa"] == D1
    assert data["peta_peran"]["zona"] == "Zona Mitra"
    assert "punya_geometri" in data["mutu_data"]


@pytest.mark.integration
async def test_kartu_tanpa_data_kembalikan_503(
    dir_data_manifest: Path, klien: httpx.AsyncClient
) -> None:
    """`dir_data_manifest` cuma punya manifest.json — indeks kartu belum ada."""
    respons = await klien.get(f"/api/model/kartu/{D1}")

    assert respons.status_code == 503
    body = respons.json()
    assert body["sukses"] is False
    assert body["galat"]["kode"] == "DATA_BELUM_SIAP"
