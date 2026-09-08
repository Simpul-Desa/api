"""Titik masuk aplikasi FastAPI: instansiasi, lifespan, dan pendaftaran rute.

Jalankan dengan: `uvicorn src.main:app`.
"""

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import Depends, FastAPI
from slowapi.errors import RateLimitExceeded

from src.admin.router import router as router_admin
from src.auth.dependencies import (
    wajib_admin,
    wajib_di_atas_tamu,
    wajib_pemerintah,
    wajib_tamu,
)
from src.berita.router import router as router_berita
from src.chat.llm import LayananGemini
from src.chat.router import buat_router as buat_router_chat
from src.citra_potensi.router import router as router_citra_potensi
from src.config import ambil_pengaturan
from src.datastore import muat_manifest, muat_simpanan
from src.desa.router import router as router_cari
from src.desa_kembar.router import router as router_desa_kembar
from src.exceptions import daftarkan_handler
from src.geo.router import router as router_geo
from src.health.router import router as router_kesehatan
from src.jalur_ekonomi.router import router as router_jalur_ekonomi
from src.kartu.router import router as router_kartu
from src.laporan.router import router as router_laporan
from src.middleware.cors import MiddlewareCORS
from src.middleware.http_cache import MiddlewareCacheHTTP
from src.middleware.rate_limit import (
    MiddlewareBatasLaju,
    buat_limiter,
    tangani_batas_laju,
)
from src.peta_peran.router import router as router_peta_peran
from src.wilayah.router import router as router_wilayah

# Lama menunggu `tugas_penyegaran` benar-benar berhenti setelah dibatalkan.
# Menunggu BERBATAS, bukan tanpa batas: `panen_desa` blocking di `requests`
# dan `time.sleep` di dalam `run_in_threadpool`, sehingga `asyncio` tidak
# bisa menyela threadnya — `await tugas` tanpa tenggat menahan shutdown
# selama sisa panen, yang terukur sampai 3 menit 37 detik untuk SATU desa.
# Dengan tenggat ini `finally` di `jobs._jalankan` (penanda `selesai` +
# penutupan `httpx.Client` miliknya) mendapat kesempatan berjalan, tanpa
# pernah menyandera proses yang sedang dimatikan.
TENGGAT_SHUTDOWN_PEKERJAAN = 5.0


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Muat manifest + `Simpanan` ke `app.state` dan buka klien HTTP Supabase."""
    app.state.manifest = muat_manifest(ambil_pengaturan().dir_data)
    app.state.simpanan = muat_simpanan(ambil_pengaturan().dir_data)
    app.state.klien_supabase = httpx.AsyncClient(timeout=10.0)
    # `create_app()` sudah mengisi keduanya dengan nilai yang sama, jadi
    # menimpanya di sini tidak menambah apa pun di produksi. Yang ia rusak
    # ada di uji: penugasan tanpa syarat MEMBUANG `LayananPalsu` yang
    # dipasang uji ke `app.state` sebelum lifespan berjalan, dan suite
    # diam-diam memanggil Gemini SUNGGUHAN — terbukti 8 September 2026,
    # menabrak 429 RESOURCE_EXHAUSTED dan memakan kuota free tier tanpa
    # satu pun galat yang menunjuk penyebabnya. Dibuat lazy (lihat
    # `LayananGemini._client`), jadi kunci kosong tidak menggagalkan boot —
    # hanya rute chat yang 503 saat benar-benar dipanggil.
    if getattr(app.state, "layanan_ai", None) is None:
        app.state.layanan_ai = LayananGemini(ambil_pengaturan())
    # Nama berkas prompt yang dipakai rute chat. Hidup di `app.state` supaya
    # harness bisa membandingkan varian prompt tanpa menyunting kode;
    # produksi tidak pernah mengubahnya. Bersyarat dengan alasan yang sama
    # seperti `layanan_ai` di atas.
    if getattr(app.state, "nama_prompt_chat", None) is None:
        app.state.nama_prompt_chat = "asisten.md"
    app.state.pekerjaan_penyegaran = None
    app.state.tugas_penyegaran = None
    yield
    tugas = app.state.tugas_penyegaran
    if tugas is not None and not tugas.done():
        tugas.cancel()
        # CancelledError memang yang diharapkan; TimeoutError berarti thread
        # panen masih blocking. Keduanya ditelan: jalur shutdown tidak boleh
        # melempar, dan panen yang menggantung tidak boleh mencegah proses
        # keluar.
        with contextlib.suppress(asyncio.CancelledError, TimeoutError):
            await asyncio.wait_for(
                asyncio.shield(tugas), timeout=TENGGAT_SHUTDOWN_PEKERJAAN
            )
    await app.state.klien_supabase.aclose()


def create_app() -> FastAPI:
    """Bangun instance FastAPI: siapkan logging, handler galat, dan rute."""
    logging.basicConfig(level=logging.INFO)

    app = FastAPI(title="SIMPUL DESA API", lifespan=_lifespan)
    daftarkan_handler(app)

    # Limiter dibuat per aplikasi supaya storage in-memory segar per instance
    # dan ambang selalu dari konfigurasi (PRD §3).
    app.state.limiter = buat_limiter(ambil_pengaturan().laju_bawaan)
    app.add_exception_handler(RateLimitExceeded, tangani_batas_laju)

    # Nilai awal yang sama seperti `_lifespan` (pola sudah dipakai
    # `app.state.limiter` di atas) — sebagian uji membangun app lewat
    # `create_app()` TANPA menjalankan lifespan, dan rute chat butuh
    # `app.state.layanan_ai` supaya tidak `AttributeError` di situ.
    # `_lifespan` MEMPERTAHANKANNYA (bersyarat) saat aplikasi sungguhan
    # berjalan — lihat komentar di `_lifespan` kenapa penugasan di sana
    # tidak boleh tanpa syarat.
    app.state.layanan_ai = LayananGemini(ambil_pengaturan())
    # Sama alasannya seperti `layanan_ai` di atas: uji membangun app lewat
    # `create_app()` TANPA menjalankan lifespan, dan rute chat butuh
    # `app.state.nama_prompt_chat` supaya tidak `AttributeError` di situ.
    # `_lifespan` MEMPERTAHANKANNYA (bersyarat) saat aplikasi sungguhan
    # berjalan.
    app.state.nama_prompt_chat = "asisten.md"

    # Middleware yang ditambah terakhir berjalan paling luar; CORS terluar
    # supaya respons 304/429/galat — termasuk 500 yang ditangkapnya sendiri —
    # tetap berheader CORS. Konsekuensi yang diterima: preflight OPTIONS
    # dijawab CORS sebelum pembatas laju (lihat docstring src/middleware/cors.py).
    app.add_middleware(MiddlewareCacheHTTP)
    app.add_middleware(MiddlewareBatasLaju)
    app.add_middleware(MiddlewareCORS)

    # Matriks akses PRD akar §3: empat router tamu diberi dependensi peran
    # di titik include_router (router fase 3 tidak disentuh).
    dependensi_tamu = [Depends(wajib_tamu)]
    app.include_router(router_kesehatan)
    app.include_router(router_wilayah)
    app.include_router(router_cari)
    app.include_router(router_kartu)
    app.include_router(router_peta_peran, dependencies=dependensi_tamu)
    app.include_router(router_citra_potensi, dependencies=dependensi_tamu)
    app.include_router(router_jalur_ekonomi, dependencies=dependensi_tamu)
    app.include_router(router_desa_kembar, dependencies=dependensi_tamu)
    app.include_router(router_berita, dependencies=dependensi_tamu)
    # Chat memakai pabrik (`buat_router_chat`), bukan router modul-level
    # seperti domain lain — dekorator ambang per pengguna butuh
    # `app.state.limiter`, yang baru ada setelah baris limiter di atas.
    app.include_router(
        buat_router_chat(app.state.limiter, ambil_pengaturan()),
        dependencies=[Depends(wajib_di_atas_tamu)],
    )
    app.include_router(router_admin, dependencies=[Depends(wajib_admin)])
    app.include_router(router_laporan, dependencies=[Depends(wajib_pemerintah)])
    app.include_router(router_geo)
    return app


app = create_app()
