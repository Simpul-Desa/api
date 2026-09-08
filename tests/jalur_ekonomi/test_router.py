"""Uji integrasi untuk rute Jalur Ekonomi (`src/jalur_ekonomi/router.py`, Tugas 7)."""

from pathlib import Path

import httpx
import pytest

from src.jalur_ekonomi import router as router_jalur
from tests.conftest import D1, D2, D4, IDKAB_DUA, IDKAB_SATU, TARGET_CITRA

pytestmark = pytest.mark.anyio


@pytest.mark.integration
async def test_daftar_jalur_varian_tak_dikenal_kembalikan_422(
    dir_data_lengkap: Path, klien: httpx.AsyncClient
) -> None:
    respons = await klien.get("/api/model/jalur-ekonomi/varian-salah")

    assert respons.status_code == 422
    assert respons.json()["galat"]["kode"] == "PARAMETER_TIDAK_VALID"


@pytest.mark.integration
async def test_daftar_komoditas_id_deterministik_dan_meta_parameter(
    dir_data_lengkap: Path, klien: httpx.AsyncClient
) -> None:
    """Kab 1802 punya `komoditas: {}` — tidak menyumbang baris (bukan galat)."""
    respons = await klien.get("/api/model/jalur-ekonomi/komoditas")

    assert respons.status_code == 200
    body = respons.json()
    assert len(body["data"]) == 1
    baris = body["data"][0]
    assert baris["id_jalur"] == f"{IDKAB_SATU}-{TARGET_CITRA}-1"
    assert baris["idkab"] == IDKAB_SATU
    assert baris["poros"]["iddesa"] == D1
    assert baris["n_anggota"] == 2
    assert baris["bobot"] == 60
    assert baris["label"] == "Pisang Lainnya"
    assert body["meta"]["parameter"] == {"MIN_ANGGOTA": 2, "MAKS_ANGGOTA": 25}


@pytest.mark.integration
async def test_daftar_gudang_kopdes_satu_baris_per_kabupaten(
    dir_data_lengkap: Path, klien: httpx.AsyncClient
) -> None:
    respons = await klien.get("/api/model/jalur-ekonomi/gudang-kopdes")

    assert respons.status_code == 200
    body = respons.json()
    assert [b["id_jalur"] for b in body["data"]] == [
        f"{IDKAB_SATU}-gudang-1",
        f"{IDKAB_DUA}-gudang-1",
    ]
    assert all(b["label"] == "gudang" for b in body["data"])


@pytest.mark.integration
async def test_daftar_cold_storage_kab_tak_layak_hanya_baris_kab_lain(
    dir_data_lengkap: Path, klien: httpx.AsyncClient
) -> None:
    """Kab 1802 TAK_LAYAK (`cs_baru`/`cs_eksisting` kosong) tidak menghasilkan
    baris, dan permintaan tetap 200 — bukan galat."""
    respons = await klien.get("/api/model/jalur-ekonomi/cold-storage")

    assert respons.status_code == 200
    body = respons.json()
    assert [b["id_jalur"] for b in body["data"]] == [
        f"{IDKAB_SATU}-cs-baru-1",
        f"{IDKAB_SATU}-cs-eksisting-1",
    ]
    assert all(b["idkab"] == IDKAB_SATU for b in body["data"])


@pytest.mark.integration
async def test_daftar_cold_storage_filter_kab_tak_layak_kembalikan_kosong_bukan_galat(
    dir_data_lengkap: Path, klien: httpx.AsyncClient
) -> None:
    respons = await klien.get(
        "/api/model/jalur-ekonomi/cold-storage", params={"kab": IDKAB_DUA}
    )

    assert respons.status_code == 200
    assert respons.json()["data"] == []


@pytest.mark.integration
async def test_daftar_jalur_filter_kab_tak_dikenal_kembalikan_404(
    dir_data_lengkap: Path, klien: httpx.AsyncClient
) -> None:
    respons = await klien.get(
        "/api/model/jalur-ekonomi/komoditas", params={"kab": "9999"}
    )

    assert respons.status_code == 404
    assert respons.json()["galat"]["kode"] == "WILAYAH_TIDAK_ADA"


@pytest.mark.integration
async def test_daftar_komoditas_filter_iddesa_ditemukan_lewat_poros(
    dir_data_lengkap: Path, klien: httpx.AsyncClient
) -> None:
    respons = await klien.get(
        "/api/model/jalur-ekonomi/komoditas", params={"iddesa": D1}
    )

    assert respons.status_code == 200
    body = respons.json()
    assert len(body["data"]) == 1
    assert body["data"][0]["poros"]["iddesa"] == D1


@pytest.mark.integration
async def test_daftar_komoditas_filter_iddesa_ditemukan_lewat_anggota(
    dir_data_lengkap: Path, klien: httpx.AsyncClient
) -> None:
    """`D2` bukan poros grup ini — hanya anggota — tapi tetap ditemukan."""
    respons = await klien.get(
        "/api/model/jalur-ekonomi/komoditas", params={"iddesa": D2}
    )

    assert respons.status_code == 200
    body = respons.json()
    assert len(body["data"]) == 1
    assert body["data"][0]["poros"]["iddesa"] == D1


@pytest.mark.integration
async def test_daftar_komoditas_filter_iddesa_tidak_ditemukan_kembalikan_kosong(
    dir_data_lengkap: Path, klien: httpx.AsyncClient
) -> None:
    respons = await klien.get(
        "/api/model/jalur-ekonomi/komoditas", params={"iddesa": D4}
    )

    assert respons.status_code == 200
    assert respons.json()["data"] == []


@pytest.mark.integration
async def test_detail_jalur_ditemukan_grup_utuh_dengan_id_jalur(
    dir_data_lengkap: Path, klien: httpx.AsyncClient
) -> None:
    id_jalur = f"{IDKAB_SATU}-{TARGET_CITRA}-1"
    respons = await klien.get(f"/api/model/jalur-ekonomi/komoditas/{id_jalur}")

    assert respons.status_code == 200
    body = respons.json()["data"]
    assert body["id_jalur"] == id_jalur
    assert body["volume"] == 60
    assert len(body["anggota"]) == 2
    assert body["anggota"][1]["iddesa"] == D2


@pytest.mark.integration
async def test_detail_jalur_tidak_ditemukan_kembalikan_404(
    dir_data_lengkap: Path, klien: httpx.AsyncClient
) -> None:
    respons = await klien.get("/api/model/jalur-ekonomi/komoditas/tidak-ada-id")

    assert respons.status_code == 404
    assert respons.json()["galat"]["kode"] == "TIDAK_DITEMUKAN"


@pytest.mark.integration
async def test_detail_cs_eksisting_grup_utuh_id_cs_tetap_di_payload(
    dir_data_lengkap: Path, klien: httpx.AsyncClient
) -> None:
    """`id_cs` bukan id publik (`id_jalur` yang dipakai router) — tapi tetap
    ikut di payload grup utuh apa adanya."""
    id_jalur = f"{IDKAB_SATU}-cs-eksisting-1"
    respons = await klien.get(f"/api/model/jalur-ekonomi/cold-storage/{id_jalur}")

    assert respons.status_code == 200
    body = respons.json()["data"]
    assert body["id_jalur"] == id_jalur
    assert body["id_cs"] == 1
    assert body["kapasitas_ton"] == 500.0


@pytest.mark.integration
async def test_daftar_wisata_regresi_placeholder_koordinat_tidak_ada(
    dir_data_lengkap: Path, klien: httpx.AsyncClient
) -> None:
    respons = await klien.get("/api/model/jalur-ekonomi/wisata")

    assert respons.status_code == 200
    assert "-6.2297465" not in respons.text
    assert "106.829518" not in respons.text


@pytest.mark.integration
async def test_daftar_wisata_label_kategori_basis(
    dir_data_lengkap: Path, klien: httpx.AsyncClient
) -> None:
    respons = await klien.get("/api/model/jalur-ekonomi/wisata")

    assert respons.status_code == 200
    body = respons.json()
    labels = {b["idkab"]: b["label"] for b in body["data"]}
    assert labels[IDKAB_SATU] == "BERKEMBANG"
    assert labels[IDKAB_DUA] == "RINTISAN"


@pytest.mark.integration
async def test_daftar_jalur_paginasi_batas_memotong_hasil(
    dir_data_lengkap: Path, klien: httpx.AsyncClient
) -> None:
    respons = await klien.get(
        "/api/model/jalur-ekonomi/gudang-kopdes", params={"batas": 1}
    )

    assert respons.status_code == 200
    body = respons.json()
    assert len(body["data"]) == 1
    assert body["meta"]["total"] == 2


@pytest.mark.integration
async def test_grup_hilang_dari_hasil_yang_sama_kembalikan_500_beramplop(
    dir_data_lengkap: Path,
    klien: httpx.AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Penjaga invarian internal: `ratakan()` dan `cari_grup()` membaca
    `hasil` yang SAMA, jadi grupnya selalu ada.

    Kalau invarian itu pecah, jawabannya harus 500 beramplop dengan jejak di
    log — bukan `TypeError` buram di pemanggil. `RuntimeError` dipakai
    (bukan `assert`) justru karena `assert` hilang saat Python dijalankan
    dengan `-O`.
    """
    # `_grup_dari_baris` hanya dipanggil pada jalur filter `?iddesa=`
    # (router.py:97) — di situlah penjaga invariannya berada.
    monkeypatch.setattr(router_jalur, "cari_grup", lambda *a, **k: None)

    # Header `Origin` disertakan dengan sengaja: `MiddlewareCORS` yang
    # menangkap 500 tak terduga untuk permintaan ber-Origin (respons handler
    # galat global tidak melewati middleware itu lagi), jadi inilah jalur
    # yang benar-benar dilihat browser — dan yang membuktikan amplopnya utuh.
    respons = await klien.get(
        f"/api/model/jalur-ekonomi/komoditas?iddesa={D1}",
        headers={"Origin": "http://localhost:3000"},
    )

    assert respons.status_code == 500
    assert respons.json()["galat"]["kode"] == "GALAT_SERVER"
