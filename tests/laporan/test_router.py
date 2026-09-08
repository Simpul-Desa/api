"""Uji integrasi untuk GET /api/laporan/{iddesa} (Fase 8 Tugas 5-6)."""

from dataclasses import replace
from pathlib import Path

import pytest
from fastapi import FastAPI

from src.auth.dependencies import wajib_pemerintah
from tests.conftest import D1, D3, PembuatKlien

pytestmark = pytest.mark.anyio

IDDESA_POLA_SALAH = "180104000"  # 9 digit
IDDESA_TAK_DIKENAL = "1801049999"  # 10 digit, tak ada di indeks kartu


@pytest.fixture
def aplikasi_pemerintah(aplikasi: FastAPI) -> FastAPI:
    # Nilai balik dependensi TIDAK dibaca rute ini - string polos cukup.
    aplikasi.dependency_overrides[wajib_pemerintah] = lambda: "pemerintah"
    return aplikasi


@pytest.mark.integration
async def test_laporan_sukses_kembalikan_pdf(
    dir_data_lengkap: Path,
    aplikasi_pemerintah: FastAPI,
    buat_klien: PembuatKlien,
) -> None:
    klien = await buat_klien(aplikasi_pemerintah, lifespan=True)

    respons = await klien.get(f"/api/laporan/{D1}")

    assert respons.status_code == 200
    assert "application/pdf" in respons.headers["content-type"]
    assert respons.content.startswith(b"%PDF-")


@pytest.mark.integration
async def test_laporan_content_disposition_persis(
    dir_data_lengkap: Path,
    aplikasi_pemerintah: FastAPI,
    buat_klien: PembuatKlien,
) -> None:
    klien = await buat_klien(aplikasi_pemerintah, lifespan=True)

    respons = await klien.get(f"/api/laporan/{D1}")

    assert respons.status_code == 200
    assert (
        respons.headers["content-disposition"]
        == f'attachment; filename="laporan-desa-{D1}.pdf"'
    )


@pytest.mark.integration
async def test_laporan_cache_control_private_no_store_tanpa_etag(
    dir_data_lengkap: Path,
    aplikasi_pemerintah: FastAPI,
    buat_klien: PembuatKlien,
) -> None:
    klien = await buat_klien(aplikasi_pemerintah, lifespan=True)

    respons = await klien.get(f"/api/laporan/{D1}")

    assert respons.status_code == 200
    assert respons.headers["cache-control"] == "private, no-store"
    assert "etag" not in respons.headers


@pytest.mark.integration
async def test_laporan_iddesa_pola_salah_kembalikan_422(
    dir_data_lengkap: Path,
    aplikasi_pemerintah: FastAPI,
    buat_klien: PembuatKlien,
) -> None:
    klien = await buat_klien(aplikasi_pemerintah, lifespan=True)

    respons = await klien.get(f"/api/laporan/{IDDESA_POLA_SALAH}")

    assert respons.status_code == 422
    assert respons.json()["galat"]["kode"] == "PARAMETER_TIDAK_VALID"


@pytest.mark.integration
async def test_laporan_iddesa_tak_dikenal_kembalikan_404(
    dir_data_lengkap: Path,
    aplikasi_pemerintah: FastAPI,
    buat_klien: PembuatKlien,
) -> None:
    klien = await buat_klien(aplikasi_pemerintah, lifespan=True)

    respons = await klien.get(f"/api/laporan/{IDDESA_TAK_DIKENAL}")

    assert respons.status_code == 404
    body = respons.json()
    assert body["sukses"] is False
    assert body["galat"]["kode"] == "DESA_TIDAK_ADA"


@pytest.mark.integration
async def test_laporan_tanpa_baris_peta_peran_kembalikan_404(
    dir_data_lengkap: Path,
    aplikasi_pemerintah: FastAPI,
    buat_klien: PembuatKlien,
) -> None:
    """`D1` dikenal di indeks kartu, tapi baris Peta Peran-nya dihapus manual.

    Dihapus dari `app.state.simpanan` saat runtime (bukan dari fixture
    `dir_data_lengkap` bersama) supaya test lain tidak ikut terpengaruh.
    """
    klien = await buat_klien(aplikasi_pemerintah, lifespan=True)
    del aplikasi_pemerintah.state.simpanan.peta_peran_per_desa[D1]

    respons = await klien.get(f"/api/laporan/{D1}")

    assert respons.status_code == 404
    body = respons.json()
    assert body["sukses"] is False
    assert body["galat"]["kode"] == "DESA_TIDAK_ADA"


@pytest.mark.integration
async def test_laporan_tanpa_data_kembalikan_503(
    dir_data_manifest: Path,
    aplikasi_pemerintah: FastAPI,
    buat_klien: PembuatKlien,
) -> None:
    """`dir_data_manifest` cuma punya manifest.json - indeks kartu belum ada."""
    klien = await buat_klien(aplikasi_pemerintah, lifespan=True)

    respons = await klien.get(f"/api/laporan/{D1}")

    assert respons.status_code == 503
    body = respons.json()
    assert body["sukses"] is False
    assert body["galat"]["kode"] == "DATA_BELUM_SIAP"


@pytest.mark.integration
async def test_laporan_desa_belum_terpetakan_tetap_200_pdf(
    dir_data_lengkap: Path,
    aplikasi_pemerintah: FastAPI,
    buat_klien: PembuatKlien,
) -> None:
    """`D3`: zona Belum Terpetakan, keyakinan kosong, kartu minim blok."""
    klien = await buat_klien(aplikasi_pemerintah, lifespan=True)

    respons = await klien.get(f"/api/laporan/{D3}")

    assert respons.status_code == 200
    assert "application/pdf" in respons.headers["content-type"]
    assert respons.content.startswith(b"%PDF-")


@pytest.mark.integration
async def test_laporan_desa_hilang_dari_berkas_kartu_kembalikan_404(
    dir_data_lengkap: Path,
    aplikasi_pemerintah: FastAPI,
    buat_klien: PembuatKlien,
) -> None:
    """Desa terdaftar di indeks tetapi tidak ada di berkas kartu kabupatennya.

    Cabang 404 kedua rute ini — indeks dan berkas kartu adalah dua artefak
    terpisah, jadi keduanya bisa tidak sinkron. Kondisinya dibuat dengan
    menambah satu entri indeks di `app.state`, bukan dengan mengubah
    fixture bersama.
    """
    klien = await buat_klien(aplikasi_pemerintah, lifespan=True)
    simpanan = aplikasi_pemerintah.state.simpanan
    iddesa_hantu = "1801049998"
    aplikasi_pemerintah.state.simpanan = replace(
        simpanan,
        indeks_per_desa={
            **(simpanan.indeks_per_desa or {}),
            iddesa_hantu: {"iddesa": iddesa_hantu, "idkab": "1801"},
        },
    )

    respons = await klien.get(f"/api/laporan/{iddesa_hantu}")

    assert respons.status_code == 404
    assert respons.json()["galat"]["kode"] == "DESA_TIDAK_ADA"


@pytest.mark.integration
async def test_wilayah_hilang_tetap_200_pdf(
    dir_data_lengkap: Path,
    aplikasi_pemerintah: FastAPI,
    buat_klien: PembuatKlien,
) -> None:
    """Artefak `wilayah.json` hilang tidak boleh menjatuhkan rute jadi 503.

    Nama provinsi cuma hiasan judul; kartu sudah membawa kode provinsinya
    sendiri sebagai cadangan. Karena itu `_nama_provinsi` sengaja TIDAK
    memakai `wajib()`.
    """
    klien = await buat_klien(aplikasi_pemerintah, lifespan=True)
    aplikasi_pemerintah.state.simpanan = replace(
        aplikasi_pemerintah.state.simpanan, wilayah=None
    )

    respons = await klien.get(f"/api/laporan/{D1}")

    assert respons.status_code == 200
    assert respons.content.startswith(b"%PDF-")


@pytest.mark.integration
async def test_baris_indeks_tanpa_idkab_kembalikan_503(
    dir_data_lengkap: Path,
    aplikasi_pemerintah: FastAPI,
    buat_klien: PembuatKlien,
) -> None:
    """Baris indeks kartu tanpa `idkab` = indeks cacat, bukan desa tak dikenal.

    503 DATA_BELUM_SIAP menunjuk build datanya; 500 GALAT_SERVER akan
    menyesatkan pemanggil bahwa servernya yang rusak.
    """
    klien = await buat_klien(aplikasi_pemerintah, lifespan=True)
    simpanan = aplikasi_pemerintah.state.simpanan
    iddesa_tanpa_kab = "1801049996"
    aplikasi_pemerintah.state.simpanan = replace(
        simpanan,
        indeks_per_desa={
            **(simpanan.indeks_per_desa or {}),
            iddesa_tanpa_kab: {"iddesa": iddesa_tanpa_kab},
        },
    )

    respons = await klien.get(f"/api/laporan/{iddesa_tanpa_kab}")

    assert respons.status_code == 503
    assert respons.json()["galat"]["kode"] == "DATA_BELUM_SIAP"
