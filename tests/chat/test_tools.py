"""Uji unit alat function calling Asisten Desa (`src/chat/tools.py`).

`Simpanan` nyata dimuat langsung lewat `src.datastore.muat_simpanan` atas
`dir_data_lengkap` (Tugas 4 rencana fase 5) — tidak ada aplikasi FastAPI yang
dibangun sama sekali, sesuai kontrak `KonteksAlat` (alat harus bisa diuji
tanpa `Request`). PostgREST Supabase distub lewat `httpx.MockTransport`.
"""

import json
import logging
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest

from src.chat import tools
from src.chat.constants import (
    ALAT_TIDAK_DIKENAL,
    ARGUMEN_TIDAK_SAH,
    MAKS_BARIS_ALAT,
    MAKS_BARIS_BERITA,
)
from src.chat.tools import DEKLARASI_ALAT, KonteksAlat, _potong, jalankan_alat
from src.citra_potensi.service import baca_sel_citra
from src.config import ambil_pengaturan
from src.datastore import muat_simpanan
from src.desa_kembar.constants import KETERANGAN_TANPA_VEKTOR
from src.exceptions import DATA_BELUM_SIAP, DESA_TIDAK_ADA, TIDAK_DITEMUKAN
from tests.conftest import D1, D2, D3, IDKAB_SATU, IDPROV, TARGET_CITRA

pytestmark = [pytest.mark.unit, pytest.mark.anyio]

IDDESA_TAK_DIKENAL = "9999999999"
NAMA_ALAT_IDDESA = ["kartu_ekonomi", "peta_peran", "desa_kembar", "berita_desa"]


class _SimpananMeledak:
    """Pengganti `Simpanan` yang meledak begitu atribut apa pun diakses.

    Membuktikan bahwa `_argumen_sah` menolak SEBELUM menyentuh data sama
    sekali — bila `jalankan_alat` sampai mengakses `konteks.simpanan.<apa
    pun>` sebelum menolak argumen tidak sah, uji ini gagal lewat
    `AssertionError`, bukan lewat pembacaan nilai yang salah.
    """

    def __getattr__(self, nama: str) -> Any:
        raise AssertionError(
            f"argumen tidak sah semestinya menolak sebelum menyentuh {nama}"
        )


def _item_berita(id_: int) -> dict[str, Any]:
    """Satu baris `berita_desa` sah menurut `src/berita/schemas.py::ItemBerita`."""
    return {
        "id": id_,
        "judul": f"Judul {id_}",
        "url": f"https://contoh.id/{id_}",
        "sumber": "Contoh",
        "terbit_pada": "2026-09-01T00:00:00+00:00",
        "dipanen_pada": "2026-09-02T00:00:00+00:00",
        "rangkuman": f"Rangkuman {id_}.",
        "kategori": ["Wisata"],
        "perangkum": "gemini",
    }


@pytest.fixture
def env_supabase(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """`SUPABASE_URL` absolut supaya `baris_berita` merakit URL yang sah untuk MockTransport."""
    monkeypatch.setenv("SUPABASE_URL", "https://uji.supabase.co")
    ambil_pengaturan.cache_clear()

    yield

    ambil_pengaturan.cache_clear()


@pytest.fixture
def konteks(dir_data_lengkap: Path, env_supabase: None) -> KonteksAlat:
    """`KonteksAlat` atas `Simpanan` nyata; Supabase membalas satu berita bawaan."""
    simpanan = muat_simpanan(dir_data_lengkap)
    klien = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json=[_item_berita(1)])
        )
    )
    return KonteksAlat(simpanan=simpanan, klien_supabase=klien)


@pytest.fixture
def konteks_berita_banyak(dir_data_lengkap: Path, env_supabase: None) -> KonteksAlat:
    """`KonteksAlat` dengan Supabase membalas 15 berita — uji pemotongan."""
    simpanan = muat_simpanan(dir_data_lengkap)
    baris = [_item_berita(i) for i in range(1, 16)]
    klien = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json=baris))
    )
    return KonteksAlat(simpanan=simpanan, klien_supabase=klien)


@pytest.fixture
def konteks_berita_gagal(dir_data_lengkap: Path, env_supabase: None) -> KonteksAlat:
    """`KonteksAlat` dengan Supabase mati (galat jaringan)."""
    simpanan = muat_simpanan(dir_data_lengkap)

    def _handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("gagal jaringan", request=request)

    klien = httpx.AsyncClient(transport=httpx.MockTransport(_handler))
    return KonteksAlat(simpanan=simpanan, klien_supabase=klien)


@pytest.fixture
def konteks_tak_boleh_disentuh(env_supabase: None) -> KonteksAlat:
    """`KonteksAlat` bersimpanan `_SimpananMeledak` — dipakai uji argumen tidak sah."""
    klien = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json=[]))
    )
    return KonteksAlat(simpanan=_SimpananMeledak(), klien_supabase=klien)  # type: ignore[arg-type]


# --- 1. DEKLARASI_ALAT ------------------------------------------------------


def test_deklarasi_alat_berisi_sembilan_nama_yang_diharapkan() -> None:
    nama = {d.name for d in DEKLARASI_ALAT}
    assert nama == {
        "cari_desa",
        "kartu_ekonomi",
        "peta_peran",
        "desa_kembar",
        "jalur_ekonomi",
        "berita_desa",
        "citra_potensi",
        "wilayah_ringkasan",
        "cek_cakupan_wilayah",
    }
    assert len(DEKLARASI_ALAT) == 9


# --- 2. tiap alat sukses pada masukan sah -----------------------------------


async def test_cari_desa_mengembalikan_kandidat_terurut(konteks: KonteksAlat) -> None:
    hasil = await jalankan_alat("cari_desa", {"nama": "desa a"}, konteks)

    assert "galat" not in hasil
    assert hasil["total"] == 3
    assert hasil["terpotong"] is False
    assert [b["iddesa"] for b in hasil["data"]] == [D1, D2, D3]


async def test_kartu_ekonomi_mengembalikan_kartu_utuh(konteks: KonteksAlat) -> None:
    hasil = await jalankan_alat("kartu_ekonomi", {"iddesa": D1}, konteks)

    assert "galat" not in hasil
    assert hasil["identitas"]["iddesa"] == D1
    assert "peta_peran" in hasil
    assert "mutu_data" in hasil


async def test_peta_peran_mengembalikan_baris_penuh(konteks: KonteksAlat) -> None:
    hasil = await jalankan_alat("peta_peran", {"iddesa": D2}, konteks)

    assert "galat" not in hasil
    assert hasil["iddesa"] == D2
    assert hasil["keyakinan"] == "rendah"
    assert hasil["sumber_dominan"] == "heuristik-belum-teruji"


async def test_desa_kembar_mengembalikan_tetangga_terjoin(konteks: KonteksAlat) -> None:
    hasil = await jalankan_alat("desa_kembar", {"iddesa": D1}, konteks)

    assert "galat" not in hasil
    assert hasil["iddesa"] == D1
    assert hasil["tetangga"] == [
        {
            "iddesa": D2,
            "nmdesa": "DESA A2",
            "nmkec": "KEC ALFA",
            "idkab": IDKAB_SATU,
            "nmkab": "KAB SATU",
            "persen": 50.0,
        }
    ]
    assert "keterangan" not in hasil


async def test_jalur_ekonomi_mengembalikan_baris_ringkas_dan_parameter(
    konteks: KonteksAlat,
) -> None:
    hasil = await jalankan_alat("jalur_ekonomi", {"varian": "komoditas"}, konteks)

    assert "galat" not in hasil
    assert hasil["total"] == 1
    assert hasil["terpotong"] is False
    assert hasil["data"][0]["id_jalur"] == f"{IDKAB_SATU}-{TARGET_CITRA}-1"
    assert hasil["parameter"] == {"MIN_ANGGOTA": 2, "MAKS_ANGGOTA": 25}


async def test_berita_desa_mengembalikan_daftar_terproyeksi(
    konteks: KonteksAlat,
) -> None:
    hasil = await jalankan_alat("berita_desa", {"iddesa": D1}, konteks)

    assert "galat" not in hasil
    assert hasil["total"] == 1
    assert hasil["data"] == [
        {
            "judul": "Judul 1",
            "sumber": "Contoh",
            "terbit_pada": "2026-09-01T00:00:00+00:00",
            "rangkuman": "Rangkuman 1.",
        }
    ]


async def test_citra_potensi_mengembalikan_skor(konteks: KonteksAlat) -> None:
    hasil = await jalankan_alat(
        "citra_potensi", {"prov": IDPROV, "target": TARGET_CITRA}, konteks
    )

    assert "galat" not in hasil
    assert hasil["prov"] == IDPROV
    assert hasil["target"] == TARGET_CITRA
    assert hasil["total"] == 3
    assert hasil["terpotong"] is False


async def test_wilayah_ringkasan_mengembalikan_ringkasan(konteks: KonteksAlat) -> None:
    hasil = await jalankan_alat("wilayah_ringkasan", {}, konteks)

    assert "galat" not in hasil
    assert hasil["n_provinsi"] == 1
    assert hasil["n_kabupaten"] == 2
    assert hasil["n_desa"] == 6


# --- 3. alat tak dikenal -----------------------------------------------------


async def test_alat_tak_dikenal_mengembalikan_kode(konteks: KonteksAlat) -> None:
    hasil = await jalankan_alat("alat_siluman", {}, konteks)

    assert hasil == {"galat": ALAT_TIDAK_DIKENAL}


# --- 4. iddesa tak dikenal ---------------------------------------------------


@pytest.mark.parametrize("nama_alat", NAMA_ALAT_IDDESA)
async def test_iddesa_tak_dikenal_mengembalikan_desa_tidak_ada(
    nama_alat: str, konteks: KonteksAlat
) -> None:
    hasil = await jalankan_alat(nama_alat, {"iddesa": IDDESA_TAK_DIKENAL}, konteks)

    assert hasil == {"galat": DESA_TIDAK_ADA}


# --- 5. iddesa bentuk tidak sah ----------------------------------------------


@pytest.mark.parametrize(
    "iddesa_tak_sah",
    ["1801040001\n", "١٨٠١٠٤٠٠٠١"],
    ids=["newline-penutup", "digit-arab-indic"],
)
async def test_iddesa_bentuk_tak_sah_mengembalikan_argumen_tidak_sah(
    iddesa_tak_sah: str, konteks: KonteksAlat
) -> None:
    hasil = await jalankan_alat("kartu_ekonomi", {"iddesa": iddesa_tak_sah}, konteks)

    assert hasil == {"galat": ARGUMEN_TIDAK_SAH}


# --- 6. cari_desa nama di luar rentang panjang -------------------------------


async def test_cari_desa_nama_satu_huruf_mengembalikan_argumen_tidak_sah(
    konteks: KonteksAlat,
) -> None:
    hasil = await jalankan_alat("cari_desa", {"nama": "a"}, konteks)

    assert hasil == {"galat": ARGUMEN_TIDAK_SAH}


async def test_cari_desa_nama_seratus_satu_huruf_mengembalikan_argumen_tidak_sah(
    konteks: KonteksAlat,
) -> None:
    hasil = await jalankan_alat("cari_desa", {"nama": "a" * 101}, konteks)

    assert hasil == {"galat": ARGUMEN_TIDAK_SAH}


# --- 7. jalur_ekonomi varian tak dikenal -------------------------------------


async def test_jalur_ekonomi_varian_tak_dikenal_mengembalikan_argumen_tidak_sah(
    konteks: KonteksAlat,
) -> None:
    hasil = await jalankan_alat("jalur_ekonomi", {"varian": "saham"}, konteks)

    assert hasil == {"galat": ARGUMEN_TIDAK_SAH}


# --- 8. argumen tidak sah menolak TANPA menyentuh data -----------------------


async def test_argumen_tidak_sah_menolak_tanpa_menyentuh_simpanan(
    konteks_tak_boleh_disentuh: KonteksAlat,
) -> None:
    hasil = await jalankan_alat(
        "kartu_ekonomi", {"iddesa": "bukan-iddesa"}, konteks_tak_boleh_disentuh
    )

    assert hasil == {"galat": ARGUMEN_TIDAK_SAH}


# --- 9. desa_kembar tanpa vektor: jalur anggun, bukan galat ------------------


async def test_desa_kembar_tanpa_vektor_mengembalikan_keterangan(
    konteks: KonteksAlat,
) -> None:
    hasil = await jalankan_alat("desa_kembar", {"iddesa": D3}, konteks)

    assert hasil == {
        "iddesa": D3,
        "tetangga": [],
        "keterangan": KETERANGAN_TANPA_VEKTOR,
    }


# --- 10. berita_desa memotong + tanpa kolom url ------------------------------


async def test_berita_desa_memotong_ke_maks_baris_berita_tanpa_url(
    konteks_berita_banyak: KonteksAlat,
) -> None:
    hasil = await jalankan_alat("berita_desa", {"iddesa": D1}, konteks_berita_banyak)

    assert hasil["total"] == 15
    assert hasil["terpotong"] is True
    assert len(hasil["data"]) == MAKS_BARIS_BERITA
    assert all("url" not in baris for baris in hasil["data"])


# --- 11. berita_desa saat Supabase mati --------------------------------------


async def test_berita_desa_supabase_mati_mengembalikan_data_belum_siap(
    konteks_berita_gagal: KonteksAlat,
) -> None:
    hasil = await jalankan_alat("berita_desa", {"iddesa": D1}, konteks_berita_gagal)

    assert hasil == {"galat": DATA_BELUM_SIAP}


# --- 12. _potong ---------------------------------------------------------


def test_potong_menandai_terpotong_dan_total_untuk_daftar_panjang() -> None:
    baris = list(range(25))

    hasil = _potong(baris, MAKS_BARIS_ALAT)

    assert hasil["total"] == 25
    assert hasil["terpotong"] is True
    assert len(hasil["data"]) == MAKS_BARIS_ALAT


# --- 13. citra_potensi prov/target tak dikenal -------------------------------


async def test_citra_potensi_tak_dikenal_mengembalikan_tidak_ditemukan(
    konteks: KonteksAlat,
) -> None:
    hasil = await jalankan_alat(
        "citra_potensi", {"prov": "99", "target": "tak-ada"}, konteks
    )

    assert hasil == {"galat": TIDAK_DITEMUKAN}


# --- 14. citra_potensi: join nmdesa + format_skor ----------------------------


async def test_citra_potensi_join_nmdesa_dan_format_skor(konteks: KonteksAlat) -> None:
    hasil = await jalankan_alat(
        "citra_potensi", {"prov": IDPROV, "target": TARGET_CITRA}, konteks
    )

    assert hasil["format_skor"] == [
        "skor_mentah",
        "skor100_dlm_kab",
        "peringkat_dlm_kab",
        "n_desa_kab",
    ]
    # D2 (skor100_dlm_kab 70.0) > D1 (50.0) > D3 (10.0) — urutan menurun.
    assert list(hasil["skor"]) == [D2, D1, D3]
    assert hasil["skor"][D2] == {"skor": [45.0, 70.0, 1, 3], "nmdesa": "DESA A2"}


# --- 15. KeyError/IndexError dari alat -> galat data, bukan exception --------


@pytest.mark.parametrize("kelas_galat", [KeyError, IndexError])
async def test_kunci_artefak_hilang_dikembalikan_sebagai_galat_data(
    kelas_galat: type[Exception],
    konteks: KonteksAlat,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Artefak yang ADA tapi kehilangan kunci internal (`baris["idkab"]`,
    `skor[iddesa][1]`, dst.) membuat `KeyError`/`IndexError` merambat keluar
    dari fungsi alat -- sebelum perbaikan, `jalankan_alat` hanya menangkap
    `GalatAPI`/`TypeError`/`ValueError`, jadi galat ini diteruskan mentah dan
    diperlakukan seperti galat vendor Gemini, bukan data cacat."""

    async def _alat_meledak(konteks: KonteksAlat, **_kwargs: Any) -> dict[str, Any]:
        raise kelas_galat("idkab")

    monkeypatch.setitem(tools._ALAT, "wilayah_ringkasan", _alat_meledak)

    hasil = await jalankan_alat("wilayah_ringkasan", {}, konteks)

    assert hasil == {"galat": DATA_BELUM_SIAP}


async def test_kunci_artefak_hilang_tercatat_di_log(
    konteks: KonteksAlat,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    async def _alat_meledak(konteks: KonteksAlat, **_kwargs: Any) -> dict[str, Any]:
        raise KeyError("idkab")

    monkeypatch.setitem(tools._ALAT, "wilayah_ringkasan", _alat_meledak)

    with caplog.at_level(logging.WARNING):
        hasil = await jalankan_alat("wilayah_ringkasan", {}, konteks)

    assert hasil == {"galat": DATA_BELUM_SIAP}
    assert any("wilayah_ringkasan" in rec.message for rec in caplog.records)


# --- 16. citra_potensi mengikuti format_skor, bukan indeks tetap -------------


def _berkas_produksi_citra(dir_data: Path) -> Path:
    return dir_data / "citra-potensi" / "produksi" / IDPROV / f"{TARGET_CITRA}.json"


async def test_citra_potensi_mengikuti_urutan_format_skor(
    konteks: KonteksAlat, dir_data_lengkap: Path
) -> None:
    """`format_skor` menentukan posisi kolom `skor100_dlm_kab`, BUKAN indeks
    tetap `1` -- produksi v5 memang seragam, tapi varian ML wisata di
    `data/arsip/` memakai urutan kolom lain. Berkas sel ditulis ulang dengan
    `format_skor` DIBALIK dan baris skor konsisten dengan urutan baru; hasil
    harus tetap terurut menurun menurut `skor100_dlm_kab`, bukan ikut kolom
    indeks 1 yang sekarang berarti kolom lain."""
    berkas = _berkas_produksi_citra(dir_data_lengkap)
    isi = json.loads(berkas.read_text(encoding="utf-8"))
    isi["format_skor"] = [
        "skor100_dlm_kab",
        "skor_mentah",
        "peringkat_dlm_kab",
        "n_desa_kab",
    ]
    isi["skor"] = {
        D1: [50.0, 38.19, 2, 3],
        D2: [70.0, 45.0, 1, 3],
        D3: [10.0, 20.0, 3, 3],
    }
    berkas.write_text(json.dumps(isi), encoding="utf-8")
    baca_sel_citra.cache_clear()

    hasil = await jalankan_alat(
        "citra_potensi", {"prov": IDPROV, "target": TARGET_CITRA}, konteks
    )

    assert "galat" not in hasil
    assert list(hasil["skor"]) == [D2, D1, D3]
    assert hasil["skor"][D2]["skor"] == [70.0, 45.0, 1, 3]


async def test_citra_potensi_format_skor_tanpa_kolom_mengembalikan_galat_data(
    konteks: KonteksAlat, dir_data_lengkap: Path
) -> None:
    berkas = _berkas_produksi_citra(dir_data_lengkap)
    isi = json.loads(berkas.read_text(encoding="utf-8"))
    isi["format_skor"] = ["skor_mentah", "peringkat_dlm_kab", "n_desa_kab"]
    berkas.write_text(json.dumps(isi), encoding="utf-8")
    baca_sel_citra.cache_clear()

    hasil = await jalankan_alat(
        "citra_potensi", {"prov": IDPROV, "target": TARGET_CITRA}, konteks
    )

    assert hasil == {"galat": DATA_BELUM_SIAP}


# --- 17. cek_cakupan_wilayah --------------------------------------------------
#
# Fixture `dir_data_lengkap` (lihat tests/conftest.py) memuat satu provinsi
# "Lampung" (idprov "18") dan dua kabupaten "KAB SATU"/"KAB DUA" (keduanya
# idprov "18") -- data nyata TIDAK menyimpan awalan "Kabupaten"/"Kota" pada
# `nmkab` (mis. "TANGGAMUS", bukan "Kabupaten Tanggamus"), jadi fixture ini
# sudah representatif.


async def test_cek_cakupan_wilayah_menemukan_provinsi(konteks: KonteksAlat) -> None:
    hasil = await jalankan_alat("cek_cakupan_wilayah", {"nama": "lampung"}, konteks)

    assert hasil["ditemukan"] is True
    assert hasil["provinsi"] == [{"idprov": IDPROV, "nama": "Lampung"}]
    assert hasil["kabupaten"] == []
    assert "provinsi_tercakup" not in hasil


async def test_cek_cakupan_wilayah_menemukan_kabupaten(konteks: KonteksAlat) -> None:
    hasil = await jalankan_alat("cek_cakupan_wilayah", {"nama": "satu"}, konteks)

    assert hasil["ditemukan"] is True
    assert hasil["provinsi"] == []
    assert hasil["kabupaten"] == [
        {
            "idkab": IDKAB_SATU,
            "nmkab": "KAB SATU",
            "idprov": IDPROV,
            "nmprov": "Lampung",
        }
    ]


@pytest.mark.parametrize(
    "variasi",
    ["KAB SATU", "kab satu", "Kab. Satu", "  kab   satu  ", "Kabupaten Satu"],
    ids=["kapital", "huruf-kecil", "kab-titik", "spasi-berlebih", "awalan-panjang"],
)
async def test_cek_cakupan_wilayah_toleran_variasi_penulisan(
    variasi: str, konteks: KonteksAlat
) -> None:
    hasil = await jalankan_alat("cek_cakupan_wilayah", {"nama": variasi}, konteks)

    assert hasil["ditemukan"] is True
    assert hasil["kabupaten"] == [
        {
            "idkab": IDKAB_SATU,
            "nmkab": "KAB SATU",
            "idprov": IDPROV,
            "nmprov": "Lampung",
        }
    ]


async def test_cek_cakupan_wilayah_menolak_wilayah_di_luar_cakupan(
    konteks: KonteksAlat,
) -> None:
    hasil = await jalankan_alat(
        "cek_cakupan_wilayah", {"nama": "Kabupaten Kediri"}, konteks
    )

    assert hasil["ditemukan"] is False
    assert hasil["provinsi"] == []
    assert hasil["kabupaten"] == []
    assert hasil["provinsi_tercakup"] == [{"idprov": IDPROV, "nama": "Lampung"}]


async def test_cek_cakupan_wilayah_nama_satu_huruf_mengembalikan_argumen_tidak_sah(
    konteks: KonteksAlat,
) -> None:
    hasil = await jalankan_alat("cek_cakupan_wilayah", {"nama": "a"}, konteks)

    assert hasil == {"galat": ARGUMEN_TIDAK_SAH}


async def test_cek_cakupan_wilayah_nama_seratus_satu_huruf_mengembalikan_argumen_tidak_sah(
    konteks: KonteksAlat,
) -> None:
    hasil = await jalankan_alat("cek_cakupan_wilayah", {"nama": "a" * 101}, konteks)

    assert hasil == {"galat": ARGUMEN_TIDAK_SAH}


async def test_cek_cakupan_wilayah_nama_bukan_string_mengembalikan_argumen_tidak_sah(
    konteks: KonteksAlat,
) -> None:
    hasil = await jalankan_alat("cek_cakupan_wilayah", {"nama": 123}, konteks)

    assert hasil == {"galat": ARGUMEN_TIDAK_SAH}


async def test_cek_cakupan_wilayah_argumen_kosong_mengembalikan_argumen_tidak_sah(
    konteks: KonteksAlat,
) -> None:
    hasil = await jalankan_alat("cek_cakupan_wilayah", {}, konteks)

    assert hasil == {"galat": ARGUMEN_TIDAK_SAH}
