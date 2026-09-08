"""Uji unit untuk `src/jalur_ekonomi/service.py`: perataan grup jalur ekonomi + pencarian.

Struktur `hasil` di bawah adalah potongan mini yang meniru bentuk asli
`jalur-ekonomi/hasil_*.json` — lihat bagian "Bentuk artefak data-salinan/"
di rencana `.claude/PRPs/plans/fase-3-endpoint-baca.plan.md`.
"""

import json
import logging
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from src.config import ambil_pengaturan
from src.jalur_ekonomi.service import (
    anggota_iddesa,
    baca_jalur,
    cari_grup,
    ratakan,
)


def _identitas(iddesa: str, nmdesa: str, nmkec: str) -> dict[str, str]:
    return {"iddesa": iddesa, "nmdesa": nmdesa, "nmkec": nmkec}


@pytest.fixture
def hasil_komoditas() -> dict[str, Any]:
    """Meniru `hasil_komoditas.json` — 1 target, 1 grup sejalur, kab 1801."""
    return {
        "parameter": {"MIN_ANGGOTA": 2},
        "kabupaten": {
            "1801": {
                "nmkab": "KAB SATU",
                "komoditas": {
                    "kom_prov_tp_02": {
                        "nama": "Padi Sawah",
                        "subsektor": "tp",
                        "n_desa_tema": 2,
                        "volume_tema": 100,
                        "metrik": {"n_sejalur": 1},
                        "sejalur": [
                            {
                                "volume": 60,
                                "n_anggota": 2,
                                "poros": _identitas(
                                    "1801040001", "DESA A1", "KEC ALFA"
                                ),
                                "kecamatan": ["KEC ALFA"],
                                "anggota": [
                                    _identitas("1801040001", "DESA A1", "KEC ALFA"),
                                    _identitas("1801040002", "DESA A2", "KEC ALFA"),
                                ],
                            }
                        ],
                    }
                },
            }
        },
    }


@pytest.fixture
def hasil_gudang() -> dict[str, Any]:
    """Meniru `hasil_gudang.json` — 1 gudang per kabupaten (1801, 1802)."""
    return {
        "parameter": {"OPSI": "B"},
        "kabupaten": {
            "1801": {
                "nmkab": "KAB SATU",
                "gudang": [
                    {
                        "volume": 80,
                        "n_desa_layanan": 2,
                        "lokasi": _identitas("1801040002", "DESA A2", "KEC ALFA"),
                        "kecamatan": ["KEC ALFA"],
                        "desa_layanan": [
                            _identitas("1801040001", "DESA A1", "KEC ALFA"),
                            _identitas("1801040003", "DESA A3", "KEC BETA"),
                        ],
                    }
                ],
            },
            "1802": {
                "nmkab": "KAB DUA",
                "gudang": [
                    {
                        "volume": 70,
                        "n_desa_layanan": 1,
                        "lokasi": _identitas("1802010001", "DESA B1", "KEC GAMMA"),
                        "kecamatan": ["KEC GAMMA"],
                        "desa_layanan": [
                            _identitas("1802010002", "DESA B2", "KEC GAMMA"),
                        ],
                    }
                ],
            },
        },
    }


@pytest.fixture
def hasil_cold_storage() -> dict[str, Any]:
    """Meniru `hasil_cold_storage.json` — 1801 layak (baru+eksisting), 1802 TAK_LAYAK kosong."""
    return {
        "parameter": {"KANDIDAT": "K2"},
        "kabupaten": {
            "1801": {
                "nmkab": "KAB SATU",
                "cs_baru": [
                    {
                        "volume": 60,
                        "n_desa_layanan": 1,
                        "lokasi": _identitas("1801040001", "DESA A1", "KEC ALFA"),
                        "kecamatan": ["KEC ALFA"],
                        "desa_layanan": [
                            _identitas("1801040002", "DESA A2", "KEC ALFA"),
                        ],
                    }
                ],
                "cs_eksisting": [
                    {
                        "id_cs": 1,
                        "iddesa": "1801040003",
                        "nmdesa": "DESA A3",
                        "kapasitas_ton": 500.0,
                        "n_desa_layanan": 1,
                        "desa_layanan": [
                            _identitas("1801040001", "DESA A1", "KEC ALFA"),
                        ],
                    }
                ],
            },
            "1802": {"nmkab": "KAB DUA", "cs_baru": [], "cs_eksisting": []},
        },
    }


@pytest.fixture
def hasil_wisata() -> dict[str, Any]:
    """Meniru `hasil_wisata.json` — 1 kawasan kab 1801, tanpa kolom koordinat."""
    return {
        "parameter": {"KANDIDAT": "W6"},
        "kabupaten": {
            "1801": {
                "nmkab": "KAB SATU",
                "kawasan": [
                    {
                        "bobot": 20,
                        "n_desa": 2,
                        "basis": {
                            **_identitas("1801040001", "DESA A1", "KEC ALFA"),
                            "kategori": "BERKEMBANG",
                        },
                        "kecamatan": ["KEC ALFA"],
                        "desa": [
                            {
                                **_identitas("1801040001", "DESA A1", "KEC ALFA"),
                                "kategori": "BERKEMBANG",
                                "bobot": 12,
                            },
                            {
                                **_identitas("1801040002", "DESA A2", "KEC ALFA"),
                                "kategori": "RINTISAN",
                                "bobot": 8,
                            },
                        ],
                    }
                ],
            }
        },
    }


@pytest.mark.unit
def test_ratakan_komoditas_id_deterministik_dan_baris_ringkas(
    hasil_komoditas: dict[str, Any],
) -> None:
    baris = ratakan(hasil_komoditas, "komoditas")

    assert baris == [
        {
            "id_jalur": "1801-kom_prov_tp_02-1",
            "idkab": "1801",
            "nmkab": "KAB SATU",
            "poros": {
                "iddesa": "1801040001",
                "nmdesa": "DESA A1",
                "nmkec": "KEC ALFA",
            },
            "n_anggota": 2,
            "bobot": 60,
            "label": "Padi Sawah",
        }
    ]


@pytest.mark.unit
def test_ratakan_gudang_id_dan_urut_idkab(hasil_gudang: dict[str, Any]) -> None:
    baris = ratakan(hasil_gudang, "gudang-kopdes")

    assert [b["id_jalur"] for b in baris] == ["1801-gudang-1", "1802-gudang-1"]
    assert baris[0]["label"] == "gudang"
    assert baris[0]["poros"]["iddesa"] == "1801040002"
    assert baris[0]["n_anggota"] == 2
    assert baris[0]["bobot"] == 80


@pytest.mark.unit
def test_ratakan_cold_storage_baru_dan_eksisting(
    hasil_cold_storage: dict[str, Any],
) -> None:
    baris = ratakan(hasil_cold_storage, "cold-storage")

    assert [b["id_jalur"] for b in baris] == [
        "1801-cs-baru-1",
        "1801-cs-eksisting-1",
    ]
    baru, eksisting = baris
    assert baru["label"] == "cs-baru"
    assert baru["bobot"] == 60
    assert eksisting["label"] == "cs-eksisting"
    assert eksisting["poros"] == {"iddesa": "1801040003", "nmdesa": "DESA A3"}
    assert eksisting["n_anggota"] == 1
    assert eksisting["bobot"] == 500.0


@pytest.mark.unit
def test_ratakan_cold_storage_kab_tak_layak_tanpa_baris(
    hasil_cold_storage: dict[str, Any],
) -> None:
    baris = ratakan(hasil_cold_storage, "cold-storage")

    assert all(b["idkab"] != "1802" for b in baris)


@pytest.mark.unit
def test_ratakan_wisata_id_dan_label_kategori_basis(
    hasil_wisata: dict[str, Any],
) -> None:
    baris = ratakan(hasil_wisata, "wisata")

    assert baris == [
        {
            "id_jalur": "1801-kawasan-1",
            "idkab": "1801",
            "nmkab": "KAB SATU",
            "poros": {
                "iddesa": "1801040001",
                "nmdesa": "DESA A1",
                "nmkec": "KEC ALFA",
            },
            "n_anggota": 2,
            "bobot": 20,
            "label": "BERKEMBANG",
        }
    ]


@pytest.mark.unit
def test_cari_grup_ditemukan_utuh_dengan_id_jalur(
    hasil_komoditas: dict[str, Any],
) -> None:
    grup = cari_grup(hasil_komoditas, "komoditas", "1801-kom_prov_tp_02-1")

    assert grup is not None
    assert grup["id_jalur"] == "1801-kom_prov_tp_02-1"
    assert grup["volume"] == 60
    assert grup["anggota"][1]["iddesa"] == "1801040002"


@pytest.mark.unit
def test_cari_grup_tidak_ditemukan_kembalikan_none(
    hasil_komoditas: dict[str, Any],
) -> None:
    assert cari_grup(hasil_komoditas, "komoditas", "1801-tak-ada-1") is None


@pytest.mark.unit
def test_cari_grup_tidak_memutasi_sumber(hasil_komoditas: dict[str, Any]) -> None:
    grup_asal = hasil_komoditas["kabupaten"]["1801"]["komoditas"]["kom_prov_tp_02"][
        "sejalur"
    ][0]

    cari_grup(hasil_komoditas, "komoditas", "1801-kom_prov_tp_02-1")

    assert "id_jalur" not in grup_asal


@pytest.mark.unit
def test_anggota_iddesa_komoditas_lewat_poros_dan_anggota(
    hasil_komoditas: dict[str, Any],
) -> None:
    grup = cari_grup(hasil_komoditas, "komoditas", "1801-kom_prov_tp_02-1")
    assert grup is not None

    anggota = anggota_iddesa(grup, "komoditas")

    assert anggota == {"1801040001", "1801040002"}


@pytest.mark.unit
def test_anggota_iddesa_cold_storage_eksisting_diri_sendiri_dan_layanan(
    hasil_cold_storage: dict[str, Any],
) -> None:
    grup = cari_grup(hasil_cold_storage, "cold-storage", "1801-cs-eksisting-1")
    assert grup is not None

    anggota = anggota_iddesa(grup, "cold-storage")

    assert anggota == {"1801040003", "1801040001"}


@pytest.mark.unit
def test_anggota_iddesa_gudang_lewat_lokasi_dan_desa_layanan(
    hasil_gudang: dict[str, Any],
) -> None:
    grup = cari_grup(hasil_gudang, "gudang-kopdes", "1801-gudang-1")
    assert grup is not None

    anggota = anggota_iddesa(grup, "gudang-kopdes")

    assert anggota == {"1801040002", "1801040001", "1801040003"}


@pytest.mark.unit
def test_anggota_iddesa_wisata_lewat_basis_dan_desa(
    hasil_wisata: dict[str, Any],
) -> None:
    grup = cari_grup(hasil_wisata, "wisata", "1801-kawasan-1")
    assert grup is not None

    anggota = anggota_iddesa(grup, "wisata")

    assert anggota == {"1801040001", "1801040002"}


# --- Pembaca berkas hasil per varian ----------------------------------------

BERKAS_PER_VARIAN = {"komoditas": "hasil_komoditas.json"}


@pytest.fixture(autouse=True)
def _bersihkan_cache_lru_baca_jalur() -> Iterator[None]:
    """Bersihkan cache LRU `baca_jalur` sebelum & sesudah tiap uji."""
    baca_jalur.cache_clear()
    yield
    baca_jalur.cache_clear()


def _hasil_komoditas_sintetis(dir_data: Path) -> None:
    """Tulis `jalur-ekonomi/hasil_komoditas.json` minimal — satu kabupaten."""
    path = dir_data / "jalur-ekonomi" / BERKAS_PER_VARIAN["komoditas"]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"kabupaten": {"1801": {"nmkab": "KAB SATU", "komoditas": {}}}}),
        encoding="utf-8",
    )


@pytest.mark.unit
def test_baca_jalur_kembalikan_isi_per_varian(tmp_path: Path) -> None:
    _hasil_komoditas_sintetis(tmp_path)

    hasil = baca_jalur(str(tmp_path), "komoditas")

    assert hasil is not None
    assert hasil["kabupaten"]["1801"]["nmkab"] == "KAB SATU"


@pytest.mark.unit
def test_baca_jalur_varian_tak_dikenal_kembalikan_none(tmp_path: Path) -> None:
    """Varian di luar empat nama PRD §5 tidak punya berkas — None, bukan galat."""
    _hasil_komoditas_sintetis(tmp_path)

    hasil = baca_jalur(str(tmp_path), "varian-tak-ada")

    assert hasil is None


@pytest.mark.unit
def test_grup_cacat_dilewati_grup_lain_tetap_tersaji(
    hasil_komoditas: dict[str, Any], caplog: pytest.LogCaptureFixture
) -> None:
    """Satu grup tanpa `n_anggota` tidak boleh menjatuhkan seluruh daftar.

    `hasil_*.json` bisa memuat ratusan grup; satu grup cacat yang membuat
    rute balas 500 berarti seluruh varian hilang dari `app/`. Grup itu
    dilewati dan dicatat — selisih cacah berkas vs respons adalah satu-satunya
    petunjuk bahwa build datanya cacat.
    """
    sejalur = hasil_komoditas["kabupaten"]["1801"]["komoditas"]["kom_prov_tp_02"][
        "sejalur"
    ]
    cacat = {k: v for k, v in sejalur[0].items() if k != "n_anggota"}
    sejalur.append(cacat)

    with caplog.at_level(logging.WARNING):
        baris = ratakan(hasil_komoditas, "komoditas")

    assert [b["id_jalur"] for b in baris] == ["1801-kom_prov_tp_02-1"]
    assert "1801-kom_prov_tp_02-2" in caplog.text


@pytest.mark.unit
def test_isi_kabupaten_bukan_objek_dilewati(
    hasil_komoditas: dict[str, Any], caplog: pytest.LogCaptureFixture
) -> None:
    hasil_komoditas["kabupaten"]["1899"] = "bukan objek"

    with caplog.at_level(logging.WARNING):
        baris = ratakan(hasil_komoditas, "komoditas")

    assert len(baris) == 1
    assert "1899" in caplog.text


@pytest.mark.unit
def test_anggota_iddesa_blok_tanpa_iddesa_tidak_melempar() -> None:
    """Filter `?iddesa=` tidak boleh jadi 500 karena satu blok poros cacat."""
    grup = {
        "poros": {"nmdesa": "TANPA IDDESA"},
        "anggota": [{"iddesa": "1801040002"}, {"nmdesa": "TANPA IDDESA"}],
    }

    assert anggota_iddesa(grup, "komoditas") == {"1801040002"}


@pytest.mark.unit
@pytest.mark.parametrize(
    ("fixture_nama", "varian", "jalan_kunci", "kunci_dibuang", "id_dilewati"),
    [
        (
            "hasil_gudang",
            "gudang-kopdes",
            ("1801", "gudang"),
            "volume",
            "1801-gudang-1",
        ),
        (
            "hasil_cold_storage",
            "cold-storage",
            ("1801", "cs_baru"),
            "lokasi",
            "1801-cs-baru-1",
        ),
        (
            "hasil_cold_storage",
            "cold-storage",
            ("1801", "cs_eksisting"),
            "kapasitas_ton",
            "1801-cs-eksisting-1",
        ),
        ("hasil_wisata", "wisata", ("1801", "kawasan"), "basis", "1801-kawasan-1"),
    ],
)
def test_grup_cacat_dilewati_di_tiap_varian(
    request: pytest.FixtureRequest,
    caplog: pytest.LogCaptureFixture,
    fixture_nama: str,
    varian: str,
    jalan_kunci: tuple[str, str],
    kunci_dibuang: str,
    id_dilewati: str,
) -> None:
    """Penjaga `_lewati` harus aktif di KEEMPAT pembangun varian, bukan hanya
    komoditas — tiap varian membaca kunci artefaknya sendiri."""
    hasil = request.getfixturevalue(fixture_nama)
    idkab, kunci_daftar = jalan_kunci
    daftar = hasil["kabupaten"][idkab][kunci_daftar]
    daftar[0] = {k: v for k, v in daftar[0].items() if k != kunci_dibuang}

    with caplog.at_level(logging.WARNING):
        baris = ratakan(hasil, varian)

    assert id_dilewati not in [b["id_jalur"] for b in baris]
    assert id_dilewati in caplog.text


@pytest.mark.unit
def test_maxsize_cache_mengikuti_pengaturan() -> None:
    """`maxsize` pembaca jalur ekonomi dibaca dari `Pengaturan`, bukan literal.

    `hasil_komoditas.json` terukur ±103 MB RAM per entri — cache inilah yang
    paling menentukan apakah instance 512 MB bertahan atau OOM.
    """
    assert baca_jalur.cache_info().maxsize == ambil_pengaturan().maks_cache_jalur
