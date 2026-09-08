"""Uji integrasi rute `POST /api/admin/berita/segarkan` (Tugas 9, fase 7).

`panen_desa` SELALU ditambal (`monkeypatch.setattr(jobs, "panen_desa", ...)`)
supaya berkas ini nol jaringan, mengikuti pola `tests/admin/test_jobs.py`.
"""

import asyncio
import threading
from pathlib import Path

import httpx
import pytest
from httpx import ASGITransport

from src import main
from src.admin import jobs
from src.berita.schemas import HasilPanen
from tests.admin.bantu import aplikasi_admin
from tests.conftest import BASIS_URL_UJI, D1, D2, PembuatKlien

pytestmark = pytest.mark.anyio

IDDESA_TAK_DIKENAL = "1801049999"


def _panen_cepat(
    klien: object, pengaturan: object, iddesa: str, nmdesa: str, nmkab: str
) -> HasilPanen:
    """Fake instan: nol jaringan, langsung mengembalikan hasil panen kosong."""
    return HasilPanen(iddesa=iddesa, n_baru=0, n_duplikat=0, n_dibuang=0, n_gagal=0)


@pytest.mark.integration
async def test_segarkan_iddesa_tak_dikenal_kembalikan_404_dan_pekerjaan_tidak_dimulai(
    dir_data_lengkap: Path,
    env_admin: None,
    buat_klien: PembuatKlien,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(jobs, "panen_desa", _panen_cepat)
    app = aplikasi_admin()
    klien = await buat_klien(app, lifespan=True)

    respons = await klien.post(
        "/api/admin/berita/segarkan", json={"iddesa": [IDDESA_TAK_DIKENAL]}
    )

    assert respons.status_code == 404
    assert respons.json()["galat"]["kode"] == "DESA_TIDAK_ADA"
    assert app.state.pekerjaan_penyegaran is None


@pytest.mark.integration
async def test_segarkan_saat_pekerjaan_lain_berjalan_kembalikan_409(
    dir_data_lengkap: Path,
    env_admin: None,
    buat_klien: PembuatKlien,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    boleh_lanjut = threading.Event()
    sudah_masuk = threading.Event()

    def _panen_blokir(
        klien: object, pengaturan: object, iddesa: str, nmdesa: str, nmkab: str
    ) -> HasilPanen:
        sudah_masuk.set()
        boleh_lanjut.wait(timeout=5)
        return HasilPanen(iddesa=iddesa, n_baru=0, n_duplikat=0, n_dibuang=0, n_gagal=0)

    monkeypatch.setattr(jobs, "panen_desa", _panen_blokir)
    app = aplikasi_admin()
    klien = await buat_klien(app, lifespan=True)

    respons_pertama = await klien.post(
        "/api/admin/berita/segarkan", json={"iddesa": [D1]}
    )
    assert respons_pertama.status_code == 202

    for _ in range(200):
        if sudah_masuk.is_set():
            break
        await asyncio.sleep(0.01)
    assert sudah_masuk.is_set(), "panen_desa palsu tidak pernah terpanggil"

    respons_kedua = await klien.post(
        "/api/admin/berita/segarkan", json={"iddesa": [D2]}
    )

    assert respons_kedua.status_code == 409
    assert respons_kedua.json()["galat"]["kode"] == "PEKERJAAN_BERJALAN"

    boleh_lanjut.set()
    await app.state.tugas_penyegaran


@pytest.mark.integration
async def test_segarkan_sukses_kembalikan_202_dengan_id_pekerjaan(
    dir_data_lengkap: Path,
    env_admin: None,
    buat_klien: PembuatKlien,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(jobs, "panen_desa", _panen_cepat)
    app = aplikasi_admin()
    klien = await buat_klien(app, lifespan=True)

    respons = await klien.post("/api/admin/berita/segarkan", json={"iddesa": [D1, D2]})

    assert respons.status_code == 202
    body = respons.json()
    assert body["sukses"] is True
    assert body["data"]["n_desa"] == 2
    assert body["data"]["keadaan"] == "berjalan"
    assert body["data"]["id_pekerjaan"]

    tugas = app.state.tugas_penyegaran
    if tugas is not None:
        await tugas


@pytest.mark.integration
async def test_segarkan_duplikat_dihitung_satu_kali(
    dir_data_lengkap: Path,
    env_admin: None,
    buat_klien: PembuatKlien,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(jobs, "panen_desa", _panen_cepat)
    app = aplikasi_admin()
    klien = await buat_klien(app, lifespan=True)

    respons = await klien.post("/api/admin/berita/segarkan", json={"iddesa": [D1, D1]})

    assert respons.status_code == 202
    assert respons.json()["data"]["n_desa"] == 1

    tugas = app.state.tugas_penyegaran
    if tugas is not None:
        await tugas


@pytest.mark.integration
async def test_shutdown_saat_pekerjaan_berjalan_membatalkan_tugas(
    dir_data_lengkap: Path,
    env_admin: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Lifespan shutdown (`src/main.py`) WAJIB membatalkan `tugas_penyegaran`
    yang masih berjalan, supaya panen tidak bocor lewat siklus hidup app.

    Lifespan dikelola langsung di sini (bukan lewat fixture `buat_klien`,
    yang menutup lifespan-nya sendiri hanya di akhir test lewat
    `AsyncExitStack` milik fixture) supaya shutdown bisa dipicu SAAT
    `panen_desa` palsu masih diblokir `threading.Event`, sebelum
    pekerjaan sempat selesai wajar.
    """
    boleh_lanjut = threading.Event()
    sudah_masuk = threading.Event()

    def _panen_blokir(
        klien: object, pengaturan: object, iddesa: str, nmdesa: str, nmkab: str
    ) -> HasilPanen:
        sudah_masuk.set()
        boleh_lanjut.wait(timeout=5)
        return HasilPanen(iddesa=iddesa, n_baru=0, n_duplikat=0, n_dibuang=0, n_gagal=0)

    monkeypatch.setattr(jobs, "panen_desa", _panen_blokir)
    app = aplikasi_admin()
    tugas: asyncio.Task | None = None

    try:
        async with (
            app.router.lifespan_context(app),
            httpx.AsyncClient(
                transport=ASGITransport(app=app), base_url=BASIS_URL_UJI
            ) as klien,
        ):
            respons = await klien.post(
                "/api/admin/berita/segarkan", json={"iddesa": [D1]}
            )
            assert respons.status_code == 202

            for _ in range(200):
                if sudah_masuk.is_set():
                    break
                await asyncio.sleep(0.01)
            assert sudah_masuk.is_set(), "panen_desa palsu tidak pernah terpanggil"

            tugas = app.state.tugas_penyegaran
            assert tugas is not None
            assert not tugas.done()
        # Keluar dari blok `async with` di atas memicu shutdown src/main.py,
        # yang membatalkan tugas_penyegaran karena masih berjalan.

        for _ in range(200):
            if tugas.done():
                break
            await asyncio.sleep(0.01)
        assert tugas.cancelled()
    finally:
        boleh_lanjut.set()


@pytest.mark.integration
async def test_shutdown_tidak_menggantung_walau_panen_masih_blocking(
    dir_data_lengkap: Path,
    env_admin: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Shutdown WAJIB selesai dalam batas waktu walau thread `panen_desa`
    masih blocking.

    `panen_desa` blocking di `requests`/`time.sleep` di dalam
    `run_in_threadpool`, jadi `asyncio` tidak bisa menyela threadnya:
    menunggu tanpa batas menggantung shutdown selama menit-menit. Uji ini
    menahan panen palsu tetap blocking, lalu memastikan keluar dari
    lifespan tetap kembali dalam waktu wajar dan tidak melempar.
    """
    boleh_lanjut = threading.Event()
    sudah_masuk = threading.Event()

    def _panen_blokir(
        klien: object, pengaturan: object, iddesa: str, nmdesa: str, nmkab: str
    ) -> HasilPanen:
        sudah_masuk.set()
        boleh_lanjut.wait(timeout=30)
        return HasilPanen(iddesa=iddesa, n_baru=0, n_duplikat=0, n_dibuang=0, n_gagal=0)

    monkeypatch.setattr(jobs, "panen_desa", _panen_blokir)
    monkeypatch.setattr(main, "TENGGAT_SHUTDOWN_PEKERJAAN", 0.2)
    app = aplikasi_admin()

    try:
        mulai = asyncio.get_running_loop().time()
        async with (
            app.router.lifespan_context(app),
            httpx.AsyncClient(
                transport=ASGITransport(app=app), base_url=BASIS_URL_UJI
            ) as klien,
        ):
            assert (
                await klien.post("/api/admin/berita/segarkan", json={"iddesa": [D1]})
            ).status_code == 202
            for _ in range(200):
                if sudah_masuk.is_set():
                    break
                await asyncio.sleep(0.01)
            assert sudah_masuk.is_set()
        lama = asyncio.get_running_loop().time() - mulai
    finally:
        boleh_lanjut.set()

    # Tenggat 0,2 detik + ongkos permintaan; jauh di bawah 30 detik blokir
    # panen palsu, jadi ini membuktikan shutdown TIDAK menunggu threadnya.
    assert lama < 5.0, f"shutdown menggantung {lama:.2f}s"
