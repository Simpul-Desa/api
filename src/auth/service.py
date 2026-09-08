"""Verifikasi token Supabase dan pembacaan peran dari tabel `profil`.

Token JWT diterbitkan Supabase Auth dan diverifikasi di sini lewat JWKS
(algoritma ES256). Peran pengguna TIDAK PERNAH dibaca dari klaim token —
peran selalu diambil dari tabel `profil` lewat PostgREST, sesuai PRD §5,
supaya klaim token yang dipalsukan atau kedaluwarsa tidak bisa menaikkan
peran seseorang tanpa sepengetahuan basis data.

`src/auth/dependencies.py` memanggil fungsi di berkas ini lewat objek
modul, bukan lewat from-import: uji menambal atribut modul ini, dan nama
yang sudah ter-bind di berkas lain tidak akan tersentuh tambalan itu.
"""

import logging
import uuid
from functools import lru_cache
from typing import Any

import httpx
import jwt

from src.auth.constants import PERAN_TAMU_KE_ATAS
from src.config import Pengaturan
from src.exceptions import (
    AUTH_BELUM_SIAP,
    PERAN_TIDAK_DIKENAL,
    TIDAK_BERWENANG,
    GalatAPI,
)

logger = logging.getLogger(__name__)


@lru_cache(maxsize=2)
def _klien_jwks(url: str) -> jwt.PyJWKClient:
    """Klien JWKS Supabase, di-cache supaya kunci publik tidak diambil ulang.

    `timeout` diperpendek dari bawaan 30 detik: pengambilan JWKS berjalan
    blocking di threadpool, dan `kid` asing pada token palsu memaksa refetch —
    timeout panjang membuat threadpool mudah dihabiskan penyerang tanpa
    kredensial (temuan tinjauan fase 4).
    """
    return jwt.PyJWKClient(url, timeout=5.0, max_cached_keys=16)


def _kunci_penandatangan(token: str, pengaturan: Pengaturan) -> Any:
    """Ambil kunci publik penandatangan `token` dari JWKS Supabase.

    Fungsi terpisah ini sengaja jadi test seam: test memonkeypatch atribut
    modul ini supaya verifikasi tanda tangan bisa diuji tanpa memanggil JWKS
    Supabase asli.
    """
    klien = _klien_jwks(f"{pengaturan.supabase_url}/auth/v1/.well-known/jwks.json")
    return klien.get_signing_key_from_jwt(token).key


def verifikasi_token(token: str, pengaturan: Pengaturan) -> dict[str, Any]:
    """Verifikasi tanda tangan, audience, issuer, dan klaim wajib token Supabase.

    Mengembalikan klaim token bila sah. 401 untuk semua cacat sisi token
    (tanda tangan, kedaluwarsa, aud/iss salah, klaim wajib hilang, `kid` tak
    dikenal); 503 `AUTH_BELUM_SIAP` untuk kegagalan sisi layanan (JWKS tak
    terjangkau atau tidak berisi kunci — mis. proyek masih memakai secret
    HS256 lama, yang JWKS-nya kosong).
    """
    try:
        kunci = _kunci_penandatangan(token, pengaturan)
    except jwt.exceptions.PyJWKClientConnectionError as exc:
        logger.warning("JWKS Supabase tidak terjangkau: %s", exc)
        raise GalatAPI(
            AUTH_BELUM_SIAP, "layanan autentikasi tidak terjangkau", 503
        ) from exc
    except jwt.exceptions.PyJWKSetError as exc:
        logger.warning("JWKS Supabase tidak berisi kunci: %s", exc)
        raise GalatAPI(
            AUTH_BELUM_SIAP, "kunci penandatangan tidak tersedia", 503
        ) from exc
    except (jwt.exceptions.PyJWKClientError, jwt.InvalidTokenError) as exc:
        raise GalatAPI(TIDAK_BERWENANG, "token tidak sah", 401) from exc

    try:
        klaim: dict[str, Any] = jwt.decode(
            token,
            kunci,
            algorithms=["ES256"],
            audience=pengaturan.jwt_audience,
            issuer=f"{pengaturan.supabase_url}/auth/v1",
            options={"require": ["exp", "iat", "sub"]},
        )
    except jwt.InvalidTokenError as exc:
        # Token basi/dipalsukan/klaim salah: lalu lintas normal, volume tinggi
        # (tiap permintaan tanpa sesi valid lewat sini) - DEBUG tanpa traceback
        # supaya log tidak banjir untuk sesuatu yang memang diharapkan terjadi.
        logger.debug("token ditolak saat decode: %s", exc)
        raise GalatAPI(TIDAK_BERWENANG, "token tidak sah", 401) from exc
    except (TypeError, ValueError) as exc:
        # TypeError/ValueError di titik ini TIDAK datang dari token pemanggil -
        # `_kunci_penandatangan` (test seam kita sendiri) yang mengembalikan
        # objek kunci cacat, dan PyJWT melemparnya langsung tanpa membungkus ke
        # InvalidTokenError. Ini bug di jalur kunci kita, bukan token forgeri,
        # jadi WARNING + exc_info=True supaya traceback tidak hilang di balik
        # 401 yang sama seperti token palsu biasa.
        logger.warning(
            "kunci penandatangan cacat saat decode token: %s", exc, exc_info=True
        )
        raise GalatAPI(TIDAK_BERWENANG, "token tidak sah", 401) from exc
    return klaim


async def ambil_peran_profil(
    klien: httpx.AsyncClient, pengaturan: Pengaturan, id_pengguna: str
) -> str | None:
    """Ambil kolom `peran` pengguna dari tabel `profil` lewat PostgREST.

    Mengembalikan `None` bila belum ada baris profil untuk pengguna tersebut.
    Melempar `GalatAPI` 401 bila `id_pengguna` bukan UUID sah (tanpa memanggil
    jaringan), 503 bila PostgREST tidak terjangkau atau balasannya tidak
    berbentuk daftar profil, dan 403 `PERAN_TIDAK_DIKENAL` bila nilai
    perannya di luar empat peran sah — data yang tak dikenal divalidasi di
    batas, bukan diteruskan, dan ini bukan indikasi layanan mati.
    """
    try:
        id_kanonik = str(uuid.UUID(id_pengguna))
    except ValueError as exc:
        raise GalatAPI(TIDAK_BERWENANG, "token tidak sah", 401) from exc

    kunci_layanan = pengaturan.supabase_service_role_key.get_secret_value()
    try:
        respons = await klien.get(
            f"{pengaturan.supabase_url}/rest/v1/profil",
            params={"id": f"eq.{id_kanonik}", "select": "peran"},
            headers={
                "apikey": kunci_layanan,
                "Authorization": f"Bearer {kunci_layanan}",
            },
        )
        respons.raise_for_status()
        baris = respons.json()
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("PostgREST profil tidak terjangkau atau rusak: %s", exc)
        raise GalatAPI(
            AUTH_BELUM_SIAP, "layanan autentikasi tidak terjangkau", 503
        ) from exc

    if not isinstance(baris, list):
        logger.warning("bentuk balasan profil tidak dikenal: %s", type(baris).__name__)
        raise GalatAPI(AUTH_BELUM_SIAP, "layanan autentikasi tidak terjangkau", 503)
    if not baris:
        return None

    peran = baris[0].get("peran") if isinstance(baris[0], dict) else None
    if peran not in PERAN_TAMU_KE_ATAS:
        # Ini bukan galat jaringan atau outage - PostgREST menjawab normal, cuma
        # satu baris berisi nilai yang tidak dikenal kode (peran hasil edit
        # tangan, migrasi belum selesai, atau peran baru yang belum didaftarkan
        # ke PERAN_TAMU_KE_ATAS). Status publik jadi 403 PERAN_TIDAK_DIKENAL
        # (bukan lagi 503 AUTH_BELUM_SIAP - melaporkan ini sebagai outage
        # keliru dan mengirim operator memburu galat jaringan yang tak ada).
        # Log operator tetap menyebut id dan nilainya; pesan publik sengaja
        # TIDAK menyertakan nilai peran supaya tidak bocor ke pemanggil.
        logger.warning(
            "peran profil id=%s bernilai %r di luar daftar peran sah "
            "(PostgREST menjawab normal, ini bukan indikasi layanan mati)",
            id_kanonik,
            peran,
        )
        raise GalatAPI(
            PERAN_TIDAK_DIKENAL,
            "peran akun ini tidak dikenal oleh layanan",
            403,
        )
    return str(peran)
