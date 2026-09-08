"""Uji middleware cache HTTP (`src/middleware/http_cache.py`).

Uji inti dipakai lewat app FastAPI lokal (bukan `klien` dari conftest):
saat berkas ini ditulis, `src/wilayah/router.py` masih stub kosong di
sesi paralel lain, sehingga `/api/wilayah/provinsi` bisa saja masih
membalas 404 (404 pun tidak diberi header cache — pada prefiks PUBLIK
middleware hanya menyentuh 200; prefiks BERTOKEN distempel di semua
status, lihat temuan T5). Supaya uji tidak rapuh terhadap progres sesi lain,
perilaku inti middleware (ETag, 304, lewat prefiks, manifest None)
diuji lewat `_dummy_app` — app FastAPI minimal dengan rute GET 200 di
prefiks publik `/api/model/kartu` (fase 4 memecah prefiks: rute bertoken
seperti `/api/model/peta-peran` tidak lagi di-cache publik dan tidak
pernah dijawab 304 — lihat docstring `src/middleware/http_cache.py`) dan
`state.manifest` diatur manual. Satu uji
integrasi lewat `klien` menegaskan `/health` (di luar prefiks cache)
tidak disentuh middleware sama sekali.
"""

from collections.abc import Iterator
from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from src.config import ambil_pengaturan
from src.middleware.http_cache import MiddlewareCacheHTTP
from tests.conftest import PembuatKlien

pytestmark = pytest.mark.anyio


def _dummy_app(manifest: dict[str, Any] | None) -> FastAPI:
    """App FastAPI minimal: rute di prefiks publik, prefiks bertoken, dan luar prefiks.

    `state.manifest` diatur manual (tanpa lifespan) supaya uji middleware
    lepas dari isi `data-salinan/` sungguhan.
    """
    app = FastAPI()
    app.add_middleware(MiddlewareCacheHTTP)

    @app.get("/api/model/kartu/dummy")
    def _dummy_get() -> dict[str, str]:
        return {"halo": "dunia"}

    @app.post("/api/model/kartu/dummy")
    def _dummy_post() -> dict[str, str]:
        return {"halo": "dunia"}

    @app.get("/api/model/peta-peran/dummy")
    def _dummy_bertoken() -> dict[str, str]:
        return {"halo": "dunia"}

    @app.get("/api/admin/uji")
    def _dummy_admin_get() -> dict[str, str]:
        return {"halo": "dunia"}

    @app.post("/api/admin/uji", status_code=202)
    def _dummy_admin_post() -> dict[str, str]:
        return {"halo": "dunia"}

    @app.get("/api/laporan/uji")
    def _dummy_laporan_get() -> dict[str, str]:
        return {"halo": "dunia"}

    @app.get("/lainnya")
    def _lainnya() -> dict[str, str]:
        return {"halo": "dunia"}

    app.state.manifest = manifest
    return app


@pytest.fixture
def pengaturan_bawaan(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Pastikan `CACHE_MAX_AGE` tidak diset — `cache_max_age` jatuh ke bawaan 3600."""
    monkeypatch.delenv("CACHE_MAX_AGE", raising=False)
    ambil_pengaturan.cache_clear()

    yield

    ambil_pengaturan.cache_clear()


@pytest.fixture
def cache_max_age_uji(monkeypatch: pytest.MonkeyPatch) -> Iterator[int]:
    """Set `CACHE_MAX_AGE=120` supaya uji menegaskan nilai dibaca dari `Pengaturan`."""
    monkeypatch.setenv("CACHE_MAX_AGE", "120")
    ambil_pengaturan.cache_clear()

    yield 120

    ambil_pengaturan.cache_clear()


@pytest.mark.integration
async def test_get_prefiks_data_dengan_manifest_membawa_etag_dan_cache_control_bawaan(
    pengaturan_bawaan: None, buat_klien: PembuatKlien
) -> None:
    klien = await buat_klien(_dummy_app({"hash": "uji123"}))

    respons = await klien.get("/api/model/kartu/dummy")

    assert respons.status_code == 200
    assert respons.headers["etag"] == '"uji123"'
    assert respons.headers["cache-control"] == "public, max-age=3600"


@pytest.mark.integration
async def test_cache_control_max_age_dibaca_dari_pengaturan(
    cache_max_age_uji: int, buat_klien: PembuatKlien
) -> None:
    klien = await buat_klien(_dummy_app({"hash": "uji123"}))

    respons = await klien.get("/api/model/kartu/dummy")

    assert respons.status_code == 200
    assert respons.headers["cache-control"] == f"public, max-age={cache_max_age_uji}"


@pytest.mark.integration
async def test_if_none_match_cocok_kembalikan_304_tanpa_body(
    pengaturan_bawaan: None, buat_klien: PembuatKlien
) -> None:
    klien = await buat_klien(_dummy_app({"hash": "uji123"}))

    respons = await klien.get(
        "/api/model/kartu/dummy", headers={"If-None-Match": '"uji123"'}
    )

    assert respons.status_code == 304
    assert respons.content == b""
    assert respons.headers["etag"] == '"uji123"'


@pytest.mark.integration
async def test_if_none_match_tidak_cocok_tetap_200(
    pengaturan_bawaan: None, buat_klien: PembuatKlien
) -> None:
    klien = await buat_klien(_dummy_app({"hash": "uji123"}))

    respons = await klien.get(
        "/api/model/kartu/dummy", headers={"If-None-Match": '"lain"'}
    )

    assert respons.status_code == 200
    assert respons.headers["etag"] == '"uji123"'


@pytest.mark.integration
async def test_manifest_none_tanpa_header_cache_tanpa_crash(
    pengaturan_bawaan: None, buat_klien: PembuatKlien
) -> None:
    klien = await buat_klien(_dummy_app(None))

    respons = await klien.get("/api/model/kartu/dummy")

    assert respons.status_code == 200
    assert "etag" not in respons.headers
    assert "cache-control" not in respons.headers


@pytest.mark.integration
async def test_path_di_luar_prefiks_cache_tidak_disentuh(
    pengaturan_bawaan: None, buat_klien: PembuatKlien
) -> None:
    klien = await buat_klien(_dummy_app({"hash": "uji123"}))

    respons = await klien.get("/lainnya")

    assert respons.status_code == 200
    assert "etag" not in respons.headers
    assert "cache-control" not in respons.headers


@pytest.mark.integration
async def test_method_selain_get_tidak_disentuh(
    pengaturan_bawaan: None, buat_klien: PembuatKlien
) -> None:
    klien = await buat_klien(_dummy_app({"hash": "uji123"}))

    respons = await klien.post("/api/model/kartu/dummy")

    assert respons.status_code == 200
    assert "etag" not in respons.headers
    assert "cache-control" not in respons.headers


@pytest.mark.integration
async def test_health_tanpa_header_cache(klien: httpx.AsyncClient) -> None:
    respons = await klien.get("/health")

    assert respons.status_code == 200
    assert "etag" not in respons.headers
    assert "cache-control" not in respons.headers


@pytest.mark.integration
async def test_prefiks_bertoken_tidak_dicache_publik(
    pengaturan_bawaan: None, buat_klien: PembuatKlien
) -> None:
    """Rute bertoken: `private, no-store`, tanpa ETag (temuan tinjauan fase 4)."""
    klien = await buat_klien(_dummy_app({"hash": "uji123"}))

    respons = await klien.get("/api/model/peta-peran/dummy")

    assert respons.status_code == 200
    assert respons.headers["cache-control"] == "private, no-store"
    assert "etag" not in respons.headers


@pytest.mark.integration
async def test_prefiks_bertoken_if_none_match_tidak_dijawab_304(
    pengaturan_bawaan: None, buat_klien: PembuatKlien
) -> None:
    """`If-None-Match` pada rute bertoken tidak boleh memotong jalur auth."""
    klien = await buat_klien(_dummy_app({"hash": "uji123"}))

    respons = await klien.get(
        "/api/model/peta-peran/dummy", headers={"If-None-Match": '"uji123"'}
    )

    assert respons.status_code == 200


@pytest.mark.integration
async def test_304_membawa_cache_control(
    pengaturan_bawaan: None, buat_klien: PembuatKlien
) -> None:
    """304 menyegarkan umur cache klien (RFC 9111 §15.4.5)."""
    klien = await buat_klien(_dummy_app({"hash": "uji123"}))

    respons = await klien.get(
        "/api/model/kartu/dummy", headers={"If-None-Match": '"uji123"'}
    )

    assert respons.status_code == 304
    assert respons.headers["cache-control"] == "public, max-age=3600"


@pytest.mark.integration
async def test_prefiks_admin_get_no_store(
    pengaturan_bawaan: None, buat_klien: PembuatKlien
) -> None:
    """`/api/admin` GET: `private, no-store`, bukan cache publik."""
    klien = await buat_klien(_dummy_app({"hash": "uji123"}))

    respons = await klien.get("/api/admin/uji")

    assert respons.status_code == 200
    assert respons.headers["cache-control"] == "private, no-store"


@pytest.mark.integration
async def test_prefiks_admin_non_get_juga_no_store(
    pengaturan_bawaan: None, buat_klien: PembuatKlien
) -> None:
    """`/api/admin` non-GET (POST 202) tetap distempel no-store."""
    klien = await buat_klien(_dummy_app({"hash": "uji123"}))

    respons = await klien.post("/api/admin/uji")

    assert respons.status_code == 202
    assert respons.headers["cache-control"] == "private, no-store"


@pytest.mark.integration
async def test_prefiks_admin_tidak_pernah_ber_etag(
    pengaturan_bawaan: None, buat_klien: PembuatKlien
) -> None:
    """`/api/admin` tidak pernah diberi ETag, walau manifest tersedia."""
    klien = await buat_klien(_dummy_app({"hash": "uji123"}))

    respons = await klien.get("/api/admin/uji")

    assert "etag" not in respons.headers


@pytest.mark.integration
async def test_path_mirip_prefiks_cache_sebagai_substring_tidak_ikut_publik(
    pengaturan_bawaan: None, buat_klien: PembuatKlien
) -> None:
    """`/api/model/kartu-interno` cuma berbagi PREFIKS sebagai substring
    dengan `/api/model/kartu` (publik) — `startswith` polos meloloskannya
    ke ETag/304 publik. `src/middleware/cors.py::_cocok_publik` sudah
    memecahkan cacat kelas ini untuk daftar prefiksnya sendiri; middleware
    cache ini belum, dan rute token-gated masa depan seperti itu akan
    diam-diam mewarisi perlakuan publik prefiks `/api/model/kartu`."""
    app = _dummy_app({"hash": "uji123"})

    @app.get("/api/model/kartu-interno/dummy")
    def _dummy_mirip_publik() -> dict[str, str]:
        return {"halo": "dunia"}

    klien = await buat_klien(app)

    respons = await klien.get("/api/model/kartu-interno/dummy")

    assert respons.status_code == 200
    assert "etag" not in respons.headers
    assert "cache-control" not in respons.headers


@pytest.mark.integration
async def test_path_mirip_prefiks_desa_sebagai_substring_tidak_ikut_publik(
    pengaturan_bawaan: None, buat_klien: PembuatKlien
) -> None:
    """`/api/desa-internal` cuma berbagi `/api/desa` (`PREFIKS_CACHE`) sebagai
    substring — bukan salah satu prefiks resmi manapun, jadi tidak boleh
    dapat ETag/304 publik maupun stempel no-store; lewat tanpa header
    cache apa pun, sama seperti path di luar prefiks lain."""
    app = _dummy_app({"hash": "uji123"})

    @app.get("/api/desa-internal/dummy")
    def _dummy_mirip_desa() -> dict[str, str]:
        return {"halo": "dunia"}

    klien = await buat_klien(app)

    respons = await klien.get("/api/desa-internal/dummy")

    assert respons.status_code == 200
    assert "etag" not in respons.headers
    assert "cache-control" not in respons.headers


@pytest.mark.integration
async def test_prefiks_bertoken_404_membawa_cache_control(
    pengaturan_bawaan: None, buat_klien: PembuatKlien
) -> None:
    """T5: 404 pada prefiks bertoken (rute tidak ada) tetap distempel
    `private, no-store` -- sebelumnya stempel hanya dipasang untuk 2xx,
    jadi 404 pada prefiks bertoken keluar TANPA `Cache-Control` sama
    sekali, yang boleh di-cache heuristik oleh shared cache (RFC 9111)."""
    klien = await buat_klien(_dummy_app({"hash": "uji123"}))

    respons = await klien.get("/api/admin/tidak-ada")

    assert respons.status_code == 404
    assert respons.headers["cache-control"] == "private, no-store"


@pytest.mark.integration
async def test_prefiks_bertoken_405_membawa_cache_control(
    pengaturan_bawaan: None, buat_klien: PembuatKlien
) -> None:
    """T5: 405 pada prefiks bertoken (metode tidak didaftarkan rute) tetap
    distempel `private, no-store`."""
    klien = await buat_klien(_dummy_app({"hash": "uji123"}))

    respons = await klien.post("/api/laporan/uji")

    assert respons.status_code == 405
    assert respons.headers["cache-control"] == "private, no-store"


@pytest.mark.integration
async def test_prefiks_laporan_no_store_tanpa_etag(
    pengaturan_bawaan: None, buat_klien: PembuatKlien
) -> None:
    """`/api/laporan` (PDF bertoken fase 8): `private, no-store`, tanpa ETag."""
    klien = await buat_klien(_dummy_app({"hash": "uji123"}))

    respons = await klien.get("/api/laporan/uji")

    assert respons.status_code == 200
    assert respons.headers["cache-control"] == "private, no-store"
    assert "etag" not in respons.headers
