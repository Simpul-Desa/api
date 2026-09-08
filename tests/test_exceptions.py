"""Uji unit untuk penanganan galat (error handler) global FastAPI."""

import logging

import pytest
from fastapi import FastAPI
from starlette.exceptions import HTTPException as StarletteHTTPException

from src.exceptions import (
    AKSI_DITOLAK,
    BERITA_TIDAK_ADA,
    DESA_TIDAK_ADA,
    GALAT_SERVER,
    KONFLIK,
    METODE_TIDAK_DIIZINKAN,
    PARAMETER_TIDAK_VALID,
    PEKERJAAN_BERJALAN,
    PENGGUNA_TIDAK_ADA,
    TIDAK_DITEMUKAN,
    GalatAPI,
    daftarkan_handler,
)
from tests.conftest import PembuatKlien

pytestmark = pytest.mark.anyio


def buat_app() -> FastAPI:
    app = FastAPI()
    daftarkan_handler(app)

    @app.get("/desa-tidak-ada")
    async def rute_desa_tidak_ada() -> None:
        raise GalatAPI(kode=DESA_TIDAK_ADA, pesan="desa tidak dikenal", status=404)

    @app.get("/angka/{angka}")
    async def rute_angka(angka: int) -> dict[str, int]:
        return {"angka": angka}

    @app.get("/rusak")
    async def rute_rusak() -> None:
        raise RuntimeError("rahasia-internal")

    @app.get("/http/{status}")
    async def rute_http(status: int) -> None:
        raise StarletteHTTPException(status_code=status, detail="galat klien uji")

    return app


@pytest.mark.unit
async def test_galat_api_menghasilkan_envelope_persis(buat_klien: PembuatKlien) -> None:
    client = await buat_klien(buat_app())

    respons = await client.get("/desa-tidak-ada")

    assert respons.status_code == 404
    assert respons.json() == {
        "sukses": False,
        "data": None,
        "galat": {"kode": DESA_TIDAK_ADA, "pesan": "desa tidak dikenal"},
        "meta": None,
    }


@pytest.mark.unit
async def test_parameter_tidak_valid_saat_path_param_salah_tipe(
    buat_klien: PembuatKlien,
) -> None:
    client = await buat_klien(buat_app())

    respons = await client.get("/angka/abc")

    assert respons.status_code == 422
    body = respons.json()
    assert body["sukses"] is False
    assert body["data"] is None
    assert body["galat"]["kode"] == PARAMETER_TIDAK_VALID
    assert isinstance(body["galat"]["pesan"], str)
    assert body["galat"]["pesan"] != ""
    assert body["meta"] is None


@pytest.mark.unit
async def test_path_tidak_dikenal_menghasilkan_tidak_ditemukan(
    buat_klien: PembuatKlien,
) -> None:
    client = await buat_klien(buat_app())

    respons = await client.get("/path/yang/tidak/ada")

    assert respons.status_code == 404
    body = respons.json()
    assert body["sukses"] is False
    assert body["data"] is None
    assert body["galat"]["kode"] == TIDAK_DITEMUKAN
    assert body["meta"] is None


@pytest.mark.unit
async def test_exception_tak_terduga_tidak_bocorkan_detail(
    caplog: pytest.LogCaptureFixture, buat_klien: PembuatKlien
) -> None:
    client = await buat_klien(buat_app(), lempar_galat_app=False)

    with caplog.at_level(logging.ERROR):
        respons = await client.get("/rusak")

    assert respons.status_code == 500
    body = respons.json()
    assert body["sukses"] is False
    assert body["data"] is None
    assert body["galat"]["kode"] == GALAT_SERVER
    assert "rahasia-internal" not in respons.text
    assert body["meta"] is None

    assert any(
        record.levelno >= logging.ERROR and record.exc_info is not None
        for record in caplog.records
    )


@pytest.mark.unit
async def test_metode_salah_menghasilkan_metode_tidak_diizinkan(
    buat_klien: PembuatKlien,
) -> None:
    """405 adalah galat klien: kodenya bukan GALAT_SERVER."""
    client = await buat_klien(buat_app())

    respons = await client.post("/desa-tidak-ada")

    assert respons.status_code == 405
    body = respons.json()
    assert body["sukses"] is False
    assert body["data"] is None
    assert body["galat"]["kode"] == METODE_TIDAK_DIIZINKAN
    assert body["meta"] is None


@pytest.mark.unit
@pytest.mark.parametrize(
    ("status", "kode_diharapkan"),
    [
        (400, PARAMETER_TIDAK_VALID),
        (413, PARAMETER_TIDAK_VALID),
        (415, PARAMETER_TIDAK_VALID),
        (422, PARAMETER_TIDAK_VALID),
        (409, KONFLIK),
    ],
)
async def test_status_klien_terdaftar_menghasilkan_kode_yang_benar(
    status: int, kode_diharapkan: str, buat_klien: PembuatKlien
) -> None:
    """400/413/415/422 adalah galat klien; sebelum FIX 5 jatuh ke GALAT_SERVER
    karena tidak terdaftar di `_KODE_PER_STATUS` (`api/CLAUDE.md`, jebakan
    teknis). Dibuktikan empiris lewat `StarletteHTTPException` nyata, bukan
    tebakan — 400 genuinely reachable lewat jalur baca body FastAPI sendiri.
    409 ditambahkan di sini (bukan tes terpisah) karena memakai infrastruktur
    rute generik `/http/{status}` yang sama: `StarletteHTTPException(409)`
    dari luar `GalatAPI` sebelumnya jatuh ke `GALAT_SERVER`, kini `KONFLIK`."""
    client = await buat_klien(buat_app())

    respons = await client.get(f"/http/{status}")

    assert respons.status_code == status
    body = respons.json()
    assert body["galat"]["kode"] == kode_diharapkan
    assert body["meta"] is None


@pytest.mark.unit
async def test_status_404_dan_405_tidak_berubah_setelah_fix5(
    buat_klien: PembuatKlien,
) -> None:
    """Pemetaan 404/405 (dan lewat rute lain: 401/403/429) tidak boleh ikut
    berubah saat 400/413/415/422 didaftarkan."""
    client = await buat_klien(buat_app())

    resp_404 = await client.get("/http/404")
    resp_405 = await client.post("/desa-tidak-ada")

    assert resp_404.json()["galat"]["kode"] == TIDAK_DITEMUKAN
    assert resp_405.json()["galat"]["kode"] == METODE_TIDAK_DIIZINKAN


@pytest.mark.unit
def test_kode_galat_modul_admin_sama_dengan_namanya() -> None:
    """Empat kode galat modul admin bernilai sama persis dengan namanya."""
    assert PEKERJAAN_BERJALAN == "PEKERJAAN_BERJALAN"
    assert BERITA_TIDAK_ADA == "BERITA_TIDAK_ADA"
    assert PENGGUNA_TIDAK_ADA == "PENGGUNA_TIDAK_ADA"
    assert AKSI_DITOLAK == "AKSI_DITOLAK"
