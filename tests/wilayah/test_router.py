"""Uji integrasi untuk rute wilayah (`src/wilayah/router.py`, Tugas 5)."""

from dataclasses import replace
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI

from src.exceptions import DATA_BELUM_SIAP, GalatAPI
from src.wilayah.service import kab_dikenal, prov_dikenal
from tests.conftest import (
    D1,
    D2,
    D3,
    IDKAB_DUA,
    IDKAB_SATU,
    IDPROV,
    PembuatKlien,
)

pytestmark = pytest.mark.anyio

IDKAB_TAK_DIKENAL = "9999"
IDKAB_POLA_SALAH = "180"  # 3 digit
IDPROV_TAK_DIKENAL = "99"
IDPROV_POLA_SALAH = "1"  # 1 digit


@pytest.mark.integration
async def test_daftar_provinsi_sukses_amplop_dan_meta(
    dir_data_lengkap: Path, klien: httpx.AsyncClient
) -> None:
    respons = await klien.get("/api/wilayah/provinsi")

    assert respons.status_code == 200
    body = respons.json()
    assert body["sukses"] is True
    assert body["data"] == [{"idprov": IDPROV, "nama": "Lampung"}]
    assert body["meta"] == {"total": 1, "hal": 1, "batas": 50, "parameter": None}


@pytest.mark.integration
async def test_daftar_provinsi_tanpa_data_kembalikan_503(
    dir_data_manifest: Path, klien: httpx.AsyncClient
) -> None:
    """`dir_data_manifest` cuma punya manifest.json — `wilayah.json` hilang."""
    respons = await klien.get("/api/wilayah/provinsi")

    assert respons.status_code == 503
    body = respons.json()
    assert body["sukses"] is False
    assert body["galat"]["kode"] == "DATA_BELUM_SIAP"


@pytest.mark.integration
async def test_ringkasan_wilayah_sukses_tanpa_meta(
    dir_data_lengkap: Path, klien: httpx.AsyncClient
) -> None:
    respons = await klien.get("/api/wilayah/ringkasan")

    assert respons.status_code == 200
    body = respons.json()
    assert body["sukses"] is True
    assert body["meta"] is None
    assert body["data"] == {
        "n_provinsi": 1,
        "n_kabupaten": 2,
        "n_desa": 6,
        "per_provinsi": [
            {"idprov": IDPROV, "nama": "Lampung", "n_kabupaten": 2, "n_desa": 6}
        ],
    }


@pytest.mark.integration
async def test_daftar_kabupaten_tanpa_filter(
    dir_data_lengkap: Path, klien: httpx.AsyncClient
) -> None:
    respons = await klien.get("/api/wilayah/kabupaten")

    assert respons.status_code == 200
    body = respons.json()
    assert body["meta"]["total"] == 2
    idkab_terlihat = {baris["idkab"] for baris in body["data"]}
    assert idkab_terlihat == {IDKAB_SATU, IDKAB_DUA}


@pytest.mark.integration
async def test_daftar_kabupaten_filter_prov_valid(
    dir_data_lengkap: Path, klien: httpx.AsyncClient
) -> None:
    respons = await klien.get("/api/wilayah/kabupaten", params={"prov": IDPROV})

    assert respons.status_code == 200
    assert respons.json()["meta"]["total"] == 2


@pytest.mark.integration
async def test_daftar_kabupaten_prov_bentuk_salah_kembalikan_422(
    dir_data_lengkap: Path, klien: httpx.AsyncClient
) -> None:
    respons = await klien.get(
        "/api/wilayah/kabupaten", params={"prov": IDPROV_POLA_SALAH}
    )

    assert respons.status_code == 422
    assert respons.json()["galat"]["kode"] == "PARAMETER_TIDAK_VALID"


@pytest.mark.integration
async def test_daftar_kabupaten_prov_tak_dikenal_kembalikan_404(
    dir_data_lengkap: Path, klien: httpx.AsyncClient
) -> None:
    respons = await klien.get(
        "/api/wilayah/kabupaten", params={"prov": IDPROV_TAK_DIKENAL}
    )

    assert respons.status_code == 404
    body = respons.json()
    assert body["sukses"] is False
    assert body["galat"]["kode"] == "WILAYAH_TIDAK_ADA"


@pytest.mark.integration
async def test_daftar_desa_tanpa_kab_kembalikan_422(
    dir_data_lengkap: Path, klien: httpx.AsyncClient
) -> None:
    """`kab` wajib — permintaan tanpa `kab` gagal validasi."""
    respons = await klien.get("/api/wilayah/desa")

    assert respons.status_code == 422
    assert respons.json()["galat"]["kode"] == "PARAMETER_TIDAK_VALID"


@pytest.mark.integration
async def test_daftar_desa_sukses(
    dir_data_lengkap: Path, klien: httpx.AsyncClient
) -> None:
    respons = await klien.get("/api/wilayah/desa", params={"kab": IDKAB_SATU})

    assert respons.status_code == 200
    body = respons.json()
    assert body["meta"] == {"total": 3, "hal": 1, "batas": 50, "parameter": None}
    assert body["data"] == [
        {"iddesa": D1, "nmdesa": "DESA A1", "nmkec": "KEC ALFA"},
        {"iddesa": D2, "nmdesa": "DESA A2", "nmkec": "KEC ALFA"},
        {"iddesa": D3, "nmdesa": "DESA A3", "nmkec": "KEC BETA"},
    ]


@pytest.mark.integration
async def test_daftar_desa_kab_bentuk_salah_kembalikan_422(
    dir_data_lengkap: Path, klien: httpx.AsyncClient
) -> None:
    respons = await klien.get("/api/wilayah/desa", params={"kab": IDKAB_POLA_SALAH})

    assert respons.status_code == 422
    assert respons.json()["galat"]["kode"] == "PARAMETER_TIDAK_VALID"


@pytest.mark.integration
async def test_daftar_desa_kab_tak_dikenal_kembalikan_404(
    dir_data_lengkap: Path, klien: httpx.AsyncClient
) -> None:
    respons = await klien.get("/api/wilayah/desa", params={"kab": IDKAB_TAK_DIKENAL})

    assert respons.status_code == 404
    body = respons.json()
    assert body["sukses"] is False
    assert body["galat"]["kode"] == "WILAYAH_TIDAK_ADA"


@pytest.mark.integration
@pytest.mark.parametrize(
    ("wilayah_rusak", "path"),
    [
        ({"kabupaten": []}, "/api/wilayah/provinsi"),
        ({"provinsi": []}, "/api/wilayah/kabupaten"),
    ],
)
async def test_wilayah_tanpa_kunci_wajib_kembalikan_503(
    dir_data_lengkap: Path,
    aplikasi: FastAPI,
    buat_klien: PembuatKlien,
    wilayah_rusak: dict[str, object],
    path: str,
) -> None:
    """`wilayah.json` ada tapi kehilangan kunci tingkat atas = artefak bukan
    yang diklaimnya. Kontrak folder ini menjawab artefak cacat dengan 503
    DATA_BELUM_SIAP; KeyError yang lolos jadi 500 GALAT_SERVER menyesatkan
    pemanggil bahwa servernya yang rusak, bukan build datanya."""
    klien = await buat_klien(aplikasi, lifespan=True)
    aplikasi.state.simpanan = replace(aplikasi.state.simpanan, wilayah=wilayah_rusak)

    respons = await klien.get(path)

    assert respons.status_code == 503
    assert respons.json()["galat"]["kode"] == "DATA_BELUM_SIAP"


@pytest.mark.unit
@pytest.mark.parametrize(
    ("penjaga", "kode"),
    [(prov_dikenal, IDPROV), (kab_dikenal, IDKAB_SATU)],
)
def test_penjaga_kode_wilayah_tanpa_daftar_kembalikan_503(
    penjaga: object, kode: str
) -> None:
    """`peta_peran` dan `geo` memanggil penjaga ini tanpa pernah menyentuh
    daftarnya sendiri, jadi penjaganya harus punya guard sendiri."""
    with pytest.raises(GalatAPI) as info:
        penjaga({}, kode)  # type: ignore[operator]

    assert info.value.status == 503
    assert info.value.kode == DATA_BELUM_SIAP
