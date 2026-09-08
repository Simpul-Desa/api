"""Uji integrasi rute `DELETE /api/admin/berita/{id_berita}` (Tugas 9, fase 7)."""

from pathlib import Path

import httpx
import pytest

from tests.admin.bantu import aplikasi_admin, pasang_postgrest
from tests.conftest import PembuatKlien

pytestmark = pytest.mark.anyio


@pytest.mark.integration
async def test_hapus_berita_id_ada_kembalikan_200_dan_terhapus_true(
    dir_data_lengkap: Path, env_admin: None, buat_klien: PembuatKlien
) -> None:
    app = aplikasi_admin()
    klien = await buat_klien(app, lifespan=True)
    tangkapan = pasang_postgrest(app, lambda r: httpx.Response(200, json=[{"id": 42}]))

    respons = await klien.delete("/api/admin/berita/42")

    assert respons.status_code == 200
    body = respons.json()
    assert body["sukses"] is True
    assert body["data"] == {"id": 42, "terhapus": True}
    assert tangkapan[0].method == "DELETE"
    assert tangkapan[0].url.params["id"] == "eq.42"


@pytest.mark.integration
async def test_hapus_berita_id_tidak_ada_kembalikan_404(
    dir_data_lengkap: Path, env_admin: None, buat_klien: PembuatKlien
) -> None:
    app = aplikasi_admin()
    klien = await buat_klien(app, lifespan=True)
    pasang_postgrest(app, lambda r: httpx.Response(200, json=[]))

    respons = await klien.delete("/api/admin/berita/999")

    assert respons.status_code == 404
    assert respons.json()["galat"]["kode"] == "BERITA_TIDAK_ADA"


@pytest.mark.integration
async def test_hapus_berita_id_nol_kembalikan_422(
    dir_data_lengkap: Path, env_admin: None, buat_klien: PembuatKlien
) -> None:
    app = aplikasi_admin()
    klien = await buat_klien(app, lifespan=True)

    respons = await klien.delete("/api/admin/berita/0")

    assert respons.status_code == 422
    assert respons.json()["galat"]["kode"] == "PARAMETER_TIDAK_VALID"


@pytest.mark.integration
async def test_hapus_berita_postgrest_mati_kembalikan_503(
    dir_data_lengkap: Path, env_admin: None, buat_klien: PembuatKlien
) -> None:
    app = aplikasi_admin()
    klien = await buat_klien(app, lifespan=True)

    def _mati(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("PostgREST mati")

    pasang_postgrest(app, _mati)

    respons = await klien.delete("/api/admin/berita/1")

    assert respons.status_code == 503
    assert respons.json()["galat"]["kode"] == "DATA_BELUM_SIAP"
