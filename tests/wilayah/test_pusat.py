"""Uji integrasi untuk GET /api/wilayah/pusat (Blok A fase-1-fondasi app/)."""

import json
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI
from pydantic import ValidationError

from src.wilayah.schemas import PusatKabupaten, PusatProvinsi
from tests.conftest import IDKAB_DUA, IDKAB_SATU, IDPROV, PembuatKlien

pytestmark = pytest.mark.anyio


@pytest.mark.integration
async def test_pusat_wilayah_sukses_amplop_tanpa_meta(
    dir_data_lengkap: Path, klien: httpx.AsyncClient
) -> None:
    respons = await klien.get("/api/wilayah/pusat")

    assert respons.status_code == 200
    body = respons.json()
    assert body["sukses"] is True
    assert body["meta"] is None
    assert body["data"] == {
        "provinsi": [
            {
                "idprov": IDPROV,
                "nama": "Lampung",
                "pusat": pytest.approx([104.625, -4.825]),
                "n_desa": 6,
                "n_kabupaten": 2,
            }
        ],
        "kabupaten": [
            {
                "idkab": IDKAB_SATU,
                "nmkab": "KAB SATU",
                "idprov": IDPROV,
                "pusat": [104.05, -5.05],
                "n_desa": 3,
            },
            {
                "idkab": IDKAB_DUA,
                "nmkab": "KAB DUA",
                "idprov": IDPROV,
                "pusat": [105.2, -4.6],
                "n_desa": 3,
            },
        ],
    }


@pytest.mark.integration
async def test_pusat_wilayah_membawa_etag(
    dir_data_lengkap: Path, klien: httpx.AsyncClient
) -> None:
    respons = await klien.get("/api/wilayah/pusat")

    assert respons.status_code == 200
    assert respons.headers["etag"] == '"uji123"'


@pytest.mark.integration
async def test_pusat_wilayah_tanpa_data_kembalikan_503(
    dir_data_manifest: Path, klien: httpx.AsyncClient
) -> None:
    """`dir_data_manifest` cuma punya manifest.json — `pusat_wilayah.json` hilang."""
    respons = await klien.get("/api/wilayah/pusat")

    assert respons.status_code == 503
    body = respons.json()
    assert body["sukses"] is False
    assert body["galat"]["kode"] == "DATA_BELUM_SIAP"


@pytest.mark.integration
@pytest.mark.parametrize(
    "pusat_rusak",
    [{"kabupaten": []}, {}],
    ids=["daftar_kabupaten_kosong", "kunci_kabupaten_absen"],
)
async def test_pusat_wilayah_artefak_kabupaten_kosong_kembalikan_503(
    dir_data_lengkap: Path,
    aplikasi: FastAPI,
    buat_klien: PembuatKlien,
    pusat_rusak: dict[str, object],
) -> None:
    """`pusat_wilayah.json` ADA tapi kabupatennya kosong/kuncinya absen =
    artefak bukan yang diklaimnya. Sebelum perbaikan, `_hitung_pusat_wilayah`
    (`src/datastore.py`) menjawab ini 200 dengan
    `{"provinsi": [], "kabupaten": []}`; sekarang 503 DATA_BELUM_SIAP lewat
    `wajib()`, pola sama seperti `test_wilayah_tanpa_kunci_wajib_kembalikan_503`
    di `tests/wilayah/test_router.py`."""
    (dir_data_lengkap / "pusat_wilayah.json").write_text(
        json.dumps(pusat_rusak), encoding="utf-8"
    )
    klien = await buat_klien(aplikasi, lifespan=True)

    respons = await klien.get("/api/wilayah/pusat")

    assert respons.status_code == 503
    assert respons.json()["galat"]["kode"] == "DATA_BELUM_SIAP"


@pytest.mark.unit
def test_pusat_kabupaten_pusat_bukan_pasangan_lng_lat_ditolak() -> None:
    """`pusat` OpenAPI memancarkan arity [lng, lat] — list 1 elemen ditolak
    validasi, bukan cuma dokumentasi kosmetik (typegen `app/`)."""
    with pytest.raises(ValidationError):
        PusatKabupaten(
            idkab=IDKAB_SATU,
            nmkab="KAB SATU",
            idprov=IDPROV,
            pusat=[104.05],
            n_desa=1,
        )


@pytest.mark.unit
def test_pusat_provinsi_pusat_bukan_pasangan_lng_lat_ditolak() -> None:
    """Sisi lain arity: 3 elemen (bukan cuma kurang dari 2) juga ditolak."""
    with pytest.raises(ValidationError):
        PusatProvinsi(
            idprov=IDPROV,
            nama="Lampung",
            pusat=[1.0, 2.0, 3.0],
            n_desa=1,
            n_kabupaten=1,
        )
