"""Rute `POST /api/chat`: satu giliran Asisten Desa.

(a) Rute ini menambah ambang laju PER PENGGUNA (`Pengaturan.laju_chat`, lewat
`@limiter.limit` + `kunci_pengguna`) DI ATAS ambang global per-IP yang sudah
ditegakkan `MiddlewareBatasLaju` (`src/middleware/rate_limit.py`) untuk
seluruh endpoint. Keduanya hidup bersamaan dan independen: middleware
mengecek dulu ambang per-IP, lalu dekorator di sini mengecek ambang per
pengguna. Satu kantor pemerintah di balik satu NAT tidak boleh saling
menghabiskan jatah harian/menit chat satu sama lain.

(b) Router dibangun lewat PABRIK (`buat_router`), menyimpang dari pola
`router = APIRouter()` modul-level yang dipakai domain lain — dekorator
`@limiter.limit` butuh objek `Limiter` MILIK APLIKASI (`app.state.limiter`)
pada waktu fungsi didefinisikan, dan `Limiter` itu baru ada setelah
`create_app()` berjalan. Pabrik ini dipanggil dari `src/main.py` persis
sekali, sesudah `app.state.limiter` siap.

(c) Respons rute ini selalu `Cache-Control: private, no-store` — ditegakkan
lewat prefiks `/api/chat` di `PREFIKS_TANPA_CACHE`
(`src/middleware/http_cache.py`), bukan di sini. PRD §5: chat tidak pernah
di-cache, riwayat percakapan adalah data pengguna.

Temuan spike slowapi 0.1.10 + FastAPI 0.141.1 (dibuktikan empiris) yang
WAJIB diikuti persis di berkas ini — jangan "diperbaiki":

1. `@router.post` HARUS di atas `@limiter.limit`. Terbalik tidak melempar
   apa pun — `router.post` mendaftarkan fungsi polos, wrapper limiter
   dibuang, ambang mati SENYAP.
2. Endpoint WAJIB punya parameter bernama persis `request: Request` DAN
   `response: Response`. Tanpa `response`, karena `headers_enabled=True`,
   permintaan SUKSES PERTAMA meledak `Exception: parameter 'response'
   must be an instance of starlette.responses.Response` — 500 di produksi.
3. `key_func` wajib parameter bernama persis `request` (slowapi memilih
   cara memanggil lewat inspeksi nama parameter).
4. `key_func` yang mengembalikan string kosong membuat ambang dilewati
   senyap — selalu kembalikan sentinel non-kosong.
5. `request.state.identitas` sudah terisi saat `key_func` dipanggil
   (`src/auth/dependencies.py::wajib_peran` menulisnya).
6. `request.state.view_rate_limit` sudah terisi sebelum `RateLimitExceeded`
   dilempar dari jalur dekorator — `tangani_batas_laju` tidak perlu diubah
   dan tetap harus SINKRON.
7. `application_limits` (middleware) dan ambang dekorator (di sini) hidup
   bersamaan dan independen — bukan `default_limits`.
"""

from fastapi import APIRouter, Depends, Request, Response
from slowapi import Limiter

from src.chat.schemas import DataJawaban, PermintaanChat
from src.chat.service import jawab
from src.chat.tools import KonteksAlat
from src.config import Pengaturan
from src.datastore import Simpanan, ambil_simpanan
from src.models import Amplop, sukses


def kunci_pengguna(request: Request) -> str:
    """Kunci bucket rate limit: id pengguna, bukan alamat IP.

    Satu kantor pemerintah di balik satu NAT tidak boleh saling
    menghabiskan jatah. Parameter WAJIB bernama persis `request` -
    slowapi memilih cara memanggil lewat inspeksi nama parameter.

    Mengembalikan sentinel non-kosong bila identitas absen: string
    kosong membuat slowapi MELEWATI ambang secara senyap (hanya
    `logger.error` internalnya). Jalur itu seharusnya tak terjangkau -
    rute ini di balik `wajib_di_atas_tamu` - tetapi key_func tidak
    boleh punya jalan keluar yang mematikan pembatas.
    """
    identitas = getattr(request.state, "identitas", None)
    if identitas is None:
        return "tanpa-identitas"
    return f"pengguna:{identitas.id}"


def buat_router(limiter: Limiter, pengaturan: Pengaturan) -> APIRouter:
    """Bangun `APIRouter` chat terikat ke `limiter` aplikasi (lihat docstring modul)."""
    router = APIRouter()

    @router.post("/api/chat", response_model=Amplop[DataJawaban])
    @limiter.limit(pengaturan.laju_chat, key_func=kunci_pengguna)
    async def chat(
        request: Request,
        response: Response,
        badan: PermintaanChat,
        simpanan: Simpanan = Depends(ambil_simpanan),  # noqa: B008
    ) -> Amplop[DataJawaban]:
        """Jalankan satu giliran Asisten Desa: stateless, non-streaming (PRD §5).

        Stateless: klien mengirim ulang SELURUH riwayat (`badan.messages`)
        di setiap permintaan — server tidak menyimpan percakapan apa pun.
        Non-streaming: satu jawaban utuh per permintaan, bukan potongan
        token bertahap.

        `request` dan `response` tampak tak terpakai di badan fungsi, tapi
        KEDUANYA WAJIB ada di signature: slowapi butuh `request` untuk
        `key_func`, dan tanpa `response` permintaan SUKSES PERTAMA meledak
        (`headers_enabled=True` pada `Limiter` membuat wrapper slowapi
        menyuntik header `X-RateLimit-*` ke `response` setelah handler
        selesai — parameter yang hilang baru ketahuan saat itu, bukan saat
        endpoint didekorasi).

        `meta` amplop selalu `null` — jejak fungsi, model, cacah putaran
        alat, dan peringatan ada DI DALAM `data` (`DataJawaban`), karena
        `src.models.Meta` mewajibkan `total`/`hal`/`batas` (milik paginasi)
        dan PRD §6 menyatakan `meta` hanya terisi pada respons berpaginasi
        — chat tidak berpaginasi sama sekali.
        """
        konteks = KonteksAlat(
            simpanan=simpanan,
            klien_supabase=request.app.state.klien_supabase,
        )
        # Nama prompt datang dari `app.state`, bukan hardcode, supaya
        # harness bisa menukarnya; bawaannya selalu "asisten.md".
        data = await jawab(
            badan,
            request.app.state.layanan_ai,
            konteks,
            pengaturan,
            request.app.state.nama_prompt_chat,
        )
        return sukses(data)

    return router
