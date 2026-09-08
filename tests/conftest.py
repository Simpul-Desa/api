"""Fixture bersama untuk seluruh uji integrasi di folder tests/."""

import gzip
import json
import time
from collections.abc import AsyncIterator, Callable, Iterator
from contextlib import AsyncExitStack
from pathlib import Path
from typing import Any, Protocol

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi import FastAPI
from httpx import ASGITransport

from src.auth.dependencies import wajib_tamu
from src.auth.schemas import Identitas
from src.citra_potensi.service import baca_sel_citra
from src.config import ambil_pengaturan
from src.desa_kembar.service import baca_kembar_kab
from src.jalur_ekonomi.service import baca_jalur
from src.kartu.service import baca_kartu_kab
from src.main import create_app


@pytest.fixture
def dir_data_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[Path]:
    """Siapkan `DIR_DATA` menunjuk ke direktori sementara berisi manifest.json.

    Membersihkan cache `ambil_pengaturan` sebelum dan sesudah test agar
    perubahan environment variable tidak bocor ke test lain. Fixture ini
    harus dicantumkan sebelum `klien` pada signature test yang memakai
    keduanya, supaya DIR_DATA sudah berubah sebelum `create_app()` dipanggil.
    """
    isi_manifest = {"hash": "uji123", "tanggal": "2026-09-07"}
    (tmp_path / "manifest.json").write_text(json.dumps(isi_manifest), encoding="utf-8")

    monkeypatch.setenv("DIR_DATA", str(tmp_path))
    ambil_pengaturan.cache_clear()

    yield tmp_path

    ambil_pengaturan.cache_clear()


BASIS_URL_UJI = "http://uji"


class PembuatKlien(Protocol):
    """Bentuk pabrik klien uji yang dikembalikan fixture `buat_klien`."""

    async def __call__(
        self,
        app: FastAPI,
        *,
        lifespan: bool = False,
        lempar_galat_app: bool = True,
    ) -> httpx.AsyncClient: ...


@pytest.fixture
async def buat_klien() -> AsyncIterator[PembuatKlien]:
    """Pabrik `httpx.AsyncClient` ber-`ASGITransport`; menutup sendiri saat test usai.

    Pengganti `TestClient`. Starlette 1.6 mendeprekasi pemakaian `httpx` dari
    `starlette.testclient` ("Using `httpx` with `starlette.testclient` is
    deprecated; install `httpx2` instead"), sementara `src/` sendiri memakai
    httpx 0.28 untuk PostgREST dan panen berita. Memakai `AsyncClient` +
    `ASGITransport` langsung menghindari jalur terdeprekasi itu tanpa
    memasukkan mayor httpx kedua ke venv bersama, dan menjalankan rute pada
    event loop sungguhan alih-alih lewat portal sinkron.

    Padanan perilaku `TestClient` yang digantikan:

    - `lifespan=False` (bawaan) = `TestClient(app)` polos — lifespan TIDAK
      dijalankan, jadi `app.state` tetap seperti yang dipasang test;
    - `lifespan=True` = `with TestClient(app) as k`;
    - `lempar_galat_app=False` = `raise_server_exceptions=False` — exception
      rute menjadi respons 500 alih-alih dilempar ulang ke test.

    Klien dan lifespan ditutup lewat satu `AsyncExitStack` milik fixture
    (LIFO: klien dulu, lifespan sesudahnya), sehingga badan test tidak perlu
    `async with` sendiri dan tidak perlu diindentasi ulang.
    """
    async with AsyncExitStack() as tumpukan:

        async def buat(
            app: FastAPI,
            *,
            lifespan: bool = False,
            lempar_galat_app: bool = True,
        ) -> httpx.AsyncClient:
            if lifespan:
                await tumpukan.enter_async_context(app.router.lifespan_context(app))
            return await tumpukan.enter_async_context(
                httpx.AsyncClient(
                    transport=ASGITransport(
                        app=app, raise_app_exceptions=lempar_galat_app
                    ),
                    base_url=BASIS_URL_UJI,
                )
            )

        yield buat


@pytest.fixture
def aplikasi() -> FastAPI:
    """Aplikasi nyata dengan dependensi peran `wajib_tamu` di-override tamu.

    Dipisah dari fixture `klien` supaya test yang perlu menyentuh `app.state`
    (mis. mengganti `klien_supabase` dengan transport tiruan) punya pegangan
    ke objek app: `httpx.AsyncClient` tidak membawa atribut `.app` seperti
    `TestClient` dulu.
    """
    app = create_app()
    app.dependency_overrides[wajib_tamu] = lambda: Identitas(id="uji", peran="tamu")
    return app


@pytest.fixture
async def klien(aplikasi: FastAPI, buat_klien: PembuatKlien) -> httpx.AsyncClient:
    """Klien aplikasi nyata dengan lifespan aktif.

    Dependensi peran `wajib_tamu` di-override menjadi tamu supaya seluruh uji
    endpoint baca fase 1-3 tetap berjalan tanpa token; uji matriks akses
    memakai kliennya sendiri TANPA override
    (`tests/auth/test_matriks_akses.py`).

    Harus dicantumkan SETELAH `dir_data_manifest`/`dir_data_lengkap` pada
    signature test: `create_app()` membaca `DIR_DATA` saat dipanggil.
    """
    return await buat_klien(aplikasi, lifespan=True)


# --- dir_data_lengkap: data-salinan/ sintetis mini lintas seluruh router ----
#
# 1 provinsi ("18"), 2 kabupaten ("1801"/"1802"), 6 desa. `iddesa` sama
# dipakai konsisten di kartu-ekonomi, peta-peran, desa-kembar, geo, dan
# jalur-ekonomi supaya uji router lintas-berkas (join lewat `iddesa`) bisa
# dilakukan. Lihat bagian "Bentuk artefak data-salinan/" di rencana
# `.claude/PRPs/plans/fase-3-endpoint-baca.plan.md` untuk skema tiap berkas.

IDPROV = "18"
IDKAB_SATU = "1801"
IDKAB_DUA = "1802"

# Desa kabupaten 1801:
D1 = "1801040001"  # Zona Mitra, keyakinan normal
D2 = "1801040002"  # Zona Poros, keyakinan rendah
D3 = "1801040003"  # Belum Terpetakan; SENGAJA tanpa entri di desa-kembar/1801.json

# Desa kabupaten 1802:
D4 = "1802010001"  # Zona Pemerintah
D5 = "1802010002"  # Zona Bantuan
D6 = "1802010003"  # Zona Mitra

TARGET_CITRA = "kom_prov_horti_01"
_BERKAS_CITRA_REL = f"produksi/{IDPROV}/{TARGET_CITRA}.json"
_FORMAT_SKOR_CITRA = [
    "skor_mentah",
    "skor100_dlm_kab",
    "peringkat_dlm_kab",
    "n_desa_kab",
]

# Tabel tunggal sumber data sintetis — seluruh artefak diturunkan dari sini
# supaya iddesa/idkab/zona/keyakinan konsisten lintas berkas (DRY).
_DESA_DATA: list[dict[str, Any]] = [
    {
        "iddesa": D1,
        "nmdesa": "DESA A1",
        "nmkec": "KEC ALFA",
        "idkab": IDKAB_SATU,
        "nmkab": "KAB SATU",
        "zona": "Zona Mitra",
        "keyakinan": "normal",
        "potensi_dominan": "Simpul Logistik",
        "sumber_dominan": "citra",
        "desil_sp": 9,
        "desil_sk": 10,
        "n_program": 0,
        "alasan_belum_terpetakan": "",
        "punya_geometri": True,
        "punya_st2023": True,
    },
    {
        "iddesa": D2,
        "nmdesa": "DESA A2",
        "nmkec": "KEC ALFA",
        "idkab": IDKAB_SATU,
        "nmkab": "KAB SATU",
        "zona": "Zona Poros",
        "keyakinan": "rendah",
        "potensi_dominan": "Peternakan",
        "sumber_dominan": "heuristik-belum-teruji",
        "desil_sp": 8,
        "desil_sk": 7,
        "n_program": 1,
        "alasan_belum_terpetakan": "",
        "punya_geometri": True,
        "punya_st2023": True,
    },
    {
        "iddesa": D3,
        "nmdesa": "DESA A3",
        "nmkec": "KEC BETA",
        "idkab": IDKAB_SATU,
        "nmkab": "KAB SATU",
        "zona": "Belum Terpetakan",
        "keyakinan": "",
        "potensi_dominan": "",
        "sumber_dominan": "",
        "desil_sp": 0,
        "desil_sk": 5,
        "n_program": 0,
        "alasan_belum_terpetakan": "tanpa geometri; tanpa ST2023",
        "punya_geometri": False,
        "punya_st2023": False,
    },
    {
        "iddesa": D4,
        "nmdesa": "DESA B1",
        "nmkec": "KEC GAMMA",
        "idkab": IDKAB_DUA,
        "nmkab": "KAB DUA",
        "zona": "Zona Pemerintah",
        "keyakinan": "normal",
        "potensi_dominan": "Pelayanan Dasar",
        "sumber_dominan": "heuristik-belum-teruji",
        "desil_sp": 3,
        "desil_sk": 8,
        "n_program": 2,
        "alasan_belum_terpetakan": "",
        "punya_geometri": True,
        "punya_st2023": True,
    },
    {
        "iddesa": D5,
        "nmdesa": "DESA B2",
        "nmkec": "KEC GAMMA",
        "idkab": IDKAB_DUA,
        "nmkab": "KAB DUA",
        "zona": "Zona Bantuan",
        "keyakinan": "normal",
        "potensi_dominan": "",
        "sumber_dominan": "",
        "desil_sp": 2,
        "desil_sk": 3,
        "n_program": 0,
        "alasan_belum_terpetakan": "",
        "punya_geometri": True,
        "punya_st2023": True,
    },
    {
        "iddesa": D6,
        "nmdesa": "DESA B3",
        "nmkec": "KEC DELTA",
        "idkab": IDKAB_DUA,
        "nmkab": "KAB DUA",
        "zona": "Zona Mitra",
        "keyakinan": "normal",
        "potensi_dominan": "Simpul Logistik",
        "sumber_dominan": "citra",
        "desil_sp": 9,
        "desil_sk": 9,
        "n_program": 1,
        "alasan_belum_terpetakan": "",
        "punya_geometri": True,
        "punya_st2023": True,
    },
]


def _tulis_json(path: Path, isi: Any) -> None:
    """Tulis `isi` sebagai JSON ke `path`, membuat direktori induk bila perlu."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(isi), encoding="utf-8")


def _desa_kab(idkab: str) -> list[dict[str, Any]]:
    """Baris `_DESA_DATA` milik satu `idkab`."""
    return [d for d in _DESA_DATA if d["idkab"] == idkab]


def _identitas_ringkas(iddesa: str) -> dict[str, Any]:
    """Identitas minimal (`iddesa`, `nmdesa`, `nmkec`) untuk baris jalur ekonomi."""
    d = next(x for x in _DESA_DATA if x["iddesa"] == iddesa)
    return {"iddesa": d["iddesa"], "nmdesa": d["nmdesa"], "nmkec": d["nmkec"]}


def _baris_indeks_kartu() -> list[dict[str, Any]]:
    """`kartu-ekonomi/indeks.json` — tanpa `idprov`, tanpa `sumber_dominan`."""
    return [
        {
            "iddesa": d["iddesa"],
            "nmdesa": d["nmdesa"],
            "nmkec": d["nmkec"],
            "idkab": d["idkab"],
            "nmkab": d["nmkab"],
            "zona": d["zona"],
            "keyakinan": d["keyakinan"],
            "potensi_dominan": d["potensi_dominan"],
            "desil_sp": d["desil_sp"],
            "desil_sk": d["desil_sk"],
            "n_program": d["n_program"],
        }
        for d in _DESA_DATA
    ]


def _kartu_per_kab(idkab: str) -> dict[str, Any]:
    """`kartu-ekonomi/kartu/<idkab>.json` — kartu minimal identitas+peta_peran+mutu_data."""
    desa_kab = _desa_kab(idkab)
    return {
        "idkab": idkab,
        "nmkab": desa_kab[0]["nmkab"],
        "n_wilayah": len(desa_kab),
        "kartu": [
            {
                "identitas": {
                    "iddesa": d["iddesa"],
                    "nama": d["nmdesa"],
                    "kecamatan": d["nmkec"],
                    "kabupaten": d["nmkab"],
                    "provinsi": IDPROV,
                    "tipe": "desa",
                },
                "peta_peran": {
                    "zona": d["zona"],
                    "keyakinan": d["keyakinan"],
                    "alasan_belum_terpetakan": d["alasan_belum_terpetakan"],
                    "desil_sp": d["desil_sp"],
                    "desil_sk": d["desil_sk"],
                },
                "mutu_data": {
                    "punya_geometri": d["punya_geometri"],
                    "punya_st2023": d["punya_st2023"],
                    "punya_idm": True,
                    "kelengkapan_bukti_sk": 1.0 if d["punya_geometri"] else 0.25,
                },
            }
            for d in desa_kab
        ],
    }


def _baris_peta_peran() -> list[dict[str, Any]]:
    """`peta-peran/peta_peran.json` — kolom proyeksi ringkas + `alasan_belum_terpetakan`."""
    return [
        {
            "iddesa": d["iddesa"],
            "nmdesa": d["nmdesa"],
            "nmkec": d["nmkec"],
            "idkab": d["idkab"],
            "nmkab": d["nmkab"],
            "idprov": IDPROV,
            "zona": d["zona"],
            "keyakinan": d["keyakinan"],
            "desil_sp": d["desil_sp"],
            "desil_sk": d["desil_sk"],
            "potensi_dominan": d["potensi_dominan"],
            "sumber_dominan": d["sumber_dominan"],
            "alasan_belum_terpetakan": d["alasan_belum_terpetakan"],
        }
        for d in _DESA_DATA
    ]


def _ringkasan_kab() -> dict[str, Any]:
    """`peta-peran/ringkasan_kab.json` — hitungan zona per kabupaten sintetis."""
    hasil: dict[str, Any] = {}
    for idkab, ambang_sp, ambang_sk, n_jadesta in (
        (IDKAB_SATU, 90.0, 30.0, 0),
        (IDKAB_DUA, 85.0, 28.0, 1),
    ):
        desa_kab = _desa_kab(idkab)
        zona_count = {
            nama: sum(1 for d in desa_kab if d["zona"] == nama)
            for nama in (
                "Zona Pemerintah",
                "Zona Mitra",
                "Zona Poros",
                "Zona Bantuan",
                "Belum Terpetakan",
            )
        }
        hasil[idkab] = {
            "nmkab": desa_kab[0]["nmkab"],
            "n_wilayah": len(desa_kab),
            "ambang_sp": ambang_sp,
            "ambang_sk": ambang_sk,
            "zona": zona_count,
            "n_keyakinan_rendah": sum(
                1 for d in desa_kab if d["keyakinan"] == "rendah"
            ),
            "n_jadesta": n_jadesta,
        }
    return hasil


def _citra_indeks() -> dict[str, Any]:
    """`citra-potensi/indeks.json` — satu sel provinsi 18, target `TARGET_CITRA`."""
    return {
        "jumlah_sel": 1,
        "format_skor": _FORMAT_SKOR_CITRA,
        "sel": [
            {
                "prov": IDPROV,
                "target": TARGET_CITRA,
                "nama": "Pisang Lainnya",
                "subsektor": "horti",
                "mesin": "greedy",
                "ap_uji_tertahan": 0.5,
                "ci_rerata": [0.4, 0.6],
                "berkas": _BERKAS_CITRA_REL,
            }
        ],
    }


def _citra_produksi() -> dict[str, Any]:
    """`citra-potensi/produksi/18/kom_prov_horti_01.json` — skor 3 desa kab 1801."""
    desa_satu = _desa_kab(IDKAB_SATU)
    return {
        "meta": {
            "prov": IDPROV,
            "target": TARGET_CITRA,
            "nama": "Pisang Lainnya",
            "subsektor": "horti",
            "mesin": "greedy",
        },
        "validasi": {"ap_uji_tertahan": 0.5},
        "model": {"jenis": "greedy", "susunan": []},
        "format_skor": _FORMAT_SKOR_CITRA,
        "skor": {
            desa_satu[0]["iddesa"]: [38.19, 50.0, 2, 3],
            desa_satu[1]["iddesa"]: [45.0, 70.0, 1, 3],
            desa_satu[2]["iddesa"]: [20.0, 10.0, 3, 3],
        },
    }


def _hasil_komoditas() -> dict[str, Any]:
    """`jalur-ekonomi/hasil_komoditas.json` — 1 grup sejalur di kab 1801."""
    return {
        "parameter": {"MIN_ANGGOTA": 2, "MAKS_ANGGOTA": 25},
        "kabupaten": {
            IDKAB_SATU: {
                "nmkab": "KAB SATU",
                "komoditas": {
                    TARGET_CITRA: {
                        "nama": "Pisang Lainnya",
                        "subsektor": "horti",
                        "n_desa_tema": 2,
                        "volume_tema": 100,
                        "metrik": {"n_sejalur": 1, "pct_volume_tercakup": 60.0},
                        "sejalur": [
                            {
                                "volume": 60,
                                "n_anggota": 2,
                                "poros": _identitas_ringkas(D1),
                                "kecamatan": ["KEC ALFA"],
                                "anggota": [
                                    _identitas_ringkas(D1),
                                    _identitas_ringkas(D2),
                                ],
                            }
                        ],
                    }
                },
            },
            IDKAB_DUA: {"nmkab": "KAB DUA", "komoditas": {}},
        },
        "ringkasan": [
            {"idkab": IDKAB_SATU, "nmkab": "KAB SATU", "status": "OPTIMAL"},
            {"idkab": IDKAB_DUA, "nmkab": "KAB DUA", "status": "OPTIMAL"},
        ],
    }


def _hasil_gudang() -> dict[str, Any]:
    """`jalur-ekonomi/hasil_gudang.json` — 1 gudang per kabupaten."""
    return {
        "parameter": {"OPSI": "B", "GUDANG": {"t_maks": 40, "v_min": 2500}},
        "kabupaten": {
            IDKAB_SATU: {
                "nmkab": "KAB SATU",
                "gudang": [
                    {
                        "volume": 80,
                        "n_desa_layanan": 2,
                        "lokasi": _identitas_ringkas(D2),
                        "kecamatan": ["KEC ALFA"],
                        "desa_layanan": [
                            _identitas_ringkas(D1),
                            _identitas_ringkas(D3),
                        ],
                    }
                ],
            },
            IDKAB_DUA: {
                "nmkab": "KAB DUA",
                "gudang": [
                    {
                        "volume": 70,
                        "n_desa_layanan": 2,
                        "lokasi": _identitas_ringkas(D4),
                        "kecamatan": ["KEC GAMMA"],
                        "desa_layanan": [
                            _identitas_ringkas(D5),
                            _identitas_ringkas(D6),
                        ],
                    }
                ],
            },
        },
        "ringkasan": [
            {"idkab": IDKAB_SATU, "nmkab": "KAB SATU", "status": "OPTIMAL"},
            {"idkab": IDKAB_DUA, "nmkab": "KAB DUA", "status": "OPTIMAL"},
        ],
    }


def _hasil_cold_storage() -> dict[str, Any]:
    """`jalur-ekonomi/hasil_cold_storage.json` — 1801 layak, 1802 TAK_LAYAK kosong."""
    return {
        "parameter": {"KANDIDAT": "K2", "SPEK": {"t_maks": 45, "v_min": 500}},
        "kabupaten": {
            IDKAB_SATU: {
                "nmkab": "KAB SATU",
                "cs_baru": [
                    {
                        "volume": 60,
                        "n_desa_layanan": 1,
                        "lokasi": _identitas_ringkas(D1),
                        "kecamatan": ["KEC ALFA"],
                        "desa_layanan": [_identitas_ringkas(D2)],
                    }
                ],
                "cs_eksisting": [
                    {
                        "id_cs": 1,
                        "iddesa": D3,
                        "nmdesa": "DESA A3",
                        "kapasitas_ton": 500.0,
                        "kapasitas_ruta": 8000,
                        "dimodelkan": True,
                        "ruta_terserap": 0,
                        "n_desa_layanan": 0,
                        "desa_layanan": [],
                    }
                ],
            },
            IDKAB_DUA: {"nmkab": "KAB DUA", "cs_baru": [], "cs_eksisting": []},
        },
        "ringkasan": [
            {"idkab": IDKAB_SATU, "nmkab": "KAB SATU", "status": "OPTIMAL"},
            {"idkab": IDKAB_DUA, "nmkab": "KAB DUA", "status": "TAK_LAYAK"},
        ],
    }


def _hasil_wisata() -> dict[str, Any]:
    """`jalur-ekonomi/hasil_wisata.json` — 1 kawasan per kabupaten, tanpa koordinat."""
    return {
        "parameter": {"KANDIDAT": "W6", "SPEK": {"t_maks": 45, "v_min": 6}},
        "kabupaten": {
            IDKAB_SATU: {
                "nmkab": "KAB SATU",
                "kawasan": [
                    {
                        "bobot": 20,
                        "n_desa": 2,
                        "basis": {
                            **_identitas_ringkas(D1),
                            "kategori": "BERKEMBANG",
                        },
                        "kecamatan": ["KEC ALFA"],
                        "desa": [
                            {
                                **_identitas_ringkas(D1),
                                "kategori": "BERKEMBANG",
                                "bobot": 12,
                            },
                            {
                                **_identitas_ringkas(D2),
                                "kategori": "RINTISAN",
                                "bobot": 8,
                            },
                        ],
                    }
                ],
            },
            IDKAB_DUA: {
                "nmkab": "KAB DUA",
                "kawasan": [
                    {
                        "bobot": 15,
                        "n_desa": 2,
                        "basis": {
                            **_identitas_ringkas(D4),
                            "kategori": "RINTISAN",
                        },
                        "kecamatan": ["KEC GAMMA"],
                        "desa": [
                            {
                                **_identitas_ringkas(D4),
                                "kategori": "RINTISAN",
                                "bobot": 9,
                            },
                            {
                                **_identitas_ringkas(D5),
                                "kategori": "RINTISAN",
                                "bobot": 6,
                            },
                        ],
                    }
                ],
            },
        },
        "ringkasan": [
            {"idkab": IDKAB_SATU, "nmkab": "KAB SATU", "status": "OPTIMAL"},
            {"idkab": IDKAB_DUA, "nmkab": "KAB DUA", "status": "OPTIMAL"},
        ],
    }


def _desa_kembar_1801() -> dict[str, Any]:
    """`desa-kembar/1801.json` — `D3` SENGAJA tanpa entri (desa tanpa vektor)."""
    return {
        "idkab": IDKAB_SATU,
        "k": 2,
        "p95_jarak": 10.0,
        "desa": {
            D1: [{"iddesa": D2, "persen": 50.0}],
            D2: [{"iddesa": D1, "persen": 50.0}],
        },
    }


def _desa_kembar_1802() -> dict[str, Any]:
    """`desa-kembar/1802.json` — seluruh desa kab 1802 punya entri."""
    return {
        "idkab": IDKAB_DUA,
        "k": 2,
        "p95_jarak": 12.0,
        "desa": {
            D4: [{"iddesa": D5, "persen": 40.0}],
            D5: [{"iddesa": D4, "persen": 40.0}],
            D6: [{"iddesa": D4, "persen": 30.0}],
        },
    }


def _geojson_1801() -> dict[str, Any]:
    """FeatureCollection kecil kab 1801 — properti fitur hanya `iddesa`+`nmdesa`."""
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {"iddesa": d["iddesa"], "nmdesa": d["nmdesa"]},
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [
                        [
                            [104.0, -5.0],
                            [104.1, -5.0],
                            [104.1, -5.1],
                            [104.0, -5.1],
                            [104.0, -5.0],
                        ]
                    ],
                },
            }
            for d in _desa_kab(IDKAB_SATU)
        ],
    }


def _bangun_data_salinan_lengkap(dir_data: Path) -> None:
    """Bangun `data-salinan/` sintetis mini lengkap untuk uji router baca.

    1 provinsi ("18"), 2 kabupaten ("1801"/"1802"), 6 desa; seluruh jenis
    artefak yang dikonsumsi router fase 3 — lihat bagian "Bentuk artefak
    data-salinan/" di rencana `fase-3-endpoint-baca.plan.md`.
    """
    _tulis_json(
        dir_data / "manifest.json",
        {"hash": "uji123", "tanggal": "2026-09-07", "artefak": []},
    )
    _tulis_json(
        dir_data / "wilayah.json",
        {
            "provinsi": [{"idprov": IDPROV, "nama": "Lampung"}],
            "kabupaten": [
                {"idkab": IDKAB_SATU, "nmkab": "KAB SATU", "idprov": IDPROV},
                {"idkab": IDKAB_DUA, "nmkab": "KAB DUA", "idprov": IDPROV},
            ],
        },
    )

    _tulis_json(dir_data / "kartu-ekonomi" / "indeks.json", _baris_indeks_kartu())
    _tulis_json(
        dir_data / "kartu-ekonomi" / "kartu" / f"{IDKAB_SATU}.json",
        _kartu_per_kab(IDKAB_SATU),
    )
    _tulis_json(
        dir_data / "kartu-ekonomi" / "kartu" / f"{IDKAB_DUA}.json",
        _kartu_per_kab(IDKAB_DUA),
    )

    _tulis_json(dir_data / "peta-peran" / "peta_peran.json", _baris_peta_peran())
    _tulis_json(dir_data / "peta-peran" / "ringkasan_kab.json", _ringkasan_kab())

    _tulis_json(dir_data / "citra-potensi" / "indeks.json", _citra_indeks())
    _tulis_json(dir_data / "citra-potensi" / _BERKAS_CITRA_REL, _citra_produksi())

    _tulis_json(dir_data / "jalur-ekonomi" / "hasil_komoditas.json", _hasil_komoditas())
    _tulis_json(dir_data / "jalur-ekonomi" / "hasil_gudang.json", _hasil_gudang())
    _tulis_json(
        dir_data / "jalur-ekonomi" / "hasil_cold_storage.json",
        _hasil_cold_storage(),
    )
    _tulis_json(dir_data / "jalur-ekonomi" / "hasil_wisata.json", _hasil_wisata())

    _tulis_json(dir_data / "desa-kembar" / f"{IDKAB_SATU}.json", _desa_kembar_1801())
    _tulis_json(dir_data / "desa-kembar" / f"{IDKAB_DUA}.json", _desa_kembar_1802())

    berkas_geo = dir_data / "geo" / f"{IDKAB_SATU}.geojson.gz"
    berkas_geo.parent.mkdir(parents=True, exist_ok=True)
    berkas_geo.write_bytes(gzip.compress(json.dumps(_geojson_1801()).encode("utf-8")))


def _bersihkan_cache_lru_pembaca() -> None:
    """Bersihkan cache LRU keempat pembaca per domain.

    Sejak restrukturisasi, keempatnya tinggal di modulnya sendiri:
    `kartu`, `desa_kembar`, `jalur_ekonomi`, dan `citra_potensi`. Kalau satu
    terlewat di sini, state cache bocor antar-uji dan gagalnya acak
    tergantung urutan eksekusi.
    """
    baca_kartu_kab.cache_clear()
    baca_kembar_kab.cache_clear()
    baca_jalur.cache_clear()
    baca_sel_citra.cache_clear()


@pytest.fixture
def dir_data_lengkap(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Siapkan `DIR_DATA` ke `data-salinan/` sintetis mini lengkap (Tugas 4).

    1 provinsi ("18"), 2 kabupaten ("1801"/"1802"), 6 desa — seluruh jenis
    artefak dipakai router baca fase 3 (lihat `_bangun_data_salinan_lengkap`
    di atas untuk daftar berkas dan bentuknya). Pola sama seperti
    `dir_data_manifest`: monkeypatch `DIR_DATA`, bersihkan cache
    `ambil_pengaturan` DAN keempat pembaca LRU per domain sebelum
    dan sesudah test, supaya tidak bocor antar test maupun antar fixture
    dengan `tmp_path` berbeda. Fixture ini harus dicantumkan sebelum `klien`
    pada signature test yang memakai keduanya, supaya `DIR_DATA` sudah
    berubah sebelum `create_app()` memuat `Simpanan` di lifespan.
    """
    _bangun_data_salinan_lengkap(tmp_path)

    monkeypatch.setenv("DIR_DATA", str(tmp_path))
    ambil_pengaturan.cache_clear()
    _bersihkan_cache_lru_pembaca()

    yield tmp_path

    ambil_pengaturan.cache_clear()
    _bersihkan_cache_lru_pembaca()


# --- Fixture auth fase 4: keypair ES256 uji + pembuat token ---


@pytest.fixture(scope="session")
def kunci_es256() -> tuple[str, Any]:
    """Pasangan kunci ES256 (P-256) khusus uji: PEM privat + objek publik.

    Kunci privat dipakai `buat_token` untuk menandatangani token uji; kunci
    publik dipakai test untuk menggantikan (monkeypatch) `_kunci_penandatangan`
    sehingga `verifikasi_token` bisa diuji tanpa memanggil JWKS Supabase asli.
    """
    kunci_privat = ec.generate_private_key(ec.SECP256R1())
    pem_privat = kunci_privat.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")
    return pem_privat, kunci_privat.public_key()


@pytest.fixture
def buat_token(kunci_es256: tuple[str, Any]) -> Callable[..., str]:
    """Pabrik token JWT ES256 uji, ditandatangani dengan `kunci_es256`."""
    pem_privat, _ = kunci_es256

    def _buat(
        sub: str,
        *,
        aud: str = "authenticated",
        iss: str = "https://uji.supabase.co/auth/v1",
        exp_detik: int = 3600,
        klaim_ekstra: dict[str, Any] | None = None,
    ) -> str:
        sekarang = int(time.time())
        klaim = {
            "sub": sub,
            "aud": aud,
            "iss": iss,
            "exp": sekarang + exp_detik,
            "iat": sekarang,
        }
        klaim.update(klaim_ekstra or {})
        return jwt.encode(
            klaim, pem_privat, algorithm="ES256", headers={"kid": "kunci-uji"}
        )

    return _buat
