"""Uji integrasi untuk GET /api/geo/desa/{idkab} (Tugas 8).

httpx mendekode `Content-Encoding: gzip` otomatis — uji
memeriksa header respons + isi JSON terdekode, bukan bytes gzip mentah
(lihat rencana `.claude/PRPs/plans/fase-3-endpoint-baca.plan.md`, bagian
"Riset eksternal").
"""

from pathlib import Path

import httpx
import pytest

from tests.conftest import IDKAB_DUA, IDKAB_SATU

pytestmark = pytest.mark.anyio

IDKAB_TAK_DIKENAL = "9999"
IDKAB_POLA_SALAH = "18"  # bukan 4 digit


@pytest.mark.integration
async def test_geo_kab_dikenal_kembalikan_feature_collection_tergzip(
    dir_data_lengkap: Path, klien: httpx.AsyncClient
) -> None:
    respons = await klien.get(f"/api/geo/desa/{IDKAB_SATU}")

    assert respons.status_code == 200
    assert respons.headers.get("content-encoding") == "gzip"
    assert "content-disposition" not in respons.headers

    body = respons.json()
    assert body["type"] == "FeatureCollection"
    assert len(body["features"]) == 3
    for fitur in body["features"]:
        assert set(fitur["properties"].keys()) == {"iddesa", "nmdesa"}


@pytest.mark.integration
async def test_geo_idkab_tak_dikenal_kembalikan_404_amplop_wilayah_tidak_ada(
    dir_data_lengkap: Path, klien: httpx.AsyncClient
) -> None:
    respons = await klien.get(f"/api/geo/desa/{IDKAB_TAK_DIKENAL}")

    assert respons.status_code == 404
    body = respons.json()
    assert body["sukses"] is False
    assert body["galat"]["kode"] == "WILAYAH_TIDAK_ADA"


@pytest.mark.integration
async def test_geo_kab_dikenal_tapi_berkas_tak_ada_kembalikan_404_tidak_ditemukan(
    dir_data_lengkap: Path, klien: httpx.AsyncClient
) -> None:
    """Kab 1802 dikenal di wilayah.json tapi TIDAK punya geo/1802.geojson.gz."""
    respons = await klien.get(f"/api/geo/desa/{IDKAB_DUA}")

    assert respons.status_code == 404
    body = respons.json()
    assert body["sukses"] is False
    assert body["galat"]["kode"] == "TIDAK_DITEMUKAN"


@pytest.mark.integration
async def test_geo_idkab_pola_salah_kembalikan_422(
    dir_data_lengkap: Path, klien: httpx.AsyncClient
) -> None:
    respons = await klien.get(f"/api/geo/desa/{IDKAB_POLA_SALAH}")

    assert respons.status_code == 422
    assert respons.json()["galat"]["kode"] == "PARAMETER_TIDAK_VALID"
