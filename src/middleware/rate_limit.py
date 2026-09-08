"""Pembatas laju (rate limit) per-IP in-memory untuk seluruh endpoint API.

`buat_limiter()` membuat satu `Limiter` slowapi per aplikasi (bukan
singleton modul-level) supaya storage in-memory-nya segar untuk setiap
`FastAPI()` dan angka ambang berasal dari konfigurasi
(`Pengaturan.laju_bawaan`). Ambang dipasang lewat `application_limits`,
BUKAN `default_limits`: dengan `key_style` bawaan "url", default_limits
membuat bucket per (IP, path) — setiap path berparameter (mis.
`/api/model/kartu/{iddesa}` dengan ~17 ribu desa) mendapat jatah baru,
sehingga ambang efektif tak berhingga (temuan tinjauan fase 4).
`application_limits` memakai scope "global": satu bucket per IP lintas
seluruh path.

`MiddlewareBatasLaju` dipakai sebagai pengganti `SlowAPIMiddleware`:
FastAPI versi proyek ini (>=0.141) membungkus hasil `include_router`
menjadi objek `_IncludedRouter` di `app.routes` yang TIDAK punya atribut
`endpoint`, sehingga `_find_route_handler` slowapi selalu gagal dan
`_should_exempt` diam-diam MELEWATKAN seluruh rute (tidak ada rate limit
sama sekali, tanpa galat). Middleware di sini memanggil
`Limiter._check_request_limit(request, None, True)` langsung dan menjawab
pelanggaran lewat `tangani_batas_laju` (amplop seragam + Retry-After).
Tiga API privat slowapi dipakai sengaja (`_check_request_limit`,
`_inject_headers`, `_header_mapping`) — ada uji penjaga yang memastikan
ketiganya masih ada.

Registrasi `app.add_exception_handler(RateLimitExceeded, ...)` di
`main.py` adalah jaring pengaman untuk rute berdekorator
`@limiter.limit` di fase berikutnya (chat per pengguna) — jalur
middleware di berkas ini tidak memakainya karena menangkap exception
sendiri.
"""

from fastapi import Request
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.extension import HEADERS
from slowapi.util import get_remote_address
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from src.exceptions import TERLALU_BANYAK_PERMINTAAN
from src.models import gagal


def buat_limiter(laju_bawaan: str) -> Limiter:
    """Buat `Limiter` baru dengan ambang `laju_bawaan` (mis. "120/minute").

    Dibuat per-aplikasi (bukan modul-level) supaya storage in-memory
    segar per app/uji dan angka ambang berasal dari konfigurasi, bukan
    dari nilai baku yang di-hardcode.
    """
    return Limiter(
        key_func=get_remote_address,
        application_limits=[laju_bawaan],
        headers_enabled=True,
    )


def tangani_batas_laju(request: Request, exc: Exception) -> Response:
    """Balas 429 beramplop `gagal(TERLALU_BANYAK_PERMINTAAN, ...)` saat ambang laju terlampaui.

    Dipanggil langsung oleh `MiddlewareBatasLaju` dan terdaftar juga sebagai
    exception handler `RateLimitExceeded` (jaring pengaman rute berdekorator
    fase berikutnya). Parameter `exc` bertipe `Exception` supaya cocok dengan
    kontrak `add_exception_handler` Starlette; isinya tidak dipakai.
    """
    g = gagal(TERLALU_BANYAK_PERMINTAAN, "terlalu banyak permintaan, coba lagi nanti")
    respons: Response = JSONResponse(status_code=429, content=g.model_dump())
    limiter: Limiter = request.app.state.limiter
    hasil: Response = limiter._inject_headers(respons, request.state.view_rate_limit)
    return hasil


class MiddlewareBatasLaju(BaseHTTPMiddleware):
    """Terapkan ambang bawaan `Limiter` ke semua permintaan, tanpa lookup rute.

    Pengganti `SlowAPIMiddleware` — lihat docstring modul untuk alasannya.
    Pelanggaran ambang dijawab langsung lewat `tangani_batas_laju` (amplop
    seragam + header Retry-After).
    """

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        """Cek ambang sebelum handler; sisipkan header X-RateLimit ke respons."""
        limiter: Limiter = request.app.state.limiter
        if not limiter.enabled:
            return await call_next(request)

        try:
            limiter._check_request_limit(request, None, True)
        except RateLimitExceeded as exc:
            return tangani_batas_laju(request, exc)

        respons = await call_next(request)
        batas_terpakai = getattr(request.state, "view_rate_limit", None)
        # Rute berdekorator `@limiter.limit` (chat, fase 5) sudah disuntik
        # header X-RateLimit-* oleh wrapper slowapi MILIKNYA SENDIRI sebelum
        # `respons` sampai di sini. Menyuntik ulang di jalur middleware ini
        # membuat nilainya GANDA (mis. "3, 3"), dan konsumen yang mem-parse
        # header itu sebagai angka patah. Rute polos (tanpa dekorator) belum
        # berheader sama sekali di titik ini, jadi tetap diinjeksi seperti
        # sebelumnya.
        nama_header_limit = limiter._header_mapping[HEADERS.LIMIT]
        if batas_terpakai is not None and nama_header_limit not in respons.headers:
            hasil: Response = limiter._inject_headers(respons, batas_terpakai)
            return hasil
        return respons
