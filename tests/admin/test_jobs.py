"""Uji mesin state pekerjaan latar penyegaran Berita Desa (`src/admin/jobs.py`).

`panen_desa` SELALU ditambal (`monkeypatch.setattr(jobs, "panen_desa", ...)`)
supaya berkas uji ini nol jaringan dan selesai jauh di bawah 5 detik — panen
sungguhan memakai `time.sleep` per artikel dan memanggil Gemini/RSS asli.
"""

import asyncio
import threading

import pytest
from fastapi import FastAPI

from src.admin import jobs
from src.berita.schemas import HasilPanen

pytestmark = pytest.mark.anyio

DESA_A = ("1801040001", "Desa A", "Kab Satu")
DESA_B = ("1801040002", "Desa B", "Kab Satu")


async def test_mulai_memasang_keadaan_berjalan(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dipanggil: list[str] = []

    def _panen_palsu(
        klien: object, pengaturan: object, iddesa: str, nmdesa: str, nmkab: str
    ) -> HasilPanen:
        dipanggil.append(iddesa)
        return HasilPanen(iddesa=iddesa, n_baru=1, n_duplikat=0, n_dibuang=0, n_gagal=0)

    monkeypatch.setattr(jobs, "panen_desa", _panen_palsu)
    app = FastAPI()

    pekerjaan = jobs.mulai(app, [DESA_A])

    assert pekerjaan.keadaan == "berjalan"
    assert pekerjaan.total == 1
    assert pekerjaan.selesai == 0
    assert app.state.pekerjaan_penyegaran is pekerjaan
    assert app.state.tugas_penyegaran is not None

    await app.state.tugas_penyegaran

    assert dipanggil == [DESA_A[0]]


async def test_pekerjaan_selesai_mengumpulkan_hasil_per_desa(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _panen_palsu(
        klien: object, pengaturan: object, iddesa: str, nmdesa: str, nmkab: str
    ) -> HasilPanen:
        return HasilPanen(iddesa=iddesa, n_baru=3, n_duplikat=1, n_dibuang=2, n_gagal=4)

    monkeypatch.setattr(jobs, "panen_desa", _panen_palsu)
    app = FastAPI()

    jobs.mulai(app, [DESA_A, DESA_B])
    await app.state.tugas_penyegaran

    pekerjaan = app.state.pekerjaan_penyegaran
    assert pekerjaan.keadaan == "selesai"
    assert pekerjaan.selesai == pekerjaan.total == 2
    assert pekerjaan.selesai_pada is not None
    assert [h.iddesa for h in pekerjaan.hasil] == [DESA_A[0], DESA_B[0]]
    assert [h.n_baru for h in pekerjaan.hasil] == [3, 3]
    assert [h.n_duplikat for h in pekerjaan.hasil] == [1, 1]
    assert [h.n_dibuang for h in pekerjaan.hasil] == [2, 2]
    # FIX 1: n_gagal hasil_panen harus ikut mengalir ke HasilPenyegaranDesa.
    assert [h.n_gagal for h in pekerjaan.hasil] == [4, 4]
    assert all(h.galat is None for h in pekerjaan.hasil)


async def test_desa_gagal_tidak_menghentikan_desa_berikutnya(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _panen_palsu(
        klien: object, pengaturan: object, iddesa: str, nmdesa: str, nmkab: str
    ) -> HasilPanen:
        if iddesa == DESA_A[0]:
            raise RuntimeError("rss mati total")
        return HasilPanen(iddesa=iddesa, n_baru=5, n_duplikat=0, n_dibuang=0, n_gagal=0)

    monkeypatch.setattr(jobs, "panen_desa", _panen_palsu)
    app = FastAPI()

    jobs.mulai(app, [DESA_A, DESA_B])
    await app.state.tugas_penyegaran

    pekerjaan = app.state.pekerjaan_penyegaran
    assert pekerjaan.keadaan == "selesai"
    assert pekerjaan.selesai == pekerjaan.total == 2
    assert pekerjaan.hasil[0].iddesa == DESA_A[0]
    assert pekerjaan.hasil[0].galat == "rss mati total"
    assert pekerjaan.hasil[0].n_baru == 0
    # FIX 1: seluruh desa gagal (bukan satu artikel) — tak ada cacah
    # per-artikel yang berarti di sini, jadi n_gagal 0, bukan ditebak.
    # `galat` sudah membawa kegagalan tingkat desa; lihat komentar di jobs.py.
    assert pekerjaan.hasil[0].n_gagal == 0
    assert pekerjaan.hasil[1].iddesa == DESA_B[0]
    assert pekerjaan.hasil[1].galat is None
    assert pekerjaan.hasil[1].n_baru == 5


async def test_sedang_berjalan_true_saat_pekerjaan_hidup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    boleh_lanjut = threading.Event()
    sudah_masuk = threading.Event()

    def _panen_palsu(
        klien: object, pengaturan: object, iddesa: str, nmdesa: str, nmkab: str
    ) -> HasilPanen:
        sudah_masuk.set()
        boleh_lanjut.wait(timeout=5)
        return HasilPanen(iddesa=iddesa, n_baru=0, n_duplikat=0, n_dibuang=0)

    monkeypatch.setattr(jobs, "panen_desa", _panen_palsu)
    app = FastAPI()

    assert jobs.sedang_berjalan(app) is False

    jobs.mulai(app, [DESA_A])

    for _ in range(200):
        if sudah_masuk.is_set():
            break
        await asyncio.sleep(0.01)
    assert sudah_masuk.is_set(), "panen_desa palsu tidak pernah terpanggil"

    assert jobs.sedang_berjalan(app) is True

    boleh_lanjut.set()
    await app.state.tugas_penyegaran

    assert jobs.sedang_berjalan(app) is False


def test_ke_skema_none_saat_belum_pernah_ada_pekerjaan() -> None:
    assert jobs.ke_skema(None) is None


async def test_ke_skema_memproyeksikan_pekerjaan_selesai_beserta_hasilnya(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`ke_skema` dengan pekerjaan nyata — bentuk inilah yang dibaca `/api/admin/status`.

    Uji `ke_skema(None)` saja meninggalkan seluruh proyeksi ke
    `StatusPekerjaan` tanpa cakupan, padahal itu badan respons yang dipakai
    admin untuk memantau kemajuan.
    """

    def _panen_palsu(
        klien: object, pengaturan: object, iddesa: str, nmdesa: str, nmkab: str
    ) -> HasilPanen:
        return HasilPanen(iddesa=iddesa, n_baru=2, n_duplikat=1, n_dibuang=0, n_gagal=0)

    monkeypatch.setattr(jobs, "panen_desa", _panen_palsu)
    app = FastAPI()

    pekerjaan = jobs.mulai(app, [DESA_A, DESA_B])
    await app.state.tugas_penyegaran

    skema = jobs.ke_skema(app.state.pekerjaan_penyegaran)

    assert skema is not None
    assert skema.id_pekerjaan == pekerjaan.id_pekerjaan
    assert skema.keadaan == "selesai"
    assert skema.total == 2
    assert skema.selesai == 2
    assert skema.mulai_pada == pekerjaan.mulai_pada
    assert skema.selesai_pada is not None
    assert isinstance(skema.hasil, list)
    assert [h.iddesa for h in skema.hasil] == [DESA_A[0], DESA_B[0]]
    assert [h.n_baru for h in skema.hasil] == [2, 2]
    assert all(h.galat is None for h in skema.hasil)
