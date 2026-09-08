"""Uji integrasi untuk rute Citra Potensi Desa (`src/citra_potensi/router.py`, Tugas 7)."""

import json
from dataclasses import replace
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI

from src.citra_potensi.service import baca_sel_citra
from tests.conftest import IDPROV, TARGET_CITRA, PembuatKlien

pytestmark = pytest.mark.anyio


@pytest.mark.integration
async def test_daftar_sel_sukses_amplop_dan_meta_total(
    dir_data_lengkap: Path, klien: httpx.AsyncClient
) -> None:
    respons = await klien.get("/api/model/citra-potensi")

    assert respons.status_code == 200
    body = respons.json()
    assert body["sukses"] is True
    assert body["meta"]["total"] == 1
    assert len(body["data"]) == 1
    assert body["data"][0]["target"] == TARGET_CITRA
    assert body["data"][0]["prov"] == IDPROV


@pytest.mark.integration
async def test_daftar_sel_filter_prov_tidak_cocok_kembalikan_kosong(
    dir_data_lengkap: Path, klien: httpx.AsyncClient
) -> None:
    respons = await klien.get("/api/model/citra-potensi", params={"prov": "99"})

    assert respons.status_code == 200
    body = respons.json()
    assert body["data"] == []
    assert body["meta"]["total"] == 0


@pytest.mark.integration
async def test_daftar_sel_filter_target_persis_cocok(
    dir_data_lengkap: Path, klien: httpx.AsyncClient
) -> None:
    respons = await klien.get(
        "/api/model/citra-potensi", params={"prov": IDPROV, "target": TARGET_CITRA}
    )

    assert respons.status_code == 200
    body = respons.json()
    assert body["meta"]["total"] == 1
    assert body["data"][0]["target"] == TARGET_CITRA


@pytest.mark.integration
async def test_daftar_sel_prov_bentuk_salah_kembalikan_422(
    dir_data_lengkap: Path, klien: httpx.AsyncClient
) -> None:
    respons = await klien.get("/api/model/citra-potensi", params={"prov": "1"})

    assert respons.status_code == 422
    assert respons.json()["galat"]["kode"] == "PARAMETER_TIDAK_VALID"


@pytest.mark.integration
async def test_detail_sel_sukses_memuat_skor_dan_format_skor_tanpa_model_validasi(
    dir_data_lengkap: Path, klien: httpx.AsyncClient
) -> None:
    respons = await klien.get(
        "/api/model/citra-potensi/sel", params={"prov": IDPROV, "target": TARGET_CITRA}
    )

    assert respons.status_code == 200
    body = respons.json()["data"]
    assert "skor" in body
    assert "format_skor" in body
    assert body["target"] == TARGET_CITRA
    assert "model" not in body
    assert "validasi" not in body
    assert "meta" not in body


@pytest.mark.integration
async def test_detail_sel_kombinasi_tak_ada_kembalikan_404(
    dir_data_lengkap: Path, klien: httpx.AsyncClient
) -> None:
    respons = await klien.get(
        "/api/model/citra-potensi/sel", params={"prov": "99", "target": "tak-ada"}
    )

    assert respons.status_code == 404
    assert respons.json()["galat"]["kode"] == "TIDAK_DITEMUKAN"


@pytest.mark.integration
async def test_detail_sel_target_hilang_kembalikan_422(
    dir_data_lengkap: Path, klien: httpx.AsyncClient
) -> None:
    respons = await klien.get("/api/model/citra-potensi/sel", params={"prov": IDPROV})

    assert respons.status_code == 422
    assert respons.json()["galat"]["kode"] == "PARAMETER_TIDAK_VALID"


@pytest.mark.integration
async def test_detail_sel_prov_bentuk_salah_kembalikan_422(
    dir_data_lengkap: Path, klien: httpx.AsyncClient
) -> None:
    respons = await klien.get(
        "/api/model/citra-potensi/sel", params={"prov": "1", "target": TARGET_CITRA}
    )

    assert respons.status_code == 422
    assert respons.json()["galat"]["kode"] == "PARAMETER_TIDAK_VALID"


@pytest.mark.integration
async def test_daftar_sel_entri_tanpa_prov_tidak_menjatuhkan_daftar(
    dir_data_lengkap: Path, aplikasi: FastAPI, buat_klien: PembuatKlien
) -> None:
    """Satu entri sel cacat cukup TIDAK cocok filter — daftar tetap tersaji."""
    klien = await buat_klien(aplikasi, lifespan=True)
    indeks = aplikasi.state.simpanan.citra_indeks
    aplikasi.state.simpanan = replace(
        aplikasi.state.simpanan,
        citra_indeks={**indeks, "sel": [*indeks["sel"], {"berkas": "rusak.json"}]},
    )

    respons = await klien.get(f"/api/model/citra-potensi?prov={IDPROV}")

    assert respons.status_code == 200
    assert respons.json()["meta"]["total"] == 1


@pytest.mark.integration
async def test_detail_sel_berkas_tanpa_skor_kembalikan_503(
    dir_data_lengkap: Path, aplikasi: FastAPI, buat_klien: PembuatKlien
) -> None:
    """Berkas produksi tanpa `skor` bukan berkas skor sel: 503, bukan 500."""
    klien = await buat_klien(aplikasi, lifespan=True)
    berkas = aplikasi.state.simpanan.citra_indeks["sel"][0]["berkas"]
    path = dir_data_lengkap / "citra-potensi" / berkas
    path.write_text(json.dumps({"meta": {}}), encoding="utf-8")
    baca_sel_citra.cache_clear()

    respons = await klien.get(
        f"/api/model/citra-potensi/sel?prov={IDPROV}&target={TARGET_CITRA}"
    )

    assert respons.status_code == 503
    assert respons.json()["galat"]["kode"] == "DATA_BELUM_SIAP"
