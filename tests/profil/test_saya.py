"""Uji integrasi rute `GET /api/profil/saya` (`src/profil/router.py`, fase 2 auth).

Beda dari fixture `klien` bersama (yang meng-override `wajib_tamu` menjadi
tamu tetap), seluruh uji di berkas ini memakai aplikasi TANPA override:
verifikasi token dan pembacaan peran berjalan sungguhan, hanya kunci JWKS
dan lookup PostgREST-nya yang distub — pola sama seperti
`tests/auth/test_matriks_akses.py`.
"""

from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest

import src.auth.service
from src.config import Pengaturan, ambil_pengaturan
from src.main import create_app
from tests.conftest import PembuatKlien

pytestmark = pytest.mark.anyio

SUPABASE_URL_UJI = "https://uji.supabase.co"

SUB_TAMU = "00000000-0000-0000-0000-000000000001"
SUB_PEMERINTAH = "00000000-0000-0000-0000-000000000002"
SUB_SWASTA = "00000000-0000-0000-0000-000000000003"
SUB_ADMIN = "00000000-0000-0000-0000-000000000004"
SUB_TANPA_PROFIL = "00000000-0000-0000-0000-000000000009"

_PERAN_PER_SUB: dict[str, str] = {
    SUB_TAMU: "tamu",
    SUB_PEMERINTAH: "pemerintah",
    SUB_SWASTA: "swasta",
    SUB_ADMIN: "admin",
}


async def _peran_stub(
    klien: httpx.AsyncClient, pengaturan: Pengaturan, id_pengguna: str
) -> str | None:
    """Stub `ambil_peran_profil`: baca peta di memori, tanpa jaringan."""
    return _PERAN_PER_SUB.get(id_pengguna)


@pytest.fixture
def auth_stub(
    monkeypatch: pytest.MonkeyPatch, kunci_es256: tuple[str, Any]
) -> Iterator[None]:
    """Stub kunci JWKS + lookup profil dan isi env Supabase uji.

    Verifikasi tanda tangan, aud, iss, dan exp tetap berjalan sungguhan
    lewat `verifikasi_token` — hanya sumber kunci dan PostgREST yang diganti.
    """
    _, kunci_publik = kunci_es256
    monkeypatch.setattr(
        src.auth.service,
        "_kunci_penandatangan",
        lambda token, pengaturan: kunci_publik,
    )
    monkeypatch.setattr(src.auth.service, "ambil_peran_profil", _peran_stub)
    monkeypatch.setenv("SUPABASE_URL", SUPABASE_URL_UJI)
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "kunci-uji")
    ambil_pengaturan.cache_clear()

    yield

    ambil_pengaturan.cache_clear()


@pytest.fixture
async def klien_profil(
    dir_data_manifest: Path, auth_stub: None, buat_klien: PembuatKlien
) -> httpx.AsyncClient:
    """Klien aplikasi nyata TANPA override dependensi peran."""
    app = create_app()
    return await buat_klien(app, lifespan=True)


def _header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.integration
async def test_tanpa_header_authorization_kembalikan_401(
    klien_profil: httpx.AsyncClient,
) -> None:
    respons = await klien_profil.get("/api/profil/saya")

    assert respons.status_code == 401
    body = respons.json()
    assert body["sukses"] is False
    assert body["galat"]["kode"] == "TIDAK_BERWENANG"


@pytest.mark.integration
@pytest.mark.parametrize(
    "sub, peran",
    [
        (SUB_TAMU, "tamu"),
        (SUB_PEMERINTAH, "pemerintah"),
        (SUB_SWASTA, "swasta"),
        (SUB_ADMIN, "admin"),
    ],
)
async def test_token_sah_kembalikan_id_dan_peran_dari_profil(
    sub: str,
    peran: str,
    klien_profil: httpx.AsyncClient,
    buat_token: Callable[..., str],
) -> None:
    token = buat_token(sub)

    respons = await klien_profil.get("/api/profil/saya", headers=_header(token))

    assert respons.status_code == 200
    body = respons.json()
    assert body["sukses"] is True
    assert body["data"]["id"] == sub
    assert body["data"]["peran"] == peran


@pytest.mark.integration
async def test_token_sah_tanpa_baris_profil_kembalikan_403(
    klien_profil: httpx.AsyncClient, buat_token: Callable[..., str]
) -> None:
    token = buat_token(SUB_TANPA_PROFIL)

    respons = await klien_profil.get("/api/profil/saya", headers=_header(token))

    assert respons.status_code == 403
    assert respons.json()["galat"]["kode"] == "PERAN_KURANG"


@pytest.mark.integration
async def test_respons_berheader_private_no_store_tanpa_etag(
    klien_profil: httpx.AsyncClient, buat_token: Callable[..., str]
) -> None:
    respons = await klien_profil.get(
        "/api/profil/saya", headers=_header(buat_token(SUB_TAMU))
    )

    assert respons.status_code == 200
    assert respons.headers["cache-control"] == "private, no-store"
    assert "etag" not in respons.headers


@pytest.mark.integration
async def test_origin_selain_origin_app_tidak_dapat_header_cors(
    klien_profil: httpx.AsyncClient, buat_token: Callable[..., str]
) -> None:
    respons = await klien_profil.get(
        "/api/profil/saya",
        headers={
            **_header(buat_token(SUB_TAMU)),
            "Origin": "https://asing.acak",
        },
    )

    assert respons.status_code == 200
    assert "access-control-allow-origin" not in respons.headers
