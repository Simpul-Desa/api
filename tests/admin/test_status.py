"""Uji integrasi rute `GET /api/admin/status` (Tugas 9, fase 7)."""

from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from src.admin import jobs
from src.admin.schemas import HasilPenyegaranDesa
from src.config import ambil_pengaturan
from tests.admin.bantu import aplikasi_admin, pasang_postgrest
from tests.conftest import D1, PembuatKlien

pytestmark = pytest.mark.anyio


def _handler_status(request: httpx.Request) -> httpx.Response:
    """Bedakan tiga panggilan PostgREST rute status lewat path + parameter `select`."""
    if request.url.path.endswith("/rest/v1/profil"):
        return httpx.Response(
            200, json=[{"id": "x"}], headers={"Content-Range": "0-0/3"}
        )
    if request.url.path.endswith("/rest/v1/berita_desa"):
        if request.url.params.get("select") == "id":
            return httpx.Response(
                200, json=[{"id": 1}], headers={"Content-Range": "0-0/18"}
            )
        return httpx.Response(
            200,
            json=[{"iddesa": D1, "dipanen_pada": "2026-09-07T10:02:03+00:00"}],
        )
    return httpx.Response(200, json=[])


@pytest.mark.integration
async def test_status_tanpa_pekerjaan_penyegaran_null(
    dir_data_lengkap: Path, env_admin: None, buat_klien: PembuatKlien
) -> None:
    app = aplikasi_admin()
    klien = await buat_klien(app, lifespan=True)
    pasang_postgrest(app, _handler_status)

    respons = await klien.get("/api/admin/status")

    assert respons.status_code == 200
    body = respons.json()["data"]
    assert body["penyegaran"] is None
    assert body["cacah"] == {"pengguna": 3, "berita": 18}
    assert body["penyegaran_terakhir"][0]["iddesa"] == D1
    assert body["versi_data"] == "uji123"
    assert body["tanggal_data"] == "2026-09-07"


@pytest.mark.integration
async def test_status_konfigurasi_boolean_tanpa_nilai_kunci(
    dir_data_lengkap: Path,
    env_admin: None,
    monkeypatch: pytest.MonkeyPatch,
    buat_klien: PembuatKlien,
) -> None:
    """`gemini_chat` (kunci Asisten Desa, fase 5) ikut jadi bendera boolean.

    `env_admin` sendiri hanya mengisi `GEMINI_API_KEY` (panen Berita Desa) —
    `GEMINI_API_KEY_CHAT` diisi eksplisit di sini, bukan diwariskan dari
    `.env` lokal, supaya nilainya deterministik lintas mesin pengembang.
    """
    monkeypatch.setenv("GEMINI_API_KEY_CHAT", "kunci-gemini-chat-uji")
    ambil_pengaturan.cache_clear()

    app = aplikasi_admin()
    klien = await buat_klien(app, lifespan=True)
    pasang_postgrest(app, _handler_status)

    respons = await klien.get("/api/admin/status")

    body = respons.json()["data"]
    assert body["konfigurasi"] == {
        "supabase": True,
        "gemini": True,
        "gemini_chat": True,
    }
    assert "kunci-uji" not in respons.text
    assert "kunci-gemini-uji" not in respons.text
    assert "kunci-gemini-chat-uji" not in respons.text


@pytest.mark.integration
async def test_status_postgrest_mati_kembalikan_503(
    dir_data_lengkap: Path, env_admin: None, buat_klien: PembuatKlien
) -> None:
    app = aplikasi_admin()
    klien = await buat_klien(app, lifespan=True)

    def _mati(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("PostgREST mati")

    pasang_postgrest(app, _mati)

    respons = await klien.get("/api/admin/status")

    assert respons.status_code == 503
    assert respons.json()["galat"]["kode"] == "DATA_BELUM_SIAP"


@pytest.mark.integration
async def test_status_header_cache_private_no_store_tanpa_etag(
    dir_data_lengkap: Path, env_admin: None, buat_klien: PembuatKlien
) -> None:
    app = aplikasi_admin()
    klien = await buat_klien(app, lifespan=True)
    pasang_postgrest(app, _handler_status)

    respons = await klien.get("/api/admin/status")

    assert respons.status_code == 200
    assert respons.headers["cache-control"] == "private, no-store"
    assert "etag" not in respons.headers


@pytest.mark.integration
async def test_status_dengan_pekerjaan_melaporkan_kemajuan_dan_hasil_per_desa(
    dir_data_lengkap: Path, env_admin: None, buat_klien: PembuatKlien
) -> None:
    """Bentuk `penyegaran` yang dipolling admin setelah 202 — bukan hanya `null`.

    Pekerjaan dipasang SETELAH lifespan berjalan: lifespan mengisi
    `app.state.pekerjaan_penyegaran` dengan None, jadi memasangnya lebih dulu
    akan tertimpa.
    """
    app = aplikasi_admin()
    klien = await buat_klien(app, lifespan=True)
    pasang_postgrest(app, _handler_status)

    mulai_pada = datetime(2026, 9, 7, 10, 0, 0, tzinfo=UTC)
    app.state.pekerjaan_penyegaran = jobs.Pekerjaan(
        id_pekerjaan="9f2c",
        keadaan="berjalan",
        total=2,
        selesai=1,
        mulai_pada=mulai_pada,
        selesai_pada=None,
        hasil=(
            HasilPenyegaranDesa(
                iddesa=D1, n_baru=9, n_duplikat=0, n_dibuang=1, n_gagal=3, galat=None
            ),
        ),
    )

    respons = await klien.get("/api/admin/status")

    assert respons.status_code == 200
    penyegaran = respons.json()["data"]["penyegaran"]
    assert penyegaran["id_pekerjaan"] == "9f2c"
    assert penyegaran["keadaan"] == "berjalan"
    assert penyegaran["total"] == 2
    assert penyegaran["selesai"] == 1
    assert penyegaran["selesai_pada"] is None
    assert penyegaran["hasil"] == [
        {
            "iddesa": D1,
            "n_baru": 9,
            "n_duplikat": 0,
            "n_dibuang": 1,
            "n_gagal": 3,  # FIX 1: n_gagal harus tersaji lewat /api/admin/status
            "galat": None,
        }
    ]
