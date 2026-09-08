"""Uji dependensi penegak peran (`src/auth/dependencies.py`).

Sasaran monkeypatch adalah atribut modul `src.auth.service` (alias `auth`);
yang dipanggil adalah `src.auth.dependencies` (alias `dep`). Pemisahan
alias ini penting: `dependencies.py` memanggil service lewat objek modul,
jadi tambalan di `auth` benar-benar mengenai jalur yang diuji.
"""

from collections.abc import Callable
from typing import Any

import httpx
import jwt
import pytest
from fastapi import Depends, FastAPI

from src.auth.schemas import Identitas
from src.config import Pengaturan, ambil_pengaturan
from src.exceptions import (
    AUTH_BELUM_SIAP,
    PERAN_KURANG,
    TIDAK_BERWENANG,
    daftarkan_handler,
)
from tests.auth.bantu import (
    SUB_UJI,
    SUPABASE_URL_UJI,
    app_uji,
    klien_mock,
    pasang_env_supabase,
)
from tests.conftest import PembuatKlien

pytestmark = pytest.mark.anyio


@pytest.mark.integration
async def test_wajib_tamu_tanpa_header_401(
    monkeypatch: pytest.MonkeyPatch, buat_klien: PembuatKlien
) -> None:
    pasang_env_supabase(monkeypatch)
    import src.auth.dependencies as dep

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[{"peran": "tamu"}])

    app = app_uji(dep.wajib_tamu)
    app.state.klien_supabase = klien_mock(handler)

    try:
        klien = await buat_klien(app)
        respons = await klien.get("/uji")

        assert respons.status_code == 401
        body = respons.json()
        assert body["sukses"] is False
        assert body["galat"]["kode"] == TIDAK_BERWENANG
    finally:
        ambil_pengaturan.cache_clear()


@pytest.mark.integration
async def test_wajib_tamu_token_sah_profil_tamu_200(
    monkeypatch: pytest.MonkeyPatch,
    buat_token: Callable[..., str],
    kunci_es256: tuple[str, Any],
    buat_klien: PembuatKlien,
) -> None:
    pasang_env_supabase(monkeypatch)
    import src.auth.dependencies as dep
    import src.auth.service as auth

    _, kunci_publik = kunci_es256
    monkeypatch.setattr(
        auth, "_kunci_penandatangan", lambda token, pengaturan: kunci_publik
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[{"peran": "tamu"}])

    app = app_uji(dep.wajib_tamu)
    app.state.klien_supabase = klien_mock(handler)

    try:
        token = buat_token(SUB_UJI, iss=f"{SUPABASE_URL_UJI}/auth/v1")
        klien = await buat_klien(app)
        respons = await klien.get("/uji", headers={"Authorization": f"Bearer {token}"})

        assert respons.status_code == 200
        assert respons.json() == {"ok": "ya"}
    finally:
        ambil_pengaturan.cache_clear()


@pytest.mark.integration
async def test_wajib_tamu_profil_kosong_403(
    monkeypatch: pytest.MonkeyPatch,
    buat_token: Callable[..., str],
    kunci_es256: tuple[str, Any],
    buat_klien: PembuatKlien,
) -> None:
    pasang_env_supabase(monkeypatch)
    import src.auth.dependencies as dep
    import src.auth.service as auth

    _, kunci_publik = kunci_es256
    monkeypatch.setattr(
        auth, "_kunci_penandatangan", lambda token, pengaturan: kunci_publik
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[])

    app = app_uji(dep.wajib_tamu)
    app.state.klien_supabase = klien_mock(handler)

    try:
        token = buat_token(SUB_UJI, iss=f"{SUPABASE_URL_UJI}/auth/v1")
        klien = await buat_klien(app)
        respons = await klien.get("/uji", headers={"Authorization": f"Bearer {token}"})

        assert respons.status_code == 403
        assert respons.json()["galat"]["kode"] == PERAN_KURANG
    finally:
        ambil_pengaturan.cache_clear()


@pytest.mark.integration
async def test_wajib_admin_profil_tamu_403(
    monkeypatch: pytest.MonkeyPatch,
    buat_token: Callable[..., str],
    kunci_es256: tuple[str, Any],
    buat_klien: PembuatKlien,
) -> None:
    pasang_env_supabase(monkeypatch)
    import src.auth.dependencies as dep
    import src.auth.service as auth

    _, kunci_publik = kunci_es256
    monkeypatch.setattr(
        auth, "_kunci_penandatangan", lambda token, pengaturan: kunci_publik
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[{"peran": "tamu"}])

    dependensi_admin = dep.wajib_peran(frozenset({"admin"}))
    app = app_uji(dependensi_admin)
    app.state.klien_supabase = klien_mock(handler)

    try:
        token = buat_token(SUB_UJI, iss=f"{SUPABASE_URL_UJI}/auth/v1")
        klien = await buat_klien(app)
        respons = await klien.get("/uji", headers={"Authorization": f"Bearer {token}"})

        assert respons.status_code == 403
        assert respons.json()["galat"]["kode"] == PERAN_KURANG
    finally:
        ambil_pengaturan.cache_clear()


@pytest.mark.integration
async def test_wajib_tamu_env_supabase_kosong_503(
    monkeypatch: pytest.MonkeyPatch,
    buat_token: Callable[..., str],
    kunci_es256: tuple[str, Any],
    buat_klien: PembuatKlien,
) -> None:
    import src.auth.dependencies as dep
    import src.auth.service as auth

    # setenv string kosong, bukan delenv: berkas .env lokal (bila ada) tetap
    # tertimpa sehingga uji tidak flaky antar mesin.
    monkeypatch.setenv("SUPABASE_URL", "")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "")
    ambil_pengaturan.cache_clear()

    _, kunci_publik = kunci_es256
    monkeypatch.setattr(
        auth, "_kunci_penandatangan", lambda token, pengaturan: kunci_publik
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[{"peran": "tamu"}])

    app = app_uji(dep.wajib_tamu)
    app.state.klien_supabase = klien_mock(handler)

    try:
        token = buat_token(SUB_UJI, iss=f"{SUPABASE_URL_UJI}/auth/v1")
        klien = await buat_klien(app)
        respons = await klien.get("/uji", headers={"Authorization": f"Bearer {token}"})

        assert respons.status_code == 503
        assert respons.json()["galat"]["kode"] == AUTH_BELUM_SIAP
    finally:
        ambil_pengaturan.cache_clear()


@pytest.mark.integration
async def test_wajib_tamu_jwks_tidak_terjangkau_503_auth_belum_siap(
    monkeypatch: pytest.MonkeyPatch, buat_klien: PembuatKlien
) -> None:
    """`PyJWKClientConnectionError` (JWKS tak terjangkau) = kegagalan sisi
    layanan (503 `AUTH_BELUM_SIAP`), BUKAN kredensial buruk (401) — PRD §5."""
    pasang_env_supabase(monkeypatch)
    import src.auth.dependencies as dep
    import src.auth.service as auth

    def _kunci_gagal_koneksi(token: str, pengaturan: Pengaturan) -> Any:
        raise jwt.exceptions.PyJWKClientConnectionError("JWKS tidak terjangkau")

    monkeypatch.setattr(auth, "_kunci_penandatangan", _kunci_gagal_koneksi)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[{"peran": "tamu"}])

    app = app_uji(dep.wajib_tamu)
    app.state.klien_supabase = klien_mock(handler)

    try:
        klien = await buat_klien(app)
        respons = await klien.get("/uji", headers={"Authorization": "Bearer apa-saja"})

        assert respons.status_code == 503
        body = respons.json()
        assert body["galat"]["kode"] == AUTH_BELUM_SIAP
        assert body["galat"]["pesan"] == "layanan autentikasi tidak terjangkau"
    finally:
        ambil_pengaturan.cache_clear()


@pytest.mark.integration
async def test_wajib_tamu_jwks_tanpa_kunci_503_auth_belum_siap(
    monkeypatch: pytest.MonkeyPatch, buat_klien: PembuatKlien
) -> None:
    """`PyJWKSetError` (JWKS kosong, mis. proyek masih pakai secret HS256 lama)
    juga kegagalan sisi layanan (503), dengan pesan publik berbeda dari JWKS
    tak terjangkau — cabang terpisah di `verifikasi_token`."""
    pasang_env_supabase(monkeypatch)
    import src.auth.dependencies as dep
    import src.auth.service as auth

    def _kunci_kosong(token: str, pengaturan: Pengaturan) -> Any:
        raise jwt.exceptions.PyJWKSetError("JWKS tidak berisi kunci")

    monkeypatch.setattr(auth, "_kunci_penandatangan", _kunci_kosong)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[{"peran": "tamu"}])

    app = app_uji(dep.wajib_tamu)
    app.state.klien_supabase = klien_mock(handler)

    try:
        klien = await buat_klien(app)
        respons = await klien.get("/uji", headers={"Authorization": "Bearer apa-saja"})

        assert respons.status_code == 503
        body = respons.json()
        assert body["galat"]["kode"] == AUTH_BELUM_SIAP
        assert body["galat"]["pesan"] == "kunci penandatangan tidak tersedia"
    finally:
        ambil_pengaturan.cache_clear()


@pytest.mark.integration
async def test_wajib_tamu_kid_tak_dikenal_401_token_tidak_sah(
    monkeypatch: pytest.MonkeyPatch, buat_klien: PembuatKlien
) -> None:
    """`PyJWKClientError` (mis. `kid` tak dikenal) = kredensial buruk (401),
    BUKAN kegagalan layanan — harus beda status dari dua kasus 503 di atas."""
    pasang_env_supabase(monkeypatch)
    import src.auth.dependencies as dep
    import src.auth.service as auth

    def _kid_tak_dikenal(token: str, pengaturan: Pengaturan) -> Any:
        raise jwt.exceptions.PyJWKClientError("kid tak dikenal")

    monkeypatch.setattr(auth, "_kunci_penandatangan", _kid_tak_dikenal)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[{"peran": "tamu"}])

    app = app_uji(dep.wajib_tamu)
    app.state.klien_supabase = klien_mock(handler)

    try:
        klien = await buat_klien(app)
        respons = await klien.get("/uji", headers={"Authorization": "Bearer apa-saja"})

        assert respons.status_code == 401
        body = respons.json()
        assert body["galat"]["kode"] == TIDAK_BERWENANG
        assert body["galat"]["pesan"] == "token tidak sah"
    finally:
        ambil_pengaturan.cache_clear()


@pytest.mark.integration
async def test_peran_dibaca_dari_db_bukan_klaim_token(
    monkeypatch: pytest.MonkeyPatch,
    buat_token: Callable[..., str],
    kunci_es256: tuple[str, Any],
    buat_klien: PembuatKlien,
) -> None:
    """Klaim token bilang `role=admin`, tapi profil di DB bilang `tamu`.

    Terhadap `wajib_peran({"admin"})` hasilnya harus 403 — pembuktian bahwa
    peran selalu dibaca dari tabel `profil`, tidak pernah dari klaim token
    (PRD §5).
    """
    pasang_env_supabase(monkeypatch)
    import src.auth.dependencies as dep
    import src.auth.service as auth

    _, kunci_publik = kunci_es256
    monkeypatch.setattr(
        auth, "_kunci_penandatangan", lambda token, pengaturan: kunci_publik
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[{"peran": "tamu"}])

    dependensi_admin = dep.wajib_peran(frozenset({"admin"}))
    app = app_uji(dependensi_admin)
    app.state.klien_supabase = klien_mock(handler)

    try:
        token = buat_token(
            SUB_UJI,
            iss=f"{SUPABASE_URL_UJI}/auth/v1",
            klaim_ekstra={"role": "admin"},
        )
        klien = await buat_klien(app)
        respons = await klien.get("/uji", headers={"Authorization": f"Bearer {token}"})

        assert respons.status_code == 403
        assert respons.json()["galat"]["kode"] == PERAN_KURANG
    finally:
        ambil_pengaturan.cache_clear()


@pytest.mark.unit
async def test_dependensi_memanggil_service_lewat_objek_modul(
    monkeypatch: pytest.MonkeyPatch, buat_klien: PembuatKlien
) -> None:
    """Penjaga seam: tambalan pada `src.auth.service` HARUS mengenai dependensi.

    `dependencies.py` memanggil `service.verifikasi_token` dan
    `service.ambil_peran_profil` lewat objek modul, bukan lewat from-import.
    Kalau seseorang mengubahnya menjadi `from src.auth.service import ...`,
    nama itu ter-bind saat impor dan tambalan monkeypatch tidak lagi
    mengenainya — seluruh uji auth akan tetap hijau sambil benar-benar
    memanggil JWKS dan PostgREST Supabase asli. Uji ini gagal bila itu terjadi.
    """
    pasang_env_supabase(monkeypatch)
    import src.auth.dependencies as dep
    import src.auth.service as auth

    dipanggil: list[str] = []

    def _verifikasi_palsu(token: str, pengaturan: Pengaturan) -> dict[str, Any]:
        dipanggil.append("verifikasi_token")
        return {"sub": SUB_UJI}

    async def _peran_palsu(
        klien: Any, pengaturan: Pengaturan, id_pengguna: str
    ) -> str | None:
        dipanggil.append("ambil_peran_profil")
        return "tamu"

    monkeypatch.setattr(auth, "verifikasi_token", _verifikasi_palsu)
    monkeypatch.setattr(auth, "ambil_peran_profil", _peran_palsu)

    app = app_uji(dep.wajib_tamu)
    app.state.klien_supabase = None  # tak boleh dipakai: keduanya ditambal

    klien = await buat_klien(app, lifespan=True)
    respons = await klien.get("/uji", headers={"Authorization": "Bearer apa-saja"})

    assert respons.status_code == 200
    assert dipanggil == ["verifikasi_token", "ambil_peran_profil"]


@pytest.mark.integration
async def test_wajib_peran_mengembalikan_identitas_id_dan_peran(
    monkeypatch: pytest.MonkeyPatch,
    buat_token: Callable[..., str],
    kunci_es256: tuple[str, Any],
    buat_klien: PembuatKlien,
) -> None:
    """`wajib_peran` mengembalikan `Identitas` (id dari `sub`, peran dari `profil`)."""
    pasang_env_supabase(monkeypatch)
    import src.auth.dependencies as dep
    import src.auth.service as auth

    _, kunci_publik = kunci_es256
    monkeypatch.setattr(
        auth, "_kunci_penandatangan", lambda token, pengaturan: kunci_publik
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[{"peran": "tamu"}])

    app = FastAPI()
    daftarkan_handler(app)

    @app.get("/uji")
    async def _rute(
        identitas: Identitas = Depends(dep.wajib_tamu),  # noqa: B008
    ) -> dict[str, str]:
        return {"id": identitas.id, "peran": identitas.peran}

    app.state.klien_supabase = klien_mock(handler)

    try:
        token = buat_token(SUB_UJI, iss=f"{SUPABASE_URL_UJI}/auth/v1")
        klien = await buat_klien(app)
        respons = await klien.get("/uji", headers={"Authorization": f"Bearer {token}"})

        assert respons.status_code == 200
        assert respons.json() == {"id": SUB_UJI, "peran": "tamu"}
    finally:
        ambil_pengaturan.cache_clear()


@pytest.mark.integration
async def test_wajib_admin_profil_admin_200(
    monkeypatch: pytest.MonkeyPatch,
    buat_token: Callable[..., str],
    kunci_es256: tuple[str, Any],
    buat_klien: PembuatKlien,
) -> None:
    pasang_env_supabase(monkeypatch)
    import src.auth.dependencies as dep
    import src.auth.service as auth

    _, kunci_publik = kunci_es256
    monkeypatch.setattr(
        auth, "_kunci_penandatangan", lambda token, pengaturan: kunci_publik
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[{"peran": "admin"}])

    app = app_uji(dep.wajib_admin)
    app.state.klien_supabase = klien_mock(handler)

    try:
        token = buat_token(SUB_UJI, iss=f"{SUPABASE_URL_UJI}/auth/v1")
        klien = await buat_klien(app)
        respons = await klien.get("/uji", headers={"Authorization": f"Bearer {token}"})

        assert respons.status_code == 200
        assert respons.json() == {"ok": "ya"}
    finally:
        ambil_pengaturan.cache_clear()


@pytest.mark.integration
async def test_wajib_pemerintah_profil_swasta_403(
    monkeypatch: pytest.MonkeyPatch,
    buat_token: Callable[..., str],
    kunci_es256: tuple[str, Any],
    buat_klien: PembuatKlien,
) -> None:
    """Swasta satu-satunya pengecualian pewarisan peran (PRD §4) — laporan menolaknya."""
    pasang_env_supabase(monkeypatch)
    import src.auth.dependencies as dep
    import src.auth.service as auth

    _, kunci_publik = kunci_es256
    monkeypatch.setattr(
        auth, "_kunci_penandatangan", lambda token, pengaturan: kunci_publik
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[{"peran": "swasta"}])

    app = app_uji(dep.wajib_pemerintah)
    app.state.klien_supabase = klien_mock(handler)

    try:
        token = buat_token(SUB_UJI, iss=f"{SUPABASE_URL_UJI}/auth/v1")
        klien = await buat_klien(app)
        respons = await klien.get("/uji", headers={"Authorization": f"Bearer {token}"})

        assert respons.status_code == 403
        assert respons.json()["galat"]["kode"] == PERAN_KURANG
    finally:
        ambil_pengaturan.cache_clear()


@pytest.mark.integration
async def test_wajib_pemerintah_profil_pemerintah_200(
    monkeypatch: pytest.MonkeyPatch,
    buat_token: Callable[..., str],
    kunci_es256: tuple[str, Any],
    buat_klien: PembuatKlien,
) -> None:
    pasang_env_supabase(monkeypatch)
    import src.auth.dependencies as dep
    import src.auth.service as auth

    _, kunci_publik = kunci_es256
    monkeypatch.setattr(
        auth, "_kunci_penandatangan", lambda token, pengaturan: kunci_publik
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[{"peran": "pemerintah"}])

    app = app_uji(dep.wajib_pemerintah)
    app.state.klien_supabase = klien_mock(handler)

    try:
        token = buat_token(SUB_UJI, iss=f"{SUPABASE_URL_UJI}/auth/v1")
        klien = await buat_klien(app)
        respons = await klien.get("/uji", headers={"Authorization": f"Bearer {token}"})

        assert respons.status_code == 200
        assert respons.json() == {"ok": "ya"}
    finally:
        ambil_pengaturan.cache_clear()


@pytest.mark.integration
async def test_wajib_pemerintah_profil_admin_200(
    monkeypatch: pytest.MonkeyPatch,
    buat_token: Callable[..., str],
    kunci_es256: tuple[str, Any],
    buat_klien: PembuatKlien,
) -> None:
    pasang_env_supabase(monkeypatch)
    import src.auth.dependencies as dep
    import src.auth.service as auth

    _, kunci_publik = kunci_es256
    monkeypatch.setattr(
        auth, "_kunci_penandatangan", lambda token, pengaturan: kunci_publik
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[{"peran": "admin"}])

    app = app_uji(dep.wajib_pemerintah)
    app.state.klien_supabase = klien_mock(handler)

    try:
        token = buat_token(SUB_UJI, iss=f"{SUPABASE_URL_UJI}/auth/v1")
        klien = await buat_klien(app)
        respons = await klien.get("/uji", headers={"Authorization": f"Bearer {token}"})

        assert respons.status_code == 200
        assert respons.json() == {"ok": "ya"}
    finally:
        ambil_pengaturan.cache_clear()
