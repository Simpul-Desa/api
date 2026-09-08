"""Pembantu bersama uji rute admin: aplikasi beridentitas admin dan stub PostgREST.

Dipisah dari berkas ujinya supaya keempat berkas uji rute admin
(`test_segarkan`, `test_hapus_berita`, `test_pengguna`, `test_status`) tidak
menyalin stub yang sama empat kali. Fixture `env_admin` tinggal di
`tests/admin/conftest.py` — fixture yang diimpor dari modul biasa terbaca
sebagai impor tak terpakai oleh ruff.

`aplikasi_admin()` memanggil `create_app()`, yang membaca `DIR_DATA` saat
dipanggil: cantumkan fixture `dir_data_lengkap` SEBELUM memanggilnya pada
signature uji.
"""

from collections.abc import Callable

import httpx
from fastapi import FastAPI

from src.auth.dependencies import wajib_admin
from src.auth.schemas import Identitas
from src.main import create_app

ID_ADMIN = "00000000-0000-0000-0000-000000000004"
ID_LAIN = "00000000-0000-0000-0000-000000000001"


def aplikasi_admin() -> FastAPI:
    """Aplikasi nyata dengan dependensi `wajib_admin` di-override peran admin.

    Matriks aksesnya sendiri diuji tanpa override di
    `tests/auth/test_matriks_akses.py`; berkas uji rute admin memakai
    override ini supaya yang diuji perilaku rutenya, bukan gerbang perannya.
    """
    app = create_app()
    app.dependency_overrides[wajib_admin] = lambda: Identitas(
        id=ID_ADMIN, peran="admin"
    )
    return app


def pasang_postgrest(
    app: FastAPI, handler: Callable[[httpx.Request], httpx.Response]
) -> list[httpx.Request]:
    """Ganti `klien_supabase` dengan transport tiruan; kembalikan daftar tangkapan.

    Daftar yang dikembalikan terisi setiap kali rute memanggil PostgREST,
    sehingga uji bisa memeriksa parameter dan header yang benar-benar
    dikirim. Penggantian harus dilakukan SETELAH lifespan berjalan, supaya
    klien sungguhan yang dipasang lifespan tertimpa.
    """
    tangkapan: list[httpx.Request] = []

    def _handler(request: httpx.Request) -> httpx.Response:
        tangkapan.append(request)
        return handler(request)

    app.state.klien_supabase = httpx.AsyncClient(
        transport=httpx.MockTransport(_handler)
    )
    return tangkapan
