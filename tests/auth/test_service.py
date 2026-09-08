"""Uji verifikasi JWT Supabase dan pembacaan peran (`src/auth/service.py`)."""

import logging
from collections.abc import Callable
from typing import Any

import httpx
import jwt
import pytest

from src.exceptions import (
    AUTH_BELUM_SIAP,
    PERAN_TIDAK_DIKENAL,
    TIDAK_BERWENANG,
    GalatAPI,
)
from tests.auth.bantu import (
    SUB_UJI,
    SUPABASE_URL_UJI,
    klien_mock,
    pengaturan_uji,
)

pytestmark = pytest.mark.anyio


@pytest.mark.unit
def test_verifikasi_token_sah_mengembalikan_klaim(
    monkeypatch: pytest.MonkeyPatch,
    buat_token: Callable[..., str],
    kunci_es256: tuple[str, Any],
) -> None:
    import src.auth.service as auth

    _, kunci_publik = kunci_es256
    monkeypatch.setattr(
        auth, "_kunci_penandatangan", lambda token, pengaturan: kunci_publik
    )
    token = buat_token(SUB_UJI, iss=f"{SUPABASE_URL_UJI}/auth/v1")

    klaim = auth.verifikasi_token(token, pengaturan_uji())

    assert klaim["sub"] == SUB_UJI


@pytest.mark.unit
def test_verifikasi_token_kedaluwarsa_401(
    monkeypatch: pytest.MonkeyPatch,
    buat_token: Callable[..., str],
    kunci_es256: tuple[str, Any],
) -> None:
    import src.auth.service as auth

    _, kunci_publik = kunci_es256
    monkeypatch.setattr(
        auth, "_kunci_penandatangan", lambda token, pengaturan: kunci_publik
    )
    token = buat_token(SUB_UJI, iss=f"{SUPABASE_URL_UJI}/auth/v1", exp_detik=-10)

    with pytest.raises(GalatAPI) as info:
        auth.verifikasi_token(token, pengaturan_uji())

    assert info.value.status == 401
    assert info.value.kode == TIDAK_BERWENANG


@pytest.mark.unit
def test_verifikasi_token_audience_salah_401(
    monkeypatch: pytest.MonkeyPatch,
    buat_token: Callable[..., str],
    kunci_es256: tuple[str, Any],
) -> None:
    import src.auth.service as auth

    _, kunci_publik = kunci_es256
    monkeypatch.setattr(
        auth, "_kunci_penandatangan", lambda token, pengaturan: kunci_publik
    )
    token = buat_token(SUB_UJI, iss=f"{SUPABASE_URL_UJI}/auth/v1", aud="lain")

    with pytest.raises(GalatAPI) as info:
        auth.verifikasi_token(token, pengaturan_uji())

    assert info.value.status == 401
    assert info.value.kode == TIDAK_BERWENANG


@pytest.mark.unit
def test_verifikasi_token_issuer_salah_401(
    monkeypatch: pytest.MonkeyPatch,
    buat_token: Callable[..., str],
    kunci_es256: tuple[str, Any],
) -> None:
    import src.auth.service as auth

    _, kunci_publik = kunci_es256
    monkeypatch.setattr(
        auth, "_kunci_penandatangan", lambda token, pengaturan: kunci_publik
    )
    token = buat_token(SUB_UJI, iss="https://bukan-punya-kita.supabase.co/auth/v1")

    with pytest.raises(GalatAPI) as info:
        auth.verifikasi_token(token, pengaturan_uji())

    assert info.value.status == 401
    assert info.value.kode == TIDAK_BERWENANG


@pytest.mark.unit
def test_verifikasi_token_string_sampah_401(
    monkeypatch: pytest.MonkeyPatch,
    kunci_es256: tuple[str, Any],
) -> None:
    import src.auth.service as auth

    _, kunci_publik = kunci_es256
    monkeypatch.setattr(
        auth, "_kunci_penandatangan", lambda token, pengaturan: kunci_publik
    )

    with pytest.raises(GalatAPI) as info:
        auth.verifikasi_token("bukan.token.jwt", pengaturan_uji())

    assert info.value.status == 401
    assert info.value.kode == TIDAK_BERWENANG


@pytest.mark.unit
def test_verifikasi_token_kedaluwarsa_log_tanpa_traceback(
    monkeypatch: pytest.MonkeyPatch,
    buat_token: Callable[..., str],
    kunci_es256: tuple[str, Any],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Token kedaluwarsa (volume tinggi, diharapkan) tidak mengubah kontrak 401.

    Dicatat, tapi TANPA traceback: ini bukan bug kita, jadi tidak perlu
    membanjiri log dengan `exc_info` untuk setiap token basi/palsu yang
    sekadar lewat lalu lintas normal.
    """
    import src.auth.service as auth

    _, kunci_publik = kunci_es256
    monkeypatch.setattr(
        auth, "_kunci_penandatangan", lambda token, pengaturan: kunci_publik
    )
    token = buat_token(SUB_UJI, iss=f"{SUPABASE_URL_UJI}/auth/v1", exp_detik=-10)

    with caplog.at_level(logging.DEBUG), pytest.raises(GalatAPI) as info:
        auth.verifikasi_token(token, pengaturan_uji())

    assert info.value.status == 401
    assert info.value.kode == TIDAK_BERWENANG
    assert info.value.pesan == "token tidak sah"
    assert any(
        record.exc_info is None and record.levelno <= logging.INFO
        for record in caplog.records
    )


@pytest.mark.unit
def test_verifikasi_token_kunci_rusak_log_dengan_traceback(
    monkeypatch: pytest.MonkeyPatch,
    buat_token: Callable[..., str],
    kunci_es256: tuple[str, Any],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """`_kunci_penandatangan` yang mengembalikan objek bukan kunci = bug kita.

    PyJWT melempar `TypeError`/`ValueError` (bukan `InvalidTokenError`) kalau
    kuncinya cacat - itu bug di jalur kunci kita, bukan token forgeri, jadi
    HARUS tercatat dengan traceback (`exc_info=True`) supaya tidak
    tak-terbedakan selamanya dari token palsu biasa.
    """
    import src.auth.service as auth

    monkeypatch.setattr(auth, "_kunci_penandatangan", lambda token, pengaturan: 12345)
    token = buat_token(SUB_UJI, iss=f"{SUPABASE_URL_UJI}/auth/v1")

    with caplog.at_level(logging.DEBUG), pytest.raises(GalatAPI) as info:
        auth.verifikasi_token(token, pengaturan_uji())

    assert info.value.status == 401
    assert info.value.kode == TIDAK_BERWENANG
    assert info.value.pesan == "token tidak sah"
    assert any(record.exc_info is not None for record in caplog.records)


@pytest.mark.unit
async def test_ambil_peran_profil_baris_ada_mengembalikan_peran() -> None:
    import src.auth.service as auth

    permintaan_tercatat: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        permintaan_tercatat.append(request)
        return httpx.Response(200, json=[{"peran": "tamu"}])

    async with klien_mock(handler) as klien:
        peran = await auth.ambil_peran_profil(klien, pengaturan_uji(), SUB_UJI)

    assert peran == "tamu"
    assert len(permintaan_tercatat) == 1
    permintaan = permintaan_tercatat[0]
    assert permintaan.headers["apikey"] == "kunci-uji"
    assert permintaan.url.params["id"] == f"eq.{SUB_UJI}"
    assert permintaan.url.params["select"] == "peran"


@pytest.mark.unit
async def test_ambil_peran_profil_baris_kosong_mengembalikan_none() -> None:
    import src.auth.service as auth

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[])

    async with klien_mock(handler) as klien:
        peran = await auth.ambil_peran_profil(klien, pengaturan_uji(), SUB_UJI)

    assert peran is None


@pytest.mark.unit
async def test_ambil_peran_profil_status_500_503() -> None:
    import src.auth.service as auth

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"pesan": "rusak"})

    async with klien_mock(handler) as klien:
        with pytest.raises(GalatAPI) as info:
            await auth.ambil_peran_profil(klien, pengaturan_uji(), SUB_UJI)

    assert info.value.status == 503
    assert info.value.kode == AUTH_BELUM_SIAP


@pytest.mark.unit
async def test_ambil_peran_profil_id_bukan_uuid_401_tanpa_panggil_jaringan() -> None:
    import src.auth.service as auth

    dipanggil = False

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal dipanggil
        dipanggil = True
        return httpx.Response(200, json=[])

    async with klien_mock(handler) as klien:
        with pytest.raises(GalatAPI) as info:
            await auth.ambil_peran_profil(klien, pengaturan_uji(), "bukan-uuid")

    assert info.value.status == 401
    assert info.value.kode == TIDAK_BERWENANG
    assert dipanggil is False


@pytest.mark.unit
def test_verifikasi_token_tanpa_exp_ditolak_401(
    monkeypatch: pytest.MonkeyPatch, kunci_es256: tuple[str, Any]
) -> None:
    """Klaim `exp` wajib ada (RFC 8725 §3.8) — token tanpa exp bukan token sah."""
    import time as _time

    import src.auth.service as auth

    pem_privat, kunci_publik = kunci_es256
    monkeypatch.setattr(
        auth, "_kunci_penandatangan", lambda token, pengaturan: kunci_publik
    )
    token = jwt.encode(
        {
            "sub": SUB_UJI,
            "aud": "authenticated",
            "iss": f"{SUPABASE_URL_UJI}/auth/v1",
            "iat": int(_time.time()),
        },
        pem_privat,
        algorithm="ES256",
    )

    with pytest.raises(GalatAPI) as info:
        auth.verifikasi_token(token, pengaturan_uji())

    assert info.value.status == 401


@pytest.mark.unit
def test_verifikasi_token_jalur_jwks_nyata(
    monkeypatch: pytest.MonkeyPatch,
    kunci_es256: tuple[str, Any],
    buat_token: Callable[..., str],
) -> None:
    """Jalur JWKS sungguhan (`_klien_jwks` + `_kunci_penandatangan`) berjalan.

    `PyJWKClient.fetch_data` distub mengembalikan JWK set berisi kunci publik
    uji — tanpa jaringan; sisanya (pencocokan `kid`, pemilihan kunci, decode)
    memakai kode produksi asli.
    """
    import json as _json

    import src.auth.service as auth

    _, kunci_publik = kunci_es256
    jwk = _json.loads(jwt.algorithms.ECAlgorithm.to_jwk(kunci_publik))
    jwk["kid"] = "kunci-uji"
    monkeypatch.setattr(jwt.PyJWKClient, "fetch_data", lambda self: {"keys": [jwk]})
    auth._klien_jwks.cache_clear()

    try:
        token = buat_token(SUB_UJI, iss=f"{SUPABASE_URL_UJI}/auth/v1")
        klaim = auth.verifikasi_token(token, pengaturan_uji())
    finally:
        auth._klien_jwks.cache_clear()

    assert klaim["sub"] == SUB_UJI


@pytest.mark.unit
async def test_ambil_peran_profil_peran_asing_403() -> None:
    """Nilai peran di luar empat peran sah divalidasi di batas -> 403.

    Ini bukan outage: PostgREST menjawab normal, cuma satu baris berisi
    nilai peran yang tidak dikenal kode (`PERAN_TIDAK_DIKENAL`), bukan
    kegagalan layanan (`AUTH_BELUM_SIAP`/503).
    """
    import src.auth.service as auth

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[{"peran": "penyusup"}])

    async with klien_mock(handler) as klien:
        with pytest.raises(GalatAPI) as info:
            await auth.ambil_peran_profil(klien, pengaturan_uji(), SUB_UJI)

    assert info.value.status == 403
    assert info.value.kode == PERAN_TIDAK_DIKENAL


@pytest.mark.unit
async def test_ambil_peran_profil_peran_asing_log_memuat_id_dan_nilai(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Log peran asing harus bisa dipakai menemukan baris pelakunya.

    Status publik berubah ke 403 `PERAN_TIDAK_DIKENAL` (bukan lagi 503
    `AUTH_BELUM_SIAP` — ini bukan outage, lihat FIX 2); pesan publik TIDAK
    boleh membocorkan nilai perannya ("raja") ke pemanggil. Nilai itu hanya
    boleh muncul di log operator, bersama id pengguna, supaya baris
    pelakunya bisa dicari tanpa menduga-duga layanan mati.
    """
    import src.auth.service as auth

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[{"peran": "raja"}])

    async with klien_mock(handler) as klien:
        with caplog.at_level(logging.WARNING):
            with pytest.raises(GalatAPI) as info:
                await auth.ambil_peran_profil(klien, pengaturan_uji(), SUB_UJI)

    assert info.value.status == 403
    assert info.value.kode == PERAN_TIDAK_DIKENAL
    assert "raja" not in info.value.pesan
    assert any(
        SUB_UJI in record.getMessage() and "raja" in record.getMessage()
        for record in caplog.records
    )


@pytest.mark.unit
async def test_ambil_peran_profil_balasan_bukan_daftar_503() -> None:
    """Balasan PostgREST berbentuk objek galat (bukan daftar) -> 503, bukan 500."""
    import src.auth.service as auth

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"message": "galat postgrest"})

    async with klien_mock(handler) as klien:
        with pytest.raises(GalatAPI) as info:
            await auth.ambil_peran_profil(klien, pengaturan_uji(), SUB_UJI)

    assert info.value.status == 503
    assert info.value.kode == AUTH_BELUM_SIAP
