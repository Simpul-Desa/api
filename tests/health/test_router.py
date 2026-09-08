"""Uji integrasi untuk endpoint GET /health (src/health/router.py)."""

import warnings
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI

from src.config import ambil_pengaturan

pytestmark = pytest.mark.anyio


@pytest.fixture
def dir_data_kosong(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """DIR_DATA menunjuk ke direktori sementara kosong (tanpa manifest.json)."""
    monkeypatch.setenv("DIR_DATA", str(tmp_path))
    ambil_pengaturan.cache_clear()

    yield tmp_path

    ambil_pengaturan.cache_clear()


@pytest.mark.integration
async def test_health_tanpa_manifest_kembalikan_none(
    dir_data_kosong: Path, klien: httpx.AsyncClient
) -> None:
    respons = await klien.get("/health")

    assert respons.status_code == 200
    assert respons.json() == {
        "sukses": True,
        "data": {"status": "hidup", "versi_data": None, "tanggal_data": None},
        "galat": None,
        "meta": None,
    }


@pytest.mark.integration
async def test_health_dengan_manifest_kembalikan_versi_dan_tanggal(
    dir_data_manifest: Path, klien: httpx.AsyncClient
) -> None:
    respons = await klien.get("/health")

    assert respons.status_code == 200
    body = respons.json()
    assert set(body.keys()) == {"sukses", "data", "galat", "meta"}
    assert body["sukses"] is True
    assert body["galat"] is None
    assert body["meta"] is None
    assert body["data"]["status"] == "hidup"
    assert body["data"]["versi_data"] == "uji123"
    assert body["data"]["tanggal_data"] == "2026-09-07"


@pytest.mark.integration
async def test_head_health_diterima(
    dir_data_manifest: Path, klien: httpx.AsyncClient
) -> None:
    """Monitor uptime memakai HEAD; rute harus menjawab 200, bukan 405.

    Badan respons TIDAK diperiksa di sini: pemotongannya dilakukan server
    HTTP (h11 di balik uvicorn), sedangkan uji ini memanggil aplikasi lewat
    `ASGITransport` yang tidak memotong apa pun.
    """
    respons = await klien.head("/health")

    assert respons.status_code == 200
    assert respons.headers["content-type"] == "application/json"


@pytest.mark.unit
def test_head_tidak_menyentuh_kontrak_openapi(aplikasi: FastAPI) -> None:
    """`HEAD /health` tidak boleh terbit ke `/openapi.json`.

    `unique_id` sebuah rute dihitung per-rute, bukan per-metode, sehingga
    satu rute dua metode membuat `get` dan `head` berbagi `operationId` yang
    sama — FastAPI memperingatkannya dan generator klien yang membaca
    kontrak publik ikut rusak. HEAD karena itu didaftarkan sebagai rute
    sendiri di luar skema.
    """
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        spec = aplikasi.openapi()

    assert sorted(spec["paths"]["/health"]) == ["get"]
