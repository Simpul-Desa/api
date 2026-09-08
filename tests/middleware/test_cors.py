"""Uji middleware CORS per-path (`src/middleware/cors.py`).

App uji dibangun lokal di berkas ini (bukan `src.main.create_app`)
supaya lepas dari wiring app sungguhan — tugas menyambungkan
`MiddlewareCORS` ke `src/main.py` dikerjakan sesi lain. Rute uji
mencakup prefiks publik (`/health`, `/api/model/kartu`), prefiks yang
TIDAK publik (`/api/model/peta-peran` — `PREFIKS_PUBLIK` hanya memuat
`/api/model/kartu`, bukan `/api/model`), dan non-GET di prefiks publik
(`/api/wilayah/uji`, tetap dibatasi origin `app/`).
"""

from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse

from src.config import ambil_pengaturan
from src.middleware.cors import MiddlewareCORS
from tests.conftest import PembuatKlien

pytestmark = pytest.mark.anyio

ORIGIN_APP_BAWAAN = "http://localhost:3000"
ORIGIN_ASING = "https://contoh.acak"
ORIGIN_JAHAT = "https://jahat.contoh"


def _app_uji() -> FastAPI:
    """App FastAPI minimal untuk uji `MiddlewareCORS`: rute publik dan non-publik."""
    app = FastAPI()
    app.add_middleware(MiddlewareCORS)

    @app.get("/health")
    async def _kesehatan() -> dict[str, str]:
        return {"status": "hidup"}

    @app.get("/api/model/kartu/{iddesa}")
    async def _kartu(iddesa: str) -> dict[str, str]:
        return {"iddesa": iddesa}

    @app.get("/api/model/peta-peran")
    async def _peta() -> dict[str, str]:
        return {"ok": "ya"}

    @app.post("/api/wilayah/uji")
    async def _tulis() -> dict[str, str]:
        return {"ok": "ya"}

    @app.get("/api/model/vary-encoding")
    async def _vary_encoding() -> JSONResponse:
        return JSONResponse({"ok": "ya"}, headers={"Vary": "Accept-Encoding"})

    @app.get("/api/model/vary-origin-sudah-ada")
    async def _vary_origin_sudah_ada() -> JSONResponse:
        return JSONResponse({"ok": "ya"}, headers={"Vary": "Origin"})

    return app


@pytest.fixture
def origin_app_bawaan(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Pastikan `ORIGIN_APP` tidak diset — `origin_app` jatuh ke bawaan localhost:3000."""
    monkeypatch.delenv("ORIGIN_APP", raising=False)
    ambil_pengaturan.cache_clear()

    yield

    ambil_pengaturan.cache_clear()


@pytest.mark.integration
async def test_tanpa_header_origin_respons_tanpa_acao(
    origin_app_bawaan: None, buat_klien: PembuatKlien
) -> None:
    klien = await buat_klien(_app_uji())

    respons = await klien.get("/health")

    assert respons.status_code == 200
    assert "access-control-allow-origin" not in respons.headers


@pytest.mark.integration
async def test_get_health_origin_asing_acao_bintang(
    origin_app_bawaan: None, buat_klien: PembuatKlien
) -> None:
    klien = await buat_klien(_app_uji())

    respons = await klien.get("/health", headers={"Origin": ORIGIN_ASING})

    assert respons.status_code == 200
    assert respons.headers["access-control-allow-origin"] == "*"


@pytest.mark.integration
async def test_get_kartu_publik_origin_asing_acao_bintang(
    origin_app_bawaan: None, buat_klien: PembuatKlien
) -> None:
    klien = await buat_klien(_app_uji())

    respons = await klien.get(
        "/api/model/kartu/1801040001", headers={"Origin": ORIGIN_ASING}
    )

    assert respons.status_code == 200
    assert respons.headers["access-control-allow-origin"] == "*"


@pytest.mark.integration
async def test_get_peta_peran_origin_app_diizinkan(
    origin_app_bawaan: None, buat_klien: PembuatKlien
) -> None:
    klien = await buat_klien(_app_uji())

    respons = await klien.get(
        "/api/model/peta-peran", headers={"Origin": ORIGIN_APP_BAWAAN}
    )

    assert respons.status_code == 200
    assert respons.headers["access-control-allow-origin"] == ORIGIN_APP_BAWAAN
    assert respons.headers["vary"] == "Origin"


@pytest.mark.integration
async def test_get_peta_peran_origin_jahat_tanpa_acao(
    origin_app_bawaan: None, buat_klien: PembuatKlien
) -> None:
    klien = await buat_klien(_app_uji())

    respons = await klien.get("/api/model/peta-peran", headers={"Origin": ORIGIN_JAHAT})

    assert respons.status_code == 200
    assert "access-control-allow-origin" not in respons.headers


@pytest.mark.integration
async def test_post_wilayah_origin_jahat_tanpa_acao_walau_prefiks_publik(
    origin_app_bawaan: None, buat_klien: PembuatKlien
) -> None:
    klien = await buat_klien(_app_uji())

    respons = await klien.post("/api/wilayah/uji", headers={"Origin": ORIGIN_JAHAT})

    assert respons.status_code == 200
    assert "access-control-allow-origin" not in respons.headers


@pytest.mark.integration
async def test_post_wilayah_origin_app_diizinkan(
    origin_app_bawaan: None, buat_klien: PembuatKlien
) -> None:
    klien = await buat_klien(_app_uji())

    respons = await klien.post(
        "/api/wilayah/uji", headers={"Origin": ORIGIN_APP_BAWAAN}
    )

    assert respons.status_code == 200
    assert respons.headers["access-control-allow-origin"] == ORIGIN_APP_BAWAAN


@pytest.mark.integration
async def test_preflight_origin_app_ke_peta_peran_lengkap(
    origin_app_bawaan: None, buat_klien: PembuatKlien
) -> None:
    klien = await buat_klien(_app_uji())

    respons = await klien.options(
        "/api/model/peta-peran",
        headers={
            "Origin": ORIGIN_APP_BAWAAN,
            "Access-Control-Request-Method": "GET",
        },
    )

    assert respons.status_code == 200
    assert respons.headers["access-control-allow-origin"] == ORIGIN_APP_BAWAAN
    assert "authorization" in respons.headers["access-control-allow-headers"]
    assert "access-control-max-age" in respons.headers


@pytest.mark.integration
async def test_preflight_origin_jahat_ke_peta_peran_tanpa_acao(
    origin_app_bawaan: None, buat_klien: PembuatKlien
) -> None:
    klien = await buat_klien(_app_uji())

    respons = await klien.options(
        "/api/model/peta-peran",
        headers={
            "Origin": ORIGIN_JAHAT,
            "Access-Control-Request-Method": "GET",
        },
    )

    assert respons.status_code == 200
    assert "access-control-allow-origin" not in respons.headers


@pytest.mark.integration
async def test_preflight_health_get_origin_asing_acao_bintang(
    origin_app_bawaan: None, buat_klien: PembuatKlien
) -> None:
    klien = await buat_klien(_app_uji())

    respons = await klien.options(
        "/health",
        headers={
            "Origin": ORIGIN_ASING,
            "Access-Control-Request-Method": "GET",
        },
    )

    assert respons.status_code == 200
    assert respons.headers["access-control-allow-origin"] == "*"


@pytest.mark.integration
async def test_preflight_wilayah_post_origin_asing_tanpa_acao(
    origin_app_bawaan: None, buat_klien: PembuatKlien
) -> None:
    klien = await buat_klien(_app_uji())

    respons = await klien.options(
        "/api/wilayah/uji",
        headers={
            "Origin": ORIGIN_ASING,
            "Access-Control-Request-Method": "POST",
        },
    )

    assert respons.status_code == 200
    assert "access-control-allow-origin" not in respons.headers


@pytest.mark.integration
async def test_preflight_tidak_memanggil_handler(
    origin_app_bawaan: None, buat_klien: PembuatKlien
) -> None:
    app = FastAPI()
    app.add_middleware(MiddlewareCORS)
    dipanggil = {"ya": False}

    @app.get("/api/model/tandai")
    async def _tandai() -> dict[str, str]:
        dipanggil["ya"] = True
        return {"ok": "ya"}

    klien = await buat_klien(app)

    respons = await klien.options(
        "/api/model/tandai",
        headers={
            "Origin": ORIGIN_APP_BAWAAN,
            "Access-Control-Request-Method": "GET",
        },
    )

    assert respons.status_code == 200
    assert dipanggil["ya"] is False


@pytest.mark.integration
async def test_origin_ditolak_tetap_membawa_vary_origin(
    origin_app_bawaan: None, buat_klien: PembuatKlien
) -> None:
    """`Vary: Origin` wajib juga pada varian tanpa ACAO — cegah cache keracunan."""
    klien = await buat_klien(_app_uji())

    respons = await klien.get(
        "/api/model/peta-peran", headers={"Origin": "https://jahat.contoh"}
    )

    assert "access-control-allow-origin" not in respons.headers
    assert "Origin" in respons.headers.get("vary", "")


@pytest.mark.integration
async def test_vary_existing_diappend_bukan_ditimpa(
    origin_app_bawaan: None, buat_klien: PembuatKlien
) -> None:
    """`Vary: Accept-Encoding` yang sudah dipasang rute harus DIAPPEND, bukan ditimpa."""
    klien = await buat_klien(_app_uji())

    respons = await klien.get(
        "/api/model/vary-encoding", headers={"Origin": ORIGIN_APP_BAWAAN}
    )

    assert respons.status_code == 200
    assert respons.headers["vary"] == "Accept-Encoding, Origin"


@pytest.mark.integration
async def test_vary_origin_sudah_ada_tidak_diduplikasi(
    origin_app_bawaan: None, buat_klien: PembuatKlien
) -> None:
    """`Vary: Origin` yang sudah dipasang rute tidak boleh jadi "Origin, Origin"."""
    klien = await buat_klien(_app_uji())

    respons = await klien.get(
        "/api/model/vary-origin-sudah-ada", headers={"Origin": ORIGIN_APP_BAWAAN}
    )

    assert respons.status_code == 200
    assert respons.headers["vary"] == "Origin"


@pytest.mark.integration
async def test_preflight_allow_methods_hanya_metode_diminta(
    origin_app_bawaan: None, buat_klien: PembuatKlien
) -> None:
    """ACAM mengiklankan hanya metode yang diminta — bukan daftar tetap.

    Daftar lebih lebar tersimpan di cache preflight browser (Max-Age) dan
    meloloskan non-GET lintas origin tanpa preflight ulang.
    """
    klien = await buat_klien(_app_uji())

    respons = await klien.options(
        "/health",
        headers={
            "Origin": "https://contoh.acak",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert respons.headers["access-control-allow-methods"] == "GET"


@pytest.mark.integration
async def test_galat_500_tetap_berheader_cors(
    origin_app_bawaan: None, buat_klien: PembuatKlien
) -> None:
    """500 tak terduga ditangkap middleware: amplop galat + header CORS utuh.

    Tanpa ini exception lolos ke `ServerErrorMiddleware` terluar dan
    responsnya tidak pernah melewati `MiddlewareCORS` lagi.
    """
    app = _app_uji()

    @app.get("/health/meledak-uji")
    async def _meledak() -> dict[str, str]:
        raise RuntimeError("meledak")

    klien = await buat_klien(app, lempar_galat_app=False)

    respons = await klien.get(
        "/health/meledak-uji", headers={"Origin": "https://contoh.acak"}
    )

    assert respons.status_code == 500
    body = respons.json()
    assert body["sukses"] is False
    assert body["galat"]["kode"] == "GALAT_SERVER"
    assert respons.headers["access-control-allow-origin"] == "*"
