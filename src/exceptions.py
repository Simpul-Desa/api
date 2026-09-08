"""Kontrak galat (error) seragam untuk seluruh endpoint API.

Setiap respons galat dibungkus lewat `gagal()` dari `src.models`, lalu
dikirim sebagai `JSONResponse` dengan status HTTP yang sesuai. Modul ini
menyediakan kode-kode galat baku, exception `GalatAPI` untuk dilempar dari
kode rute, dan `daftarkan_handler()` untuk mendaftarkan seluruh exception
handler ke aplikasi FastAPI.
"""

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from src.models import gagal

logger = logging.getLogger(__name__)

PARAMETER_TIDAK_VALID = "PARAMETER_TIDAK_VALID"
METODE_TIDAK_DIIZINKAN = "METODE_TIDAK_DIIZINKAN"
TIDAK_DITEMUKAN = "TIDAK_DITEMUKAN"
DESA_TIDAK_ADA = "DESA_TIDAK_ADA"
WILAYAH_TIDAK_ADA = "WILAYAH_TIDAK_ADA"
TIDAK_BERWENANG = "TIDAK_BERWENANG"
PERAN_KURANG = "PERAN_KURANG"
TERLALU_BANYAK_PERMINTAAN = "TERLALU_BANYAK_PERMINTAAN"
GALAT_SERVER = "GALAT_SERVER"
DATA_BELUM_SIAP = "DATA_BELUM_SIAP"
AUTH_BELUM_SIAP = "AUTH_BELUM_SIAP"
PEKERJAAN_BERJALAN = "PEKERJAAN_BERJALAN"
BERITA_TIDAK_ADA = "BERITA_TIDAK_ADA"
PENGGUNA_TIDAK_ADA = "PENGGUNA_TIDAK_ADA"
AKSI_DITOLAK = "AKSI_DITOLAK"
KONFLIK = "KONFLIK"
PERAN_TIDAK_DIKENAL = "PERAN_TIDAK_DIKENAL"
# AI_BELUM_SIAP dan GALAT_LLM selalu dilempar lewat GalatAPI, yang sudah
# membawa kode dan status HTTP-nya sendiri (503 dan 502) - keduanya tidak
# pernah singgah di pemetaan status->kode _KODE_PER_STATUS di bawah.
AI_BELUM_SIAP = "AI_BELUM_SIAP"
GALAT_LLM = "GALAT_LLM"

# Status yang tidak terdaftar di sini jatuh ke GALAT_SERVER (lihat
# _tangani_http). Semua entri di bawah adalah galat klien: tanpa
# didaftarkan eksplisit, statusnya dilaporkan sebagai galat server. 400/
# 413/415/422 dipetakan ke PARAMETER_TIDAK_VALID (kode publik yang sudah
# ada, bukan kode baru) - 400 genuinely reachable lewat jalur baca body
# FastAPI sendiri (`HTTPException(400, "There was an error parsing the
# body")` saat body gagal dibaca di tengah stream). 409 dipetakan ke KONFLIK
# — kode ini HANYA untuk 409 generik yang tidak lewat `GalatAPI` (mis.
# `StarletteHTTPException(409)` dilempar langsung); pekerjaan penyegaran
# yang sudah berjalan tetap melempar `GalatAPI(PEKERJAAN_BERJALAN, ..., 409)`
# lewat handler `GalatAPI`-nya sendiri, tidak pernah singgah di sini.
_KODE_PER_STATUS = {
    400: PARAMETER_TIDAK_VALID,
    401: TIDAK_BERWENANG,
    403: PERAN_KURANG,
    404: TIDAK_DITEMUKAN,
    405: METODE_TIDAK_DIIZINKAN,
    409: KONFLIK,
    413: PARAMETER_TIDAK_VALID,
    415: PARAMETER_TIDAK_VALID,
    422: PARAMETER_TIDAK_VALID,
    429: TERLALU_BANYAK_PERMINTAAN,
}


class GalatAPI(Exception):
    """Exception domain untuk galat API yang sudah punya kode dan status."""

    def __init__(self, kode: str, pesan: str, status: int) -> None:
        super().__init__(pesan)
        self.kode = kode
        self.pesan = pesan
        self.status = status


def _ringkas_kesalahan_validasi(exc: RequestValidationError) -> str:
    kesalahan = exc.errors()
    bagian = []
    for e in kesalahan[:3]:
        lokasi = ".".join(str(bagian_lokasi) for bagian_lokasi in e["loc"])
        bagian.append(f"{lokasi}: {e['msg']}")
    return "parameter tidak valid: " + "; ".join(bagian)


def daftarkan_handler(app: FastAPI) -> None:
    """Daftarkan seluruh exception handler galat ke aplikasi FastAPI."""

    @app.exception_handler(GalatAPI)
    async def _tangani_galat_api(request: Request, exc: GalatAPI) -> JSONResponse:
        g = gagal(exc.kode, exc.pesan)
        return JSONResponse(status_code=exc.status, content=g.model_dump())

    @app.exception_handler(RequestValidationError)
    async def _tangani_validasi(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        g = gagal(PARAMETER_TIDAK_VALID, _ringkas_kesalahan_validasi(exc))
        return JSONResponse(status_code=422, content=g.model_dump())

    @app.exception_handler(StarletteHTTPException)
    async def _tangani_http(
        request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        kode = _KODE_PER_STATUS.get(exc.status_code, GALAT_SERVER)
        g = gagal(kode, str(exc.detail))
        return JSONResponse(status_code=exc.status_code, content=g.model_dump())

    @app.exception_handler(Exception)
    async def _tangani_tak_terduga(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("galat tak terduga saat memproses permintaan")
        g = gagal(GALAT_SERVER, "terjadi galat pada server")
        return JSONResponse(status_code=500, content=g.model_dump())
