"""Uji integrasi rute Berita Desa (`src/berita/router.py`, fase 6).

PostgREST distub lewat penggantian `app.state.klien_supabase` dengan
`AsyncClient` bertransport tiruan — lifespan tetap berjalan normal.
Dependensi peran `wajib_tamu` sudah di-override tamu oleh fixture `klien`;
matriks akses rute ini diuji di `test_matriks_akses.py`.
"""

from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI

from src.config import ambil_pengaturan
from tests.conftest import D1

pytestmark = pytest.mark.anyio

IDDESA_POLA_SALAH = "180104000"  # 9 digit
IDDESA_TAK_DIKENAL = "1801049999"  # 10 digit, tak ada di indeks kartu

_BARIS_BERITA = [
    {
        "id": 1,
        "judul": "Desa untung dari wisata",
        "url": "https://p.id/1",
        "sumber": "Contoh News",
        "terbit_pada": "2026-09-02T03:00:00+00:00",
        "dipanen_pada": "2026-09-07T03:00:00+00:00",
        "rangkuman": "Rangkuman Gemini.",
        "kategori": ["Wisata"],
        "perangkum": "gemini",
    },
    {
        "id": 2,
        "judul": "BUMDes panen kopi",
        "url": "https://p.id/2",
        "sumber": "Kopi News",
        "terbit_pada": "2026-09-01T03:00:00+00:00",
        "dipanen_pada": "2026-09-07T03:00:00+00:00",
        "rangkuman": "Rangkuman ekstraktif.",
        "kategori": [],
        "perangkum": "ekstraktif",
    },
    {
        "id": 3,
        "judul": "Galeri desa",
        "url": "https://p.id/3",
        "sumber": "Foto News",
        "terbit_pada": None,
        "dipanen_pada": "2026-09-07T03:00:00+00:00",
        "rangkuman": None,
        "kategori": [],
        "perangkum": "judul-rss",
    },
]


@pytest.fixture
def env_supabase(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Isi env Supabase uji supaya URL PostgREST rute berita terbentuk sah."""
    monkeypatch.setenv("SUPABASE_URL", "https://uji.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "kunci-uji")
    ambil_pengaturan.cache_clear()

    yield

    ambil_pengaturan.cache_clear()


def _pasang_postgrest(aplikasi: FastAPI) -> list[httpx.Request]:
    """Ganti `klien_supabase` dengan transport tiruan berisi `_BARIS_BERITA`."""
    tangkapan: list[httpx.Request] = []

    def _handler(request: httpx.Request) -> httpx.Response:
        tangkapan.append(request)
        return httpx.Response(200, json=_BARIS_BERITA)

    aplikasi.state.klien_supabase = httpx.AsyncClient(
        transport=httpx.MockTransport(_handler)
    )
    return tangkapan


@pytest.mark.integration
async def test_berita_iddesa_pola_salah_kembalikan_422(
    dir_data_lengkap: Path, env_supabase: None, klien: httpx.AsyncClient
) -> None:
    respons = await klien.get(f"/api/berita/{IDDESA_POLA_SALAH}")

    assert respons.status_code == 422
    assert respons.json()["galat"]["kode"] == "PARAMETER_TIDAK_VALID"


@pytest.mark.integration
async def test_berita_iddesa_tak_dikenal_kembalikan_404(
    dir_data_lengkap: Path, env_supabase: None, klien: httpx.AsyncClient
) -> None:
    respons = await klien.get(f"/api/berita/{IDDESA_TAK_DIKENAL}")

    assert respons.status_code == 404
    assert respons.json()["galat"]["kode"] == "DESA_TIDAK_ADA"


@pytest.mark.integration
async def test_berita_desa_sah_tanpa_berita_daftar_kosong_bukan_404(
    dir_data_lengkap: Path,
    env_supabase: None,
    klien: httpx.AsyncClient,
    aplikasi: FastAPI,
) -> None:
    aplikasi.state.klien_supabase = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, json=[]))
    )

    respons = await klien.get(f"/api/berita/{D1}")

    assert respons.status_code == 200
    body = respons.json()
    assert body["sukses"] is True
    assert body["data"] == []
    assert body["meta"]["total"] == 0


@pytest.mark.integration
async def test_berita_sukses_berisi_dan_parameter_postgrest_benar(
    dir_data_lengkap: Path,
    env_supabase: None,
    klien: httpx.AsyncClient,
    aplikasi: FastAPI,
) -> None:
    tangkapan = _pasang_postgrest(aplikasi)

    respons = await klien.get(f"/api/berita/{D1}")

    assert respons.status_code == 200
    body = respons.json()
    assert body["meta"]["total"] == 3
    assert [b["url"] for b in body["data"]] == [
        "https://p.id/1",
        "https://p.id/2",
        "https://p.id/3",
    ]
    assert [b["id"] for b in body["data"]] == [1, 2, 3]
    assert body["data"][2]["terbit_pada"] is None
    assert body["data"][2]["rangkuman"] is None

    permintaan = tangkapan[0]
    assert permintaan.url.params["iddesa"] == f"eq.{D1}"
    assert permintaan.url.params["order"] == "terbit_pada.desc.nullslast"
    assert permintaan.headers["apikey"] == "kunci-uji"
    assert permintaan.url.params["select"].startswith("id,")


@pytest.mark.integration
async def test_berita_paginasi_memotong_dan_mengisi_meta(
    dir_data_lengkap: Path,
    env_supabase: None,
    klien: httpx.AsyncClient,
    aplikasi: FastAPI,
) -> None:
    _pasang_postgrest(aplikasi)

    respons = await klien.get(f"/api/berita/{D1}?hal=2&batas=2")

    body = respons.json()
    assert body["meta"] == {"total": 3, "hal": 2, "batas": 2, "parameter": None}
    assert [b["url"] for b in body["data"]] == ["https://p.id/3"]


@pytest.mark.integration
async def test_berita_postgrest_mati_kembalikan_503(
    dir_data_lengkap: Path,
    env_supabase: None,
    klien: httpx.AsyncClient,
    aplikasi: FastAPI,
) -> None:
    def _mati(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("PostgREST mati")

    aplikasi.state.klien_supabase = httpx.AsyncClient(
        transport=httpx.MockTransport(_mati)
    )

    respons = await klien.get(f"/api/berita/{D1}")

    assert respons.status_code == 503
    assert respons.json()["galat"]["kode"] == "DATA_BELUM_SIAP"


@pytest.mark.integration
async def test_berita_balasan_bukan_daftar_kembalikan_503(
    dir_data_lengkap: Path,
    env_supabase: None,
    klien: httpx.AsyncClient,
    aplikasi: FastAPI,
) -> None:
    aplikasi.state.klien_supabase = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda r: httpx.Response(200, json={"message": "rusak"})
        )
    )

    respons = await klien.get(f"/api/berita/{D1}")

    assert respons.status_code == 503
    assert respons.json()["galat"]["kode"] == "DATA_BELUM_SIAP"


@pytest.mark.integration
async def test_berita_header_cache_private_no_store(
    dir_data_lengkap: Path,
    env_supabase: None,
    klien: httpx.AsyncClient,
    aplikasi: FastAPI,
) -> None:
    """PRD §5: berita selalu no-store — prefiks masuk PREFIKS_TANPA_CACHE."""
    _pasang_postgrest(aplikasi)

    respons = await klien.get(f"/api/berita/{D1}")

    assert respons.status_code == 200
    assert respons.headers["cache-control"] == "private, no-store"
    assert "etag" not in respons.headers
