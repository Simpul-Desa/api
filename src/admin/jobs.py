"""Pekerjaan latar penyegaran Berita Desa: satu pekerjaan pada satu waktu.

State disimpan di `app.state.pekerjaan_penyegaran` sebagai dataclass FROZEN -
tiap kemajuan menghasilkan salinan baru lewat `replace()`, bukan mutasi di
tempat (aturan imutabilitas ECC). Referensi ke `Task` disimpan di
`app.state.tugas_penyegaran` supaya tidak dikumpulkan garbage collector di
tengah jalan (`asyncio` hanya memegang weak reference ke task yang tidak
direferensikan siapa pun).

Dijalankan lewat `asyncio.create_task`, BUKAN `BackgroundTasks` FastAPI:
aplikasi ini memasang tiga `BaseHTTPMiddleware`, dan background task
Starlette berjalan setelah body respons dikirim tetapi masih di dalam
rantai middleware — pekerjaan yang bisa berjam-jam akan menahan rantai itu.
`asyncio.create_task` lepas total dari siklus permintaan/respons.

Tanpa persistensi: proses restart = state hilang. Itu memang desainnya
(PRD §4: tidak ada tabel log penyegaran). Panen sendiri idempoten
(`merge-duplicates` di `store.py`), jadi menjalankan ulang aman.
"""

import asyncio
import logging
import uuid
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Literal

import httpx
from fastapi import FastAPI
from starlette.concurrency import run_in_threadpool

from src.admin.schemas import HasilPenyegaranDesa, StatusPekerjaan
from src.berita.harvest.orchestrator import panen_desa
from src.config import Pengaturan, ambil_pengaturan

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Pekerjaan:
    """State satu pekerjaan penyegaran; salinan baru dibuat lewat `replace()`."""

    id_pekerjaan: str
    keadaan: Literal["berjalan", "selesai"]
    total: int
    selesai: int
    mulai_pada: datetime
    selesai_pada: datetime | None
    hasil: tuple[HasilPenyegaranDesa, ...]


def sedang_berjalan(app: FastAPI) -> bool:
    """True bila ada pekerjaan penyegaran yang belum `selesai`."""
    pekerjaan: Pekerjaan | None = getattr(app.state, "pekerjaan_penyegaran", None)
    return pekerjaan is not None and pekerjaan.keadaan == "berjalan"


def mulai(app: FastAPI, desa: list[tuple[str, str, str]]) -> Pekerjaan:
    """Pasang pekerjaan `berjalan` ke `app.state` dan lepas `_jalankan` di latar.

    Pemanggil (rute admin) WAJIB memanggil ini tanpa `await` di antara cek
    `sedang_berjalan` dan pemasangan state — di satu event loop keduanya
    atomik selama tidak ada titik `await` yang menyisip lomba dua
    permintaan admin bersamaan.
    """
    id_pekerjaan = uuid.uuid4().hex
    pekerjaan = Pekerjaan(
        id_pekerjaan=id_pekerjaan,
        keadaan="berjalan",
        total=len(desa),
        selesai=0,
        mulai_pada=datetime.now(UTC),
        selesai_pada=None,
        hasil=(),
    )
    app.state.pekerjaan_penyegaran = pekerjaan
    app.state.tugas_penyegaran = asyncio.create_task(
        _jalankan(app, ambil_pengaturan(), desa)
    )
    return pekerjaan


async def _jalankan(
    app: FastAPI, pengaturan: Pengaturan, desa: list[tuple[str, str, str]]
) -> None:
    """Panen tiap desa berurutan; satu desa gagal tidak menghentikan yang lain."""
    klien = httpx.Client(timeout=30.0)
    try:
        for iddesa, nmdesa, nmkab in desa:
            try:
                hasil_panen = await run_in_threadpool(
                    panen_desa, klien, pengaturan, iddesa, nmdesa, nmkab
                )
            except Exception as exc:
                logger.warning(
                    "penyegaran desa %s gagal, lanjut ke desa berikutnya: %s",
                    iddesa,
                    exc,
                    exc_info=True,
                )
                # Seluruh panggilan panen_desa gagal (mis. RSS mati total) —
                # tak ada cacah per-artikel yang berarti di sini, beda dengan
                # cabang sukses di bawah yang punya hasil_panen.n_gagal per
                # artikel. n_gagal=0 dipilih daripada menebak: `galat` di atas
                # sudah membawa kegagalan tingkat desa, jadi n_gagal tidak
                # dipakai untuk mengulang informasi yang sama di granularitas
                # yang salah.
                baru = HasilPenyegaranDesa(
                    iddesa=iddesa,
                    n_baru=0,
                    n_duplikat=0,
                    n_dibuang=0,
                    n_gagal=0,
                    galat=str(exc),
                )
            else:
                baru = HasilPenyegaranDesa(
                    iddesa=hasil_panen.iddesa,
                    n_baru=hasil_panen.n_baru,
                    n_duplikat=hasil_panen.n_duplikat,
                    n_dibuang=hasil_panen.n_dibuang,
                    n_gagal=hasil_panen.n_gagal,
                    galat=None,
                )

            pekerjaan_sekarang = app.state.pekerjaan_penyegaran
            app.state.pekerjaan_penyegaran = replace(
                pekerjaan_sekarang,
                selesai=pekerjaan_sekarang.selesai + 1,
                hasil=(*pekerjaan_sekarang.hasil, baru),
            )
    finally:
        klien.close()
        pekerjaan_sekarang = app.state.pekerjaan_penyegaran
        app.state.pekerjaan_penyegaran = replace(
            pekerjaan_sekarang, keadaan="selesai", selesai_pada=datetime.now(UTC)
        )


def ke_skema(pekerjaan: Pekerjaan | None) -> StatusPekerjaan | None:
    """Proyeksikan `Pekerjaan` internal ke `StatusPekerjaan` publik, atau None."""
    if pekerjaan is None:
        return None
    return StatusPekerjaan(
        id_pekerjaan=pekerjaan.id_pekerjaan,
        keadaan=pekerjaan.keadaan,
        total=pekerjaan.total,
        selesai=pekerjaan.selesai,
        mulai_pada=pekerjaan.mulai_pada,
        selesai_pada=pekerjaan.selesai_pada,
        hasil=list(pekerjaan.hasil),
    )
