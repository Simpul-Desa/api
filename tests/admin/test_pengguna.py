"""Uji integrasi rute `GET /api/admin/pengguna` dan ubah peran (Tugas 9, fase 7)."""

from pathlib import Path

import httpx
import pytest

from src.auth.dependencies import wajib_admin
from src.auth.schemas import Identitas
from tests.admin.bantu import ID_ADMIN, ID_LAIN, aplikasi_admin, pasang_postgrest
from tests.conftest import PembuatKlien

pytestmark = pytest.mark.anyio

_BARIS_PENGGUNA = [
    {
        "id": ID_ADMIN,
        "email": "admin@contoh.id",
        "peran": "admin",
        "dibuat_pada": "2026-09-07T03:00:00+00:00",
        "diubah_pada": "2026-09-07T03:00:00+00:00",
    },
]


@pytest.mark.integration
async def test_daftar_pengguna_tanpa_q_kembalikan_200_dan_meta_total(
    dir_data_lengkap: Path, env_admin: None, buat_klien: PembuatKlien
) -> None:
    app = aplikasi_admin()
    klien = await buat_klien(app, lifespan=True)
    pasang_postgrest(
        app,
        lambda r: httpx.Response(
            200, json=_BARIS_PENGGUNA, headers={"Content-Range": "0-0/1"}
        ),
    )

    respons = await klien.get("/api/admin/pengguna")

    assert respons.status_code == 200
    body = respons.json()
    assert body["sukses"] is True
    assert body["meta"]["total"] == 1
    assert body["data"][0]["id"] == ID_ADMIN


@pytest.mark.integration
async def test_daftar_pengguna_dengan_q_kirim_parameter_ilike(
    dir_data_lengkap: Path, env_admin: None, buat_klien: PembuatKlien
) -> None:
    app = aplikasi_admin()
    klien = await buat_klien(app, lifespan=True)
    tangkapan = pasang_postgrest(
        app,
        lambda r: httpx.Response(
            200, json=_BARIS_PENGGUNA, headers={"Content-Range": "0-0/1"}
        ),
    )

    respons = await klien.get("/api/admin/pengguna?q=ade")

    assert respons.status_code == 200
    assert tangkapan[0].url.params["email"] == "ilike.*ade*"


@pytest.mark.integration
async def test_daftar_pengguna_q_karakter_terlarang_kembalikan_422(
    dir_data_lengkap: Path, env_admin: None, buat_klien: PembuatKlien
) -> None:
    app = aplikasi_admin()
    klien = await buat_klien(app, lifespan=True)

    respons = await klien.get("/api/admin/pengguna?q=a,b")

    assert respons.status_code == 422


@pytest.mark.integration
async def test_daftar_pengguna_postgrest_mati_kembalikan_503(
    dir_data_lengkap: Path, env_admin: None, buat_klien: PembuatKlien
) -> None:
    app = aplikasi_admin()
    klien = await buat_klien(app, lifespan=True)

    def _mati(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("PostgREST mati")

    pasang_postgrest(app, _mati)

    respons = await klien.get("/api/admin/pengguna")

    assert respons.status_code == 503
    assert respons.json()["galat"]["kode"] == "DATA_BELUM_SIAP"


@pytest.mark.integration
async def test_ubah_peran_diri_sendiri_kembalikan_403_tanpa_permintaan_postgrest(
    dir_data_lengkap: Path, env_admin: None, buat_klien: PembuatKlien
) -> None:
    app = aplikasi_admin()
    klien = await buat_klien(app, lifespan=True)
    tangkapan = pasang_postgrest(
        app, lambda r: httpx.Response(200, json=[{"id": ID_ADMIN, "peran": "admin"}])
    )

    respons = await klien.post(
        f"/api/admin/pengguna/{ID_ADMIN}/peran", json={"peran": "pemerintah"}
    )

    assert respons.status_code == 403
    assert respons.json()["galat"]["kode"] == "AKSI_DITOLAK"
    assert len(tangkapan) == 0


@pytest.mark.integration
async def test_ubah_peran_pengguna_lain_kembalikan_200(
    dir_data_lengkap: Path, env_admin: None, buat_klien: PembuatKlien
) -> None:
    app = aplikasi_admin()
    klien = await buat_klien(app, lifespan=True)
    pasang_postgrest(
        app,
        lambda r: httpx.Response(200, json=[{"id": ID_LAIN, "peran": "pemerintah"}]),
    )

    respons = await klien.post(
        f"/api/admin/pengguna/{ID_LAIN}/peran", json={"peran": "pemerintah"}
    )

    assert respons.status_code == 200
    body = respons.json()
    assert body["data"] == {"id": ID_LAIN, "peran": "pemerintah"}


@pytest.mark.integration
async def test_ubah_peran_nilai_asing_kembalikan_422(
    dir_data_lengkap: Path, env_admin: None, buat_klien: PembuatKlien
) -> None:
    app = aplikasi_admin()
    klien = await buat_klien(app, lifespan=True)

    respons = await klien.post(
        f"/api/admin/pengguna/{ID_LAIN}/peran", json={"peran": "raja"}
    )

    assert respons.status_code == 422


@pytest.mark.integration
async def test_ubah_peran_id_bukan_uuid_kembalikan_422(
    dir_data_lengkap: Path, env_admin: None, buat_klien: PembuatKlien
) -> None:
    app = aplikasi_admin()
    klien = await buat_klien(app, lifespan=True)

    respons = await klien.post(
        "/api/admin/pengguna/bukan-uuid/peran", json={"peran": "admin"}
    )

    assert respons.status_code == 422


@pytest.mark.integration
async def test_ubah_peran_pengguna_tidak_ada_kembalikan_404(
    dir_data_lengkap: Path, env_admin: None, buat_klien: PembuatKlien
) -> None:
    app = aplikasi_admin()
    klien = await buat_klien(app, lifespan=True)
    pasang_postgrest(app, lambda r: httpx.Response(200, json=[]))

    respons = await klien.post(
        f"/api/admin/pengguna/{ID_LAIN}/peran", json={"peran": "admin"}
    )

    assert respons.status_code == 404
    assert respons.json()["galat"]["kode"] == "PENGGUNA_TIDAK_ADA"


@pytest.mark.integration
async def test_ubah_peran_postgrest_mati_kembalikan_503(
    dir_data_lengkap: Path, env_admin: None, buat_klien: PembuatKlien
) -> None:
    app = aplikasi_admin()
    klien = await buat_klien(app, lifespan=True)

    def _mati(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("PostgREST mati")

    pasang_postgrest(app, _mati)

    respons = await klien.post(
        f"/api/admin/pengguna/{ID_LAIN}/peran", json={"peran": "admin"}
    )

    assert respons.status_code == 503
    assert respons.json()["galat"]["kode"] == "DATA_BELUM_SIAP"


@pytest.mark.integration
async def test_identitas_bukan_uuid_tidak_menjadi_galat_server(
    dir_data_lengkap: Path, env_admin: None, buat_klien: PembuatKlien
) -> None:
    """Klaim `sub` yang tidak kanonik harus lewat penjaga, bukan meledak 500.

    Penjaga peran-sendiri mengonversi `identitas.id` ke UUID; tanpa
    penanganan `ValueError` sebuah klaim asing akan menjatuhkan rute menjadi
    galat server alih-alih memproses permintaan yang sah.
    """
    app = aplikasi_admin()
    app.dependency_overrides[wajib_admin] = lambda: Identitas(
        id="bukan-uuid", peran="admin"
    )
    klien = await buat_klien(app, lifespan=True)
    pasang_postgrest(
        app,
        lambda r: httpx.Response(200, json=[{"id": ID_LAIN, "peran": "pemerintah"}]),
    )

    respons = await klien.post(
        f"/api/admin/pengguna/{ID_LAIN}/peran", json={"peran": "pemerintah"}
    )

    assert respons.status_code == 200
    assert respons.json()["data"] == {"id": ID_LAIN, "peran": "pemerintah"}
