"""Uji integrasi ambang laju PER PENGGUNA `POST /api/chat` (Tugas 10, fase 5).

Ambang bawaan `Pengaturan.laju_chat` ("10/minute;200/day") terlalu besar
untuk uji cepat — diturunkan lewat env `LAJU_CHAT` SEBELUM `create_app()`
dipanggil (pabrik router chat membaca `pengaturan.laju_chat` saat
`include_router` dijalankan), pola yang sama seperti `dir_data_manifest`
di `tests/conftest.py`: `monkeypatch.setenv(...)` + `ambil_pengaturan.cache_clear()`
sebelum DAN sesudah supaya perubahan env tidak bocor ke uji lain.
"""

from collections.abc import Callable, Iterator
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI, Request

from src.auth.dependencies import wajib_di_atas_tamu
from src.auth.schemas import Identitas
from src.chat.llm import LangkahPalsu, LayananPalsu
from src.chat.router import kunci_pengguna
from src.config import ambil_pengaturan
from src.main import create_app
from tests.conftest import PembuatKlien

pytestmark = [pytest.mark.integration, pytest.mark.anyio]

_PESAN_DASAR = [{"role": "user", "isi": "Berapa Skor Potensi desa itu?"}]
ID_A = "pengguna-a"
ID_B = "pengguna-b"


def _override_identitas(id_pengguna: str) -> Callable[[Request], Identitas]:
    """Bangun override `wajib_di_atas_tamu` yang IKUT menulis `request.state.identitas`.

    Dependensi asli (`src.auth.dependencies.wajib_peran`) menulis
    `request.state.identitas` sebagai efek samping — itulah yang dibaca
    `kunci_pengguna` untuk kunci bucket per pengguna. Override polos
    `lambda: Identitas(...)` (tanpa parameter `request`) TIDAK meniru efek
    samping itu, sehingga `kunci_pengguna` selalu jatuh ke sentinel
    "tanpa-identitas" untuk SEMUA pengguna — dua identitas berbeda diam-diam
    berbagi satu bucket, dan uji "bucket tidak dibagi antar pengguna" jadi
    tidak membuktikan apa-apa. Dibuktikan empiris: tanpa perbaikan ini,
    permintaan pertama `ID_B` ikut kena 429 milik `ID_A`.
    """

    def _dependensi(request: Request) -> Identitas:
        identitas = Identitas(id=id_pengguna, peran="pemerintah")
        request.state.identitas = identitas
        return identitas

    return _dependensi


@pytest.fixture
def ambang_laju_kecil(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """`LAJU_CHAT=3/minute` — ambang bawaan (10/menit) terlalu besar untuk uji cepat."""
    monkeypatch.setenv("LAJU_CHAT", "3/minute")
    ambil_pengaturan.cache_clear()

    yield

    ambil_pengaturan.cache_clear()


@pytest.fixture
def aplikasi_laju(dir_data_lengkap: Path, ambang_laju_kecil: None) -> FastAPI:
    """App nyata dengan ambang chat 3/menit dan identitas awal `ID_A`.

    `dir_data_lengkap` dan `ambang_laju_kecil` HARUS mendahului `create_app()`
    di sini: keduanya mengubah env yang dibaca `create_app()` saat itu
    dipanggil (`DIR_DATA` untuk `Simpanan`, `LAJU_CHAT` untuk dekorator
    `@limiter.limit` pabrik router chat).
    """
    app = create_app()
    app.dependency_overrides[wajib_di_atas_tamu] = _override_identitas(ID_A)
    return app


@pytest.fixture
async def klien_laju(
    aplikasi_laju: FastAPI, buat_klien: PembuatKlien
) -> httpx.AsyncClient:
    """Klien `aplikasi_laju` dengan lifespan aktif + `layanan_ai` palsu.

    `layanan_ai` DIGANTI SETELAH `buat_klien(..., lifespan=True)`, bukan di
    fixture `aplikasi_laju`. Bukan `_lifespan()` (`src/main.py`) yang jadi
    alasannya — sejak itu bersyarat (`if getattr(app.state, "layanan_ai",
    None) is None`, sekitar baris 73), sehingga tidak menimpa apa pun yang
    sudah tersetel. Yang menugaskan `LayananGemini` NYATA adalah
    `create_app()` sendiri, TANPA syarat (sekitar baris 117) — dipanggil di
    dalam fixture `aplikasi_laju`, jauh sebelum fixture ini sempat menyetel
    `layanan_ai` palsu. Menimpanya di sini, setelah `create_app()` selesai,
    memastikan permintaan chat memakai `LayananPalsu`, bukan Gemini asli —
    terbukti empiris: percobaan pertama berkas ini memakan kuota Gemini asli
    sampai 429 RESOURCE_EXHAUSTED sebelum ketahuan. Insiden itu tetap
    berlaku sebagai alasan pola ini dipertahankan.
    """
    klien = await buat_klien(aplikasi_laju, lifespan=True)
    aplikasi_laju.state.layanan_ai = LayananPalsu(
        [LangkahPalsu(teks="Skor Potensi mengukur potensi ekonomi desa.")]
    )
    return klien


async def test_ambang_per_pengguna_menyala(klien_laju: httpx.AsyncClient) -> None:
    """Permintaan ke-4 pengguna yang sama → 429 beramplop.

    Membuktikan juga urutan dekorator benar (`@router.post` di atas
    `@limiter.limit`, lihat docstring `src/chat/router.py`) — kalau
    terbalik, `router.post` mendaftarkan fungsi polos, ambang mati SENYAP,
    dan keempat permintaan akan 200.
    """
    for _ in range(3):
        respons = await klien_laju.post("/api/chat", json={"messages": _PESAN_DASAR})
        assert respons.status_code == 200

    keempat = await klien_laju.post("/api/chat", json={"messages": _PESAN_DASAR})

    assert keempat.status_code == 429
    body = keempat.json()
    assert body["sukses"] is False
    assert body["galat"]["kode"] == "TERLALU_BANYAK_PERMINTAAN"


async def test_bucket_tidak_dibagi_antar_pengguna(
    aplikasi_laju: FastAPI, klien_laju: httpx.AsyncClient
) -> None:
    """Habiskan jatah `ID_A`; permintaan PERTAMA `ID_B` tetap 200."""
    for _ in range(3):
        respons = await klien_laju.post("/api/chat", json={"messages": _PESAN_DASAR})
        assert respons.status_code == 200
    habis = await klien_laju.post("/api/chat", json={"messages": _PESAN_DASAR})
    assert habis.status_code == 429

    aplikasi_laju.dependency_overrides[wajib_di_atas_tamu] = _override_identitas(ID_B)
    pertama_b = await klien_laju.post("/api/chat", json={"messages": _PESAN_DASAR})

    assert pertama_b.status_code == 200


async def test_permintaan_sukses_pertama_tidak_500(
    klien_laju: httpx.AsyncClient,
) -> None:
    """`headers_enabled=True` membuat slowapi meledak pada respons SUKSES bila
    endpoint tidak punya parameter `response: Response` (lihat docstring
    `src/chat/router.py`, butir 2) — 500 di produksi, bukan 200. Ini
    penjaga regresinya: permintaan sukses PERTAMA, bukan yang kedua dst.
    """
    respons = await klien_laju.post("/api/chat", json={"messages": _PESAN_DASAR})

    assert respons.status_code == 200


async def test_header_ratelimit_tidak_ganda(klien_laju: httpx.AsyncClient) -> None:
    """Nilai `X-RateLimit-Limit` ganda ("3, 3") berarti header disuntik dua
    kali: wrapper slowapi dekorator + `MiddlewareBatasLaju` (lihat
    docstring `src/middleware/rate_limit.py`).
    """
    respons = await klien_laju.post("/api/chat", json={"messages": _PESAN_DASAR})

    assert respons.status_code == 200
    nilai = respons.headers.get("X-RateLimit-Limit")
    assert nilai is not None
    assert "," not in nilai


def test_kunci_pengguna_tanpa_identitas_tidak_melempar() -> None:
    """String kosong membuat slowapi MELEWATI ambang secara senyap — `kunci_pengguna`
    harus selalu mengembalikan sentinel non-kosong walau `request.state.identitas`
    absen (jalur yang seharusnya tak terjangkau di balik `wajib_di_atas_tamu`).
    """

    class _StateTanpaIdentitas:
        pass

    class _RequestPalsu:
        state = _StateTanpaIdentitas()

    hasil = kunci_pengguna(_RequestPalsu())  # type: ignore[arg-type]

    assert hasil != ""
