"""Dependensi FastAPI penegak peran untuk endpoint bertoken.

Urutan penegakan: konfigurasi Supabase harus terisi (503), token harus ada
(401), token harus sah (401), lalu peran diambil dari tabel `profil` (403
bila belum terdaftar atau perannya tidak termasuk yang diizinkan).

Fungsi `service` dipanggil lewat OBJEK MODUL (`service.verifikasi_token`,
`service.ambil_peran_profil`), bukan lewat from-import. Uji menambal
atribut modul `src.auth.service`; nama yang ter-bind lewat from-import di
berkas ini tidak akan tersentuh tambalan itu, sehingga uji bisa hijau
sambil benar-benar memanggil JWKS Supabase asli.
"""

from collections.abc import Callable, Coroutine
from typing import Annotated, Any

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from starlette.concurrency import run_in_threadpool

from src.auth import service
from src.auth.constants import (
    PERAN_ADMIN_SAJA,
    PERAN_DI_ATAS_TAMU,
    PERAN_PEMERINTAH_KE_ATAS,
    PERAN_TAMU_KE_ATAS,
)
from src.auth.schemas import Identitas
from src.config import ambil_pengaturan
from src.exceptions import AUTH_BELUM_SIAP, PERAN_KURANG, TIDAK_BERWENANG, GalatAPI

_SKEMA_BEARER = HTTPBearer(auto_error=False)


def wajib_peran(
    diizinkan: frozenset[str],
) -> Callable[..., Coroutine[Any, Any, Identitas]]:
    """Buat dependensi FastAPI yang menegakkan token sah + peran `diizinkan`.

    Urutan penegakan: konfigurasi Supabase harus terisi (503), token harus
    ada (401), token harus sah (401), lalu peran diambil dari tabel `profil`
    (403 bila belum terdaftar atau bila peran tidak termasuk `diizinkan`).
    """

    async def _dependensi(
        request: Request,
        kredensial: Annotated[
            HTTPAuthorizationCredentials | None, Depends(_SKEMA_BEARER)
        ],
    ) -> Identitas:
        pengaturan = ambil_pengaturan()
        if (
            not pengaturan.supabase_url
            or not pengaturan.supabase_service_role_key.get_secret_value()
        ):
            raise GalatAPI(
                AUTH_BELUM_SIAP, "konfigurasi autentikasi belum diisi di server", 503
            )

        if kredensial is None:
            raise GalatAPI(TIDAK_BERWENANG, "token tidak diberikan", 401)

        klaim = await run_in_threadpool(
            service.verifikasi_token, kredensial.credentials, pengaturan
        )

        sub = str(klaim.get("sub", ""))
        peran = await service.ambil_peran_profil(
            request.app.state.klien_supabase, pengaturan, sub
        )
        if peran is None:
            raise GalatAPI(PERAN_KURANG, "profil pengguna belum terdaftar", 403)

        if peran not in diizinkan:
            raise GalatAPI(
                PERAN_KURANG, "peran tidak mencukupi untuk endpoint ini", 403
            )

        identitas = Identitas(id=sub, peran=peran)
        # Dipakai key_func rate limit per pengguna (src/chat/router.py).
        # Ditulis di sini, bukan di rute chat, supaya key_func tidak perlu
        # memverifikasi token untuk kedua kalinya.
        request.state.identitas = identitas
        return identitas

    return _dependensi


wajib_tamu = wajib_peran(PERAN_TAMU_KE_ATAS)
wajib_admin = wajib_peran(PERAN_ADMIN_SAJA)
wajib_pemerintah = wajib_peran(PERAN_PEMERINTAH_KE_ATAS)
wajib_di_atas_tamu = wajib_peran(PERAN_DI_ATAS_TAMU)
