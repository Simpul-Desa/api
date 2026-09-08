"""Uji integrasi untuk rute peta peran (`src/peta_peran/router.py`, Tugas 6)."""

import logging
from dataclasses import replace
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI

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

IDDESA_POLA_SALAH = "180104000"  # 9 digit
IDDESA_TAK_DIKENAL = "1801049999"  # 10 digit, tak ada di peta_peran
IDKAB_TAK_DIKENAL = "9999"
IDKAB_POLA_SALAH = "180"  # 3 digit
IDPROV_TAK_DIKENAL = "99"

_KOLOM_RINGKAS = {
    "iddesa",
    "nmdesa",
    "nmkec",
    "idkab",
    "nmkab",
    "idprov",
    "zona",
    "keyakinan",
    "desil_sp",
    "desil_sk",
    "potensi_dominan",
    "sumber_dominan",
}


# --- GET /api/model/peta-peran (daftar ringkas) -----------------------------


@pytest.mark.integration
async def test_daftar_peta_peran_sukses_dan_meta(
    dir_data_lengkap: Path, klien: httpx.AsyncClient
) -> None:
    respons = await klien.get("/api/model/peta-peran")

    assert respons.status_code == 200
    body = respons.json()
    assert body["sukses"] is True
    assert body["meta"]["total"] == 6
    assert len(body["data"]) == 6


@pytest.mark.integration
async def test_daftar_peta_peran_baris_ringkas_tidak_memuat_kolom_di_luar_proyeksi(
    dir_data_lengkap: Path, klien: httpx.AsyncClient
) -> None:
    """Baris daftar hanya 12 kolom proyeksi — kolom mutu lain (mis.
    `alasan_belum_terpetakan`) tidak ikut. Bandingkan dengan rute detail."""
    respons = await klien.get("/api/model/peta-peran")

    assert respons.status_code == 200
    for baris in respons.json()["data"]:
        assert set(baris.keys()) == _KOLOM_RINGKAS


@pytest.mark.integration
async def test_daftar_peta_peran_filter_zona_belum_terpetakan(
    dir_data_lengkap: Path, klien: httpx.AsyncClient
) -> None:
    respons = await klien.get(
        "/api/model/peta-peran", params={"zona": "Belum Terpetakan"}
    )

    assert respons.status_code == 200
    body = respons.json()
    assert body["meta"]["total"] == 1
    assert body["data"] == [
        {
            "iddesa": D3,
            "nmdesa": "DESA A3",
            "nmkec": "KEC BETA",
            "idkab": IDKAB_SATU,
            "nmkab": "KAB SATU",
            "idprov": IDPROV,
            "zona": "Belum Terpetakan",
            "keyakinan": "",
            "desil_sp": 0,
            "desil_sk": 5,
            "potensi_dominan": "",
            "sumber_dominan": "",
        }
    ]


@pytest.mark.integration
async def test_daftar_peta_peran_zona_tak_dikenal_kembalikan_422(
    dir_data_lengkap: Path, klien: httpx.AsyncClient
) -> None:
    respons = await klien.get("/api/model/peta-peran", params={"zona": "Zona Salah"})

    assert respons.status_code == 422
    assert respons.json()["galat"]["kode"] == "PARAMETER_TIDAK_VALID"


@pytest.mark.integration
async def test_daftar_peta_peran_filter_kab_valid(
    dir_data_lengkap: Path, klien: httpx.AsyncClient
) -> None:
    respons = await klien.get("/api/model/peta-peran", params={"kab": IDKAB_SATU})

    assert respons.status_code == 200
    assert respons.json()["meta"]["total"] == 3


@pytest.mark.integration
async def test_daftar_peta_peran_kab_bentuk_salah_kembalikan_422(
    dir_data_lengkap: Path, klien: httpx.AsyncClient
) -> None:
    respons = await klien.get("/api/model/peta-peran", params={"kab": IDKAB_POLA_SALAH})

    assert respons.status_code == 422
    assert respons.json()["galat"]["kode"] == "PARAMETER_TIDAK_VALID"


@pytest.mark.integration
async def test_daftar_peta_peran_prov_tak_dikenal_kembalikan_404(
    dir_data_lengkap: Path, klien: httpx.AsyncClient
) -> None:
    respons = await klien.get(
        "/api/model/peta-peran", params={"prov": IDPROV_TAK_DIKENAL}
    )

    assert respons.status_code == 404
    assert respons.json()["galat"]["kode"] == "WILAYAH_TIDAK_ADA"


@pytest.mark.integration
async def test_daftar_peta_peran_kab_tak_dikenal_kembalikan_404(
    dir_data_lengkap: Path, klien: httpx.AsyncClient
) -> None:
    respons = await klien.get(
        "/api/model/peta-peran", params={"kab": IDKAB_TAK_DIKENAL}
    )

    assert respons.status_code == 404
    assert respons.json()["galat"]["kode"] == "WILAYAH_TIDAK_ADA"


@pytest.mark.integration
async def test_daftar_peta_peran_tanpa_data_kembalikan_503(
    dir_data_manifest: Path, klien: httpx.AsyncClient
) -> None:
    respons = await klien.get("/api/model/peta-peran")

    assert respons.status_code == 503
    assert respons.json()["galat"]["kode"] == "DATA_BELUM_SIAP"


# --- Batas paginasi (hal/batas) ----------------------------------------------


@pytest.mark.integration
async def test_daftar_peta_peran_hal_nol_kembalikan_422(
    dir_data_lengkap: Path, klien: httpx.AsyncClient
) -> None:
    respons = await klien.get("/api/model/peta-peran", params={"hal": 0})

    assert respons.status_code == 422
    assert respons.json()["galat"]["kode"] == "PARAMETER_TIDAK_VALID"


@pytest.mark.integration
async def test_daftar_peta_peran_batas_nol_kembalikan_422(
    dir_data_lengkap: Path, klien: httpx.AsyncClient
) -> None:
    respons = await klien.get("/api/model/peta-peran", params={"batas": 0})

    assert respons.status_code == 422
    assert respons.json()["galat"]["kode"] == "PARAMETER_TIDAK_VALID"


@pytest.mark.integration
async def test_daftar_peta_peran_batas_melebihi_maksimum_kembalikan_422(
    dir_data_lengkap: Path, klien: httpx.AsyncClient
) -> None:
    respons = await klien.get("/api/model/peta-peran", params={"batas": 501})

    assert respons.status_code == 422
    assert respons.json()["galat"]["kode"] == "PARAMETER_TIDAK_VALID"


@pytest.mark.integration
async def test_daftar_peta_peran_batas_tepat_maksimum_bukan_422(
    dir_data_lengkap: Path, klien: httpx.AsyncClient
) -> None:
    """`batas=500` persis `BATAS_MAKS` — batas atas sah, bukan pelanggaran."""
    respons = await klien.get("/api/model/peta-peran", params={"batas": 500})

    assert respons.status_code == 200


# --- GET /api/model/peta-peran/ringkasan ------------------------------------


@pytest.mark.integration
async def test_ringkasan_peta_peran_tanpa_kab_kembalikan_daftar_bukan_422_atau_404(
    dir_data_lengkap: Path, klien: httpx.AsyncClient
) -> None:
    """`ringkasan` harus dicocokkan sebelum rute `{iddesa}` pada router yang
    sama — permintaan ini TIDAK boleh jatuh ke 422 (pola iddesa) atau 404."""
    respons = await klien.get("/api/model/peta-peran/ringkasan")

    assert respons.status_code == 200
    body = respons.json()
    assert body["sukses"] is True
    assert isinstance(body["data"], list)
    assert body["meta"]["total"] == 2
    idkab_terlihat = {baris["idkab"] for baris in body["data"]}
    assert idkab_terlihat == {IDKAB_SATU, IDKAB_DUA}


@pytest.mark.integration
async def test_ringkasan_peta_peran_dengan_kab_kembalikan_satu_objek(
    dir_data_lengkap: Path, klien: httpx.AsyncClient
) -> None:
    respons = await klien.get(
        "/api/model/peta-peran/ringkasan", params={"kab": IDKAB_SATU}
    )

    assert respons.status_code == 200
    body = respons.json()
    assert body["meta"] is None
    assert body["data"]["idkab"] == IDKAB_SATU
    assert body["data"]["nmkab"] == "KAB SATU"
    assert body["data"]["n_keyakinan_rendah"] == 1


@pytest.mark.integration
async def test_ringkasan_peta_peran_kab_tak_dikenal_kembalikan_404(
    dir_data_lengkap: Path, klien: httpx.AsyncClient
) -> None:
    respons = await klien.get(
        "/api/model/peta-peran/ringkasan", params={"kab": IDKAB_TAK_DIKENAL}
    )

    assert respons.status_code == 404
    assert respons.json()["galat"]["kode"] == "WILAYAH_TIDAK_ADA"


# --- GET /api/model/peta-peran/{iddesa} (detail) ----------------------------


@pytest.mark.integration
async def test_detail_peta_peran_iddesa_pola_salah_kembalikan_422(
    dir_data_lengkap: Path, klien: httpx.AsyncClient
) -> None:
    respons = await klien.get(f"/api/model/peta-peran/{IDDESA_POLA_SALAH}")

    assert respons.status_code == 422
    assert respons.json()["galat"]["kode"] == "PARAMETER_TIDAK_VALID"


@pytest.mark.integration
async def test_detail_peta_peran_iddesa_tak_dikenal_kembalikan_404(
    dir_data_lengkap: Path, klien: httpx.AsyncClient
) -> None:
    respons = await klien.get(f"/api/model/peta-peran/{IDDESA_TAK_DIKENAL}")

    assert respons.status_code == 404
    assert respons.json()["galat"]["kode"] == "DESA_TIDAK_ADA"


@pytest.mark.integration
async def test_detail_peta_peran_memuat_kolom_penjaga_mutu(
    dir_data_lengkap: Path, klien: httpx.AsyncClient
) -> None:
    """PRD §8: `keyakinan`, `sumber_dominan`, `alasan_belum_terpetakan` harus
    ada di respons detail — baris D2 punya `keyakinan: "rendah"`."""
    respons = await klien.get(f"/api/model/peta-peran/{D2}")

    assert respons.status_code == 200
    data = respons.json()["data"]
    assert data["keyakinan"] == "rendah"
    assert data["sumber_dominan"] == "heuristik-belum-teruji"
    assert "alasan_belum_terpetakan" in data


@pytest.mark.integration
async def test_detail_peta_peran_belum_terpetakan_memuat_alasan(
    dir_data_lengkap: Path, klien: httpx.AsyncClient
) -> None:
    respons = await klien.get(f"/api/model/peta-peran/{D3}")

    assert respons.status_code == 200
    data = respons.json()["data"]
    assert data["zona"] == "Belum Terpetakan"
    assert data["alasan_belum_terpetakan"] == "tanpa geometri; tanpa ST2023"


@pytest.mark.integration
async def test_detail_peta_peran_kartu_sama_dengan_baris_sukses_sederhana(
    dir_data_lengkap: Path, klien: httpx.AsyncClient
) -> None:
    respons = await klien.get(f"/api/model/peta-peran/{D1}")

    assert respons.status_code == 200
    body = respons.json()
    assert body["meta"] is None
    assert body["data"]["iddesa"] == D1


@pytest.mark.integration
async def test_baris_tanpa_kolom_ringkas_dilewati_bukan_500(
    dir_data_lengkap: Path,
    aplikasi: FastAPI,
    buat_klien: PembuatKlien,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Baris tanpa kolom mutu DILEWATI + dicatat, bukan diberi `None` palsu.

    PRD §8 melarang kolom mutu hilang dari respons; `sumber_dominan: None`
    yang dikarang kode tidak bisa dibedakan pembaca dari nilai kosong yang
    sah, jadi barisnya dibuang dan selisih cacahnya tercatat di log.
    """
    klien = await buat_klien(aplikasi, lifespan=True)
    peta_peran = aplikasi.state.simpanan.peta_peran or []
    n_semula = len(peta_peran)
    rusak = {k: v for k, v in peta_peran[0].items() if k != "sumber_dominan"}
    rusak["iddesa"] = "1801049997"
    aplikasi.state.simpanan = replace(
        aplikasi.state.simpanan, peta_peran=[*peta_peran, rusak]
    )

    with caplog.at_level(logging.WARNING):
        respons = await klien.get("/api/model/peta-peran")

    assert respons.status_code == 200
    assert respons.json()["meta"]["total"] == n_semula
    assert "1801049997" in caplog.text
