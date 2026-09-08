"""Uji pembatas laju per-IP (`src/middleware/rate_limit.py`).

App uji dibangun manual di berkas ini (bukan `create_app()` dari
`src.main`) supaya limiter memakai storage in-memory segar per test
dan ambang laju bisa divariasikan lewat argumen `buat_limiter`, tanpa
tergantung pemasangan wiring di `src/main.py` yang dikerjakan sesi
lain. Wiring di sini meniru persis pola yang dipasang di produksi:
`app.state.limiter`, `add_exception_handler(RateLimitExceeded, ...)`, dan
`MiddlewareBatasLaju` (pengganti `SlowAPIMiddleware` — lihat docstring
`src/middleware/rate_limit.py`).
"""

import pytest
from fastapi import FastAPI
from slowapi.errors import RateLimitExceeded
from slowapi.extension import HEADERS
from starlette.requests import Request
from starlette.responses import Response

from src.middleware.rate_limit import (
    MiddlewareBatasLaju,
    buat_limiter,
    tangani_batas_laju,
)
from tests.conftest import PembuatKlien

pytestmark = pytest.mark.anyio


def _app_uji(laju: str) -> FastAPI:
    """App FastAPI minimal dengan limiter `laju` terpasang di rute GET /uji."""
    app = FastAPI()
    app.state.limiter = buat_limiter(laju)
    app.add_exception_handler(RateLimitExceeded, tangani_batas_laju)
    app.add_middleware(MiddlewareBatasLaju)

    @app.get("/uji")
    async def _rute() -> dict[str, str]:
        return {"ok": "ya"}

    @app.get("/uji-lain")
    async def _rute_lain() -> dict[str, str]:
        return {"ok": "ya"}

    return app


@pytest.mark.integration
async def test_permintaan_di_bawah_ambang_selalu_200(buat_klien: PembuatKlien) -> None:
    klien = await buat_klien(_app_uji("2/minute"))

    respons_pertama = await klien.get("/uji")
    respons_kedua = await klien.get("/uji")

    assert respons_pertama.status_code == 200
    assert respons_kedua.status_code == 200


@pytest.mark.integration
async def test_permintaan_melewati_ambang_kembalikan_429_beramplop(
    buat_klien: PembuatKlien,
) -> None:
    klien = await buat_klien(_app_uji("2/minute"))

    await klien.get("/uji")
    await klien.get("/uji")
    respons_ketiga = await klien.get("/uji")

    assert respons_ketiga.status_code == 429
    body = respons_ketiga.json()
    assert body["sukses"] is False
    assert body["data"] is None
    assert body["galat"]["kode"] == "TERLALU_BANYAK_PERMINTAAN"
    assert body["galat"]["pesan"]
    assert body["meta"] is None


@pytest.mark.integration
async def test_respons_429_punya_header_retry_after(buat_klien: PembuatKlien) -> None:
    klien = await buat_klien(_app_uji("2/minute"))

    await klien.get("/uji")
    await klien.get("/uji")
    respons_ketiga = await klien.get("/uji")

    assert respons_ketiga.status_code == 429
    assert "retry-after" in respons_ketiga.headers


@pytest.mark.integration
async def test_ambang_dari_argumen_dihormati_bukan_hardcode(
    buat_klien: PembuatKlien,
) -> None:
    klien = await buat_klien(_app_uji("1/minute"))

    respons_pertama = await klien.get("/uji")
    respons_kedua = await klien.get("/uji")

    assert respons_pertama.status_code == 200
    assert respons_kedua.status_code == 429


@pytest.mark.integration
async def test_limiter_terpisah_per_aplikasi_storage_tidak_bocor(
    buat_klien: PembuatKlien,
) -> None:
    klien_pertama = await buat_klien(_app_uji("1/minute"))
    klien_kedua = await buat_klien(_app_uji("1/minute"))

    await klien_pertama.get("/uji")
    respons_app_pertama_kedua = await klien_pertama.get("/uji")
    respons_app_kedua_pertama = await klien_kedua.get("/uji")

    assert respons_app_pertama_kedua.status_code == 429
    assert respons_app_kedua_pertama.status_code == 200


@pytest.mark.integration
async def test_ambang_dibagi_lintas_path_bukan_per_path(
    buat_klien: PembuatKlien,
) -> None:
    """Satu bucket per IP lintas seluruh path (`application_limits`).

    Dengan `default_limits` + `key_style` "url", tiap path punya jatah
    sendiri — path berparameter membuat ambang efektif tak berhingga
    (temuan tinjauan fase 4).
    """
    klien = await buat_klien(_app_uji("2/minute"))

    assert (await klien.get("/uji")).status_code == 200
    assert (await klien.get("/uji-lain")).status_code == 200

    respons = await klien.get("/uji-lain")

    assert respons.status_code == 429


@pytest.mark.unit
def test_api_privat_slowapi_masih_ada() -> None:
    """Penjaga: tiga API privat slowapi yang dipakai `MiddlewareBatasLaju`.

    Kalau slowapi mengganti nama `_check_request_limit`/`_inject_headers`/
    `_header_mapping`, uji ini gagal saat upgrade — bukan meledak di runtime
    produksi.
    """
    limiter = buat_limiter("1/minute")

    assert hasattr(limiter, "_check_request_limit")
    assert hasattr(limiter, "_inject_headers")
    assert hasattr(limiter, "_header_mapping")


@pytest.mark.unit
async def test_limiter_dimatikan_melewatkan_permintaan_tanpa_header() -> None:
    """Cabang `limiter.enabled` adalah jaring untuk fitur kill-switch nanti.

    `buat_limiter()` tidak pernah menyetelnya False, jadi cabang ini
    didorong langsung di level unit — bukan lewat app — supaya perilakunya
    terkunci sebelum ada yang memakainya.
    """
    limiter = buat_limiter("1/minute")
    limiter.enabled = False
    app = FastAPI()
    app.state.limiter = limiter
    mw = MiddlewareBatasLaju(app)
    permintaan = Request(
        {"type": "http", "method": "GET", "path": "/uji", "headers": [], "app": app}
    )
    bawaan = Response(status_code=200)

    async def _lanjut(_: Request) -> Response:
        return bawaan

    hasil = await mw.dispatch(permintaan, _lanjut)

    assert hasil is bawaan
    assert "x-ratelimit-limit" not in hasil.headers


@pytest.mark.integration
async def test_nama_header_limit_diambil_dari_mapping_limiter(
    buat_klien: PembuatKlien,
) -> None:
    """Penjaga anti-header-ganda WAJIB membaca nama header dari
    `limiter._header_mapping[HEADERS.LIMIT]`, bukan literal
    `"X-RateLimit-Limit"` — supaya tetap benar walau mapping limiter berubah.

    Simulasi rute berdekorator `@limiter.limit`: header rate-limit sudah
    disuntik wrapper slowapi MILIKNYA SENDIRI dengan nama sesuai mapping
    (di sini ditambal jadi "X-Uji-Limit") sebelum respons sampai ke
    `MiddlewareBatasLaju`. Kalau penjaganya mengecek nama literal yang salah,
    ia tidak mengenali header itu sudah ada dan menyuntik ulang lewat
    `_inject_headers` (yang meng-`append`, bukan menimpa) — nilainya jadi
    ganda (mis. "3, 3").
    """
    app = _app_uji("2/minute")
    app.state.limiter._header_mapping[HEADERS.LIMIT] = "X-Uji-Limit"

    @app.get("/uji-sudah-berheader")
    async def _rute_sudah_berheader() -> Response:
        return Response(
            content="{}",
            media_type="application/json",
            headers={"X-Uji-Limit": "3"},
        )

    klien = await buat_klien(app)

    respons = await klien.get("/uji-sudah-berheader")

    assert respons.status_code == 200
    assert respons.headers.get("X-Uji-Limit") == "3"


@pytest.mark.unit
async def test_tanpa_view_rate_limit_respons_dikembalikan_apa_adanya(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`application_limits` scope global selalu mengisi `view_rate_limit`;
    cabang fallback ini mengunci perilaku bila kelak tidak."""
    limiter = buat_limiter("100/minute")
    monkeypatch.setattr(limiter, "_check_request_limit", lambda *a, **k: None)
    app = FastAPI()
    app.state.limiter = limiter
    mw = MiddlewareBatasLaju(app)
    permintaan = Request(
        {"type": "http", "method": "GET", "path": "/uji", "headers": [], "app": app}
    )
    bawaan = Response(status_code=200)

    async def _lanjut(_: Request) -> Response:
        return bawaan

    hasil = await mw.dispatch(permintaan, _lanjut)

    assert hasil is bawaan
    assert "x-ratelimit-limit" not in hasil.headers
