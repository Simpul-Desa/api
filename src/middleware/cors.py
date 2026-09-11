"""Middleware CORS per-path sesuai kebijakan PRD §3.

GET publik dibuka ke semua origin (`Access-Control-Allow-Origin: *`) untuk
prefiks di `PREFIKS_PUBLIK`. Endpoint bertoken dan seluruh permintaan
non-GET — termasuk yang path-nya masuk `PREFIKS_PUBLIK` — dibatasi ke satu
origin: `Pengaturan.origin_app` (dashboard `app/`, bawaan
`http://localhost:3000`).

`starlette.middleware.cors.CORSMiddleware` bawaan hanya mengenal satu
kebijakan origin untuk seluruh app; ia tidak bisa membedakan kebijakan per
path atau per metode HTTP. Karena kebutuhan di sini berbeda antara path
publik dan path bertoken, middleware ini ditulis khusus.

Galat 500 tak terduga ditangkap di sini (bukan diteruskan ke
`ServerErrorMiddleware` terluar Starlette) khusus permintaan ber-`Origin`:
respons handler galat global tidak melewati middleware ini lagi, sehingga
tanpa penangkapan itu 500 keluar tanpa header CORS dan browser hanya
melihat kegagalan CORS buram, bukan amplop galatnya.

Risiko yang diterima sadar (MVP): preflight OPTIONS dijawab sebelum
pembatas laju (middleware ini terluar) sehingga tidak terkena ambang —
murah diproses; ditukar dengan jaminan 429/304/galat tetap berheader CORS.
"""

import logging
from typing import Final

from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from src.config import ambil_pengaturan
from src.exceptions import GALAT_SERVER
from src.models import gagal

logger = logging.getLogger(__name__)

PREFIKS_PUBLIK: Final[tuple[str, ...]] = (
    "/health",
    "/api/wilayah",
    "/api/desa",
    "/api/model/kartu",
    "/api/geo",
    "/openapi.json",
    "/docs",
)


def _cocok_publik(path: str) -> bool:
    """Cocokkan `path` ke `PREFIKS_PUBLIK` per segmen, bukan substring polos.

    `startswith` polos membuat rute masa depan seperti `/api/desa-internal`
    diam-diam ikut publik lewat prefiks `/api/desa`.
    """
    return any(path == p or path.startswith(p + "/") for p in PREFIKS_PUBLIK)


def _origin_diizinkan(path: str, metode: str, origin: str) -> str | None:
    """Tentukan nilai `Access-Control-Allow-Origin`, atau `None` bila ditolak.

    GET pada `PREFIKS_PUBLIK` dibuka ke semua origin (`"*"`). Selain itu
    (endpoint bertoken maupun metode non-GET, termasuk di path publik)
    hanya origin `Pengaturan.origin_app` yang diizinkan.
    """
    if metode == "GET" and _cocok_publik(path):
        return "*"
    if origin.rstrip("/") == ambil_pengaturan().origin_app.rstrip("/"):
        return origin
    return None


def _tambah_vary_origin(respons: Response) -> None:
    """Pastikan `Vary: Origin` ada tanpa menimpa nilai `Vary` milik rute."""
    ada = respons.headers.get("vary")
    if ada is None:
        respons.headers["Vary"] = "Origin"
    elif "origin" not in {bagian.strip().lower() for bagian in ada.split(",")}:
        respons.headers["Vary"] = f"{ada}, Origin"


class MiddlewareCORS(BaseHTTPMiddleware):
    """Middleware CORS per-path: GET publik terbuka, sisanya dibatasi origin `app/`."""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        """Tangani preflight (OPTIONS) langsung; tambah header CORS pada respons biasa."""
        origin = request.headers.get("origin")
        if origin is None:
            return await call_next(request)

        metode_diminta = request.headers.get("access-control-request-method")
        if request.method == "OPTIONS" and metode_diminta is not None:
            izin = _origin_diizinkan(request.url.path, metode_diminta, origin)
            headers = {"Vary": "Origin"}
            if izin is not None:
                headers["Access-Control-Allow-Origin"] = izin
                # Hanya metode yang diminta dan tervalidasi yang diiklankan —
                # daftar lebih lebar tersimpan 600 detik di cache preflight
                # browser dan meloloskan non-GET lintas origin tanpa preflight
                # ulang.
                headers["Access-Control-Allow-Methods"] = metode_diminta
                headers["Access-Control-Allow-Headers"] = "authorization, content-type"
                headers["Access-Control-Max-Age"] = "600"
            return Response(status_code=200, headers=headers)

        izin = _origin_diizinkan(request.url.path, request.method, origin)
        try:
            respons: Response = await call_next(request)
        except Exception:
            logger.exception("galat tak terduga saat memproses permintaan ber-Origin")
            g = gagal(GALAT_SERVER, "terjadi galat pada server")
            respons = JSONResponse(status_code=500, content=g.model_dump())
        _tambah_vary_origin(respons)
        if izin is not None:
            respons.headers["Access-Control-Allow-Origin"] = izin
        return respons
