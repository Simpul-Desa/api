"""Middleware cache HTTP (`ETag` + `Cache-Control`) untuk data beku `data-salinan/`.

Permintaan GET pada prefiks data ANONIM (`PREFIKS_CACHE`) diberi `ETag`
dari hash manifest data-salinan/ + `Cache-Control` publik ber-`max-age`;
`If-None-Match` yang cocok dijawab 304 tanpa memanggil handler.

Prefiks data BERTOKEN (`PREFIKS_TANPA_CACHE` — empat router tamu fase 4,
berita fase 6, `/api/admin` fase 7, `/api/laporan` fase 8 — rute PDF
bertoken, bukan JSON, `/api/chat` fase 5, dan `/api/profil` fase 2 auth —
PRD §5: berita dan chat selalu `no-store`) sengaja TIDAK ikut skema itu:
temuan tinjauan keamanan fase 4 membuktikan
(1) `Cache-Control: public` membuat shared cache (CDN/proxy) menyimpan
body berotorisasi lalu menyajikannya ke klien anonim, dan (2) jawaban 304
dari middleware ini keluar SEBELUM dependensi peran berjalan, sehingga
`If-None-Match` (ETag-nya global dan terbaca anonim dari rute publik)
menembus gerbang 401. Karena itu SELURUH status pada prefiks bertoken
distempel `Cache-Control: private, no-store` untuk SEMUA metode HTTP
(bukan hanya GET — `/api/admin` menerima POST/DELETE), bukan hanya 2xx —
404/405 pada prefiks itu boleh di-cache heuristik oleh shared cache
menurut RFC 9111 kalau dibiarkan tanpa header — dan tidak pernah dijawab
304 di sini. Menyimpang dari PRD §5 (ETag publik untuk semua data beku)
— matriks akses PRD akar §3 menang; lihat laporan fase 4.

Rute lain dan permintaan tanpa manifest tidak disentuh sama sekali.
"""

from typing import Any, Final

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from src.config import ambil_pengaturan

PREFIKS_CACHE: Final[tuple[str, ...]] = (
    "/api/wilayah",
    "/api/desa",
    "/api/model/kartu",
    "/api/geo",
)

PREFIKS_TANPA_CACHE: Final[tuple[str, ...]] = (
    "/api/model/peta-peran",
    "/api/model/citra-potensi",
    "/api/model/jalur-ekonomi",
    "/api/model/desa-kembar",
    "/api/berita",
    "/api/profil",
    "/api/admin",
    "/api/laporan",
    "/api/chat",
)


def _cocok_prefiks(path: str, prefiks: tuple[str, ...]) -> bool:
    """Cocokkan `path` ke salah satu `prefiks` per segmen, bukan substring polos.

    `startswith` polos membuat rute masa depan seperti
    `/api/model/kartu-interno` diam-diam mewarisi perlakuan `/api/model/kartu`
    (publik). Padanan `src/middleware/cors.py::_cocok_publik` untuk daftar
    prefiks middleware ini.
    """
    return any(path == p or path.startswith(p + "/") for p in prefiks)


class MiddlewareCacheHTTP(BaseHTTPMiddleware):
    """Middleware cache HTTP: ETag dari hash manifest + Cache-Control, 304 bila cocok."""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        """Tambah header cache untuk GET pada `PREFIKS_CACHE`; lewati sisanya apa adanya."""
        if _cocok_prefiks(request.url.path, PREFIKS_TANPA_CACHE):
            respons_bertoken = await call_next(request)
            # Distempel untuk SEMUA status, bukan hanya 2xx -- 404/405 pada
            # prefiks bertoken tanpa header ini boleh di-cache heuristik oleh
            # shared cache (RFC 9111), dan PRD §5 menulis chat/berita/admin/
            # laporan "selalu" no-store, bukan "2xx saja".
            respons_bertoken.headers["Cache-Control"] = "private, no-store"
            return respons_bertoken

        if request.method != "GET":
            return await call_next(request)

        if not _cocok_prefiks(request.url.path, PREFIKS_CACHE):
            return await call_next(request)

        manifest: dict[str, Any] | None = getattr(request.app.state, "manifest", None)
        hash_manifest = manifest.get("hash") if manifest else None
        if not hash_manifest:
            return await call_next(request)

        etag = f'"{hash_manifest}"'
        max_age = ambil_pengaturan().cache_max_age
        cache_control = f"public, max-age={max_age}"
        if request.headers.get("if-none-match") == etag:
            return Response(
                status_code=304,
                headers={"ETag": etag, "Cache-Control": cache_control},
            )

        respons = await call_next(request)
        if respons.status_code == 200:
            respons.headers["ETag"] = etag
            respons.headers["Cache-Control"] = cache_control
        return respons
