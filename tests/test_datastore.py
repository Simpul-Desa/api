"""Uji unit untuk pemuat manifest & simpanan (src/datastore.py)."""

import json
import logging
from pathlib import Path
from typing import Any

import pytest

from src.datastore import Simpanan, muat_manifest, muat_simpanan


def _tulis_json(path: Path, isi: Any) -> None:
    """Tulis `isi` sebagai JSON ke `path`, membuat direktori induk bila perlu."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(isi), encoding="utf-8")


def _bangun_data_salinan_sintetis(dir_data: Path) -> None:
    """Bangun pohon `data-salinan/` sintetis mini: 1 provinsi, 2 kabupaten,
    4 desa (2 per kabupaten) — dipakai lintas uji `Simpanan` & pembaca LRU.
    """
    _tulis_json(
        dir_data / "wilayah.json",
        {
            "provinsi": [{"idprov": "18", "nama": "Lampung"}],
            "kabupaten": [
                {"idkab": "1801", "nmkab": "KAB SATU", "idprov": "18"},
                {"idkab": "1802", "nmkab": "KAB DUA", "idprov": "18"},
            ],
        },
    )

    baris_indeks = [
        {
            "iddesa": "1801000001",
            "nmdesa": "DESA A1",
            "nmkec": "KEC A",
            "idkab": "1801",
            "nmkab": "KAB SATU",
            "zona": "Zona Mitra",
            "keyakinan": "normal",
            "potensi_dominan": "Simpul Logistik",
            "desil_sp": 9,
            "desil_sk": 10,
            "n_program": 0,
        },
        {
            "iddesa": "1801000002",
            "nmdesa": "DESA A2",
            "nmkec": "KEC A",
            "idkab": "1801",
            "nmkab": "KAB SATU",
            "zona": "Belum Terpetakan",
            "keyakinan": "rendah",
            "potensi_dominan": "",
            "desil_sp": 1,
            "desil_sk": 1,
            "n_program": 0,
        },
        {
            "iddesa": "1802000001",
            "nmdesa": "DESA B1",
            "nmkec": "KEC B",
            "idkab": "1802",
            "nmkab": "KAB DUA",
            "zona": "Zona Poros",
            "keyakinan": "normal",
            "potensi_dominan": "Simpul Logistik",
            "desil_sp": 8,
            "desil_sk": 9,
            "n_program": 1,
        },
        {
            "iddesa": "1802000002",
            "nmdesa": "DESA B2",
            "nmkec": "KEC B",
            "idkab": "1802",
            "nmkab": "KAB DUA",
            "zona": "Zona Bantuan",
            "keyakinan": "normal",
            "potensi_dominan": "",
            "desil_sp": 5,
            "desil_sk": 5,
            "n_program": 0,
        },
    ]
    _tulis_json(dir_data / "kartu-ekonomi" / "indeks.json", baris_indeks)

    _tulis_json(
        dir_data / "kartu-ekonomi" / "kartu" / "1801.json",
        {
            "idkab": "1801",
            "nmkab": "KAB SATU",
            "n_wilayah": 2,
            "kartu": [
                {"identitas": {"iddesa": "1801000001", "nama": "DESA A1"}},
                {"identitas": {"iddesa": "1801000002", "nama": "DESA A2"}},
            ],
        },
    )
    _tulis_json(
        dir_data / "kartu-ekonomi" / "kartu" / "1802.json",
        {
            "idkab": "1802",
            "nmkab": "KAB DUA",
            "n_wilayah": 2,
            "kartu": [
                {"identitas": {"iddesa": "1802000001", "nama": "DESA B1"}},
                {"identitas": {"iddesa": "1802000002", "nama": "DESA B2"}},
            ],
        },
    )

    _tulis_json(
        dir_data / "peta-peran" / "peta_peran.json",
        [
            {**b, "idprov": "18", "sumber_dominan": "heuristik-belum-teruji"}
            for b in baris_indeks
        ],
    )
    _tulis_json(
        dir_data / "peta-peran" / "ringkasan_kab.json",
        {
            "1801": {"nmkab": "KAB SATU", "n_wilayah": 2},
            "1802": {"nmkab": "KAB DUA", "n_wilayah": 2},
        },
    )

    _tulis_json(
        dir_data / "citra-potensi" / "indeks.json",
        {
            "jumlah_sel": 1,
            "format_skor": "skor100_dlm_kab",
            "sel": [
                {
                    "prov": "18",
                    "target": "kom_prov_horti_01",
                    "nama": "Pisang",
                    "subsektor": "horti",
                    "mesin": "greedy",
                    "ap_uji_tertahan": 0.5,
                    "ci_rerata": [0.1, 0.2],
                    "berkas": "produksi/18/kom_prov_horti_01.json",
                }
            ],
        },
    )
    _tulis_json(
        dir_data / "citra-potensi" / "produksi" / "18" / "kom_prov_horti_01.json",
        {
            "meta": {},
            "validasi": {},
            "model": {},
            "format_skor": "skor100_dlm_kab",
            "skor": {"1801000001": [80.0, 90.0, 1, 2]},
        },
    )

    _tulis_json(
        dir_data / "jalur-ekonomi" / "hasil_komoditas.json",
        {
            "parameter": {"ambang": 0.5},
            "kabupaten": {"1801": {"nmkab": "KAB SATU", "komoditas": {}}},
            "ringkasan": {},
        },
    )

    _tulis_json(
        dir_data / "desa-kembar" / "1801.json",
        {
            "idkab": "1801",
            "k": 2,
            "p95_jarak": 10.0,
            "desa": {"1801000001": [{"iddesa": "1801000002", "persen": 50.0}]},
        },
    )

    _tulis_json(
        dir_data / "pusat_wilayah.json",
        {
            "kabupaten": [
                {"idkab": "1801", "pusat": [104.0, -5.0]},
                {"idkab": "1802", "pusat": [106.0, -6.0]},
            ]
        },
    )


@pytest.mark.unit
def test_dir_tanpa_manifest_kembalikan_none(tmp_path: Path) -> None:
    hasil = muat_manifest(tmp_path)

    assert hasil is None


@pytest.mark.unit
def test_dir_tidak_ada_kembalikan_none(tmp_path: Path) -> None:
    dir_tidak_ada = tmp_path / "tidak-ada"

    hasil = muat_manifest(dir_tidak_ada)

    assert hasil is None


@pytest.mark.unit
def test_manifest_valid_kembalikan_dict_persis(tmp_path: Path) -> None:
    isi = {"hash": "abc123", "tanggal": "2026-09-07"}
    (tmp_path / "manifest.json").write_text(json.dumps(isi), encoding="utf-8")

    hasil = muat_manifest(tmp_path)

    assert hasil == isi


@pytest.mark.unit
def test_manifest_json_korup_kembalikan_none_dan_warning(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    berkas_manifest = tmp_path / "manifest.json"
    berkas_manifest.write_text("{tidak-json", encoding="utf-8")

    with caplog.at_level(logging.WARNING):
        hasil = muat_manifest(tmp_path)

    assert hasil is None
    assert any(
        record.levelno == logging.WARNING
        and str(berkas_manifest) in record.getMessage()
        for record in caplog.records
    )


@pytest.mark.unit
def test_manifest_array_bukan_objek_kembalikan_none_dan_warning(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    berkas_manifest = tmp_path / "manifest.json"
    berkas_manifest.write_text("[1,2]", encoding="utf-8")

    with caplog.at_level(logging.WARNING):
        hasil = muat_manifest(tmp_path)

    assert hasil is None
    assert any(
        record.levelno == logging.WARNING
        and str(berkas_manifest) in record.getMessage()
        for record in caplog.records
    )


# --- Simpanan: muat_simpanan() ---------------------------------------------


@pytest.mark.unit
def test_muat_simpanan_lengkap_dari_data_sintetis(tmp_path: Path) -> None:
    _bangun_data_salinan_sintetis(tmp_path)

    simpanan = muat_simpanan(tmp_path)

    assert isinstance(simpanan, Simpanan)
    assert simpanan.dir_data == tmp_path
    assert simpanan.wilayah is not None
    assert simpanan.indeks_kartu is not None
    assert len(simpanan.indeks_kartu) == 4
    assert simpanan.peta_peran is not None
    assert len(simpanan.peta_peran) == 4
    # Assert ISI, bukan cuma keberadaan: `is not None` tetap lolos kalau
    # `muat_simpanan` memuat berkas yang benar ke FIELD yang salah (mis.
    # ringkasan_kab dan citra_indeks tertukar).
    assert simpanan.ringkasan_kab is not None
    assert simpanan.ringkasan_kab["1801"]["nmkab"] == "KAB SATU"
    assert simpanan.ringkasan_kab["1802"]["n_wilayah"] == 2
    assert simpanan.citra_indeks is not None
    assert simpanan.citra_indeks["jumlah_sel"] == 1
    assert simpanan.citra_indeks["sel"][0]["target"] == "kom_prov_horti_01"
    assert simpanan.ringkasan_wilayah is not None
    assert simpanan.pusat_wilayah is not None

    # indeks_per_desa: referensi ke baris yang sama (bukan salinan)
    assert simpanan.indeks_per_desa is not None
    baris = simpanan.indeks_per_desa["1801000001"]
    assert baris["nmdesa"] == "DESA A1"
    assert baris is simpanan.indeks_kartu[0]

    # desa_per_kab: pengelompokan per idkab
    assert simpanan.desa_per_kab is not None
    assert {b["iddesa"] for b in simpanan.desa_per_kab["1801"]} == {
        "1801000001",
        "1801000002",
    }
    assert {b["iddesa"] for b in simpanan.desa_per_kab["1802"]} == {
        "1802000001",
        "1802000002",
    }

    # peta_peran_per_desa: referensi ke baris yang sama (bukan salinan)
    assert simpanan.peta_peran_per_desa is not None
    baris_peran = simpanan.peta_peran_per_desa["1802000002"]
    assert baris_peran is simpanan.peta_peran[3]


@pytest.mark.unit
def test_muat_simpanan_artefak_hilang_kembalikan_none_tanpa_crash(
    tmp_path: Path,
) -> None:
    # tmp_path kosong sama sekali — tidak ada satu pun artefak data-salinan
    simpanan = muat_simpanan(tmp_path)

    assert isinstance(simpanan, Simpanan)
    assert simpanan.dir_data == tmp_path
    assert simpanan.wilayah is None
    assert simpanan.indeks_kartu is None
    assert simpanan.indeks_per_desa is None
    assert simpanan.desa_per_kab is None
    assert simpanan.peta_peran is None
    assert simpanan.peta_peran_per_desa is None
    assert simpanan.ringkasan_kab is None
    assert simpanan.citra_indeks is None
    assert simpanan.ringkasan_wilayah is None
    assert simpanan.pusat_wilayah is None


@pytest.mark.unit
def test_muat_simpanan_artefak_korup_kembalikan_none_dan_warning(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    _bangun_data_salinan_sintetis(tmp_path)
    (tmp_path / "wilayah.json").write_text("{tidak-json", encoding="utf-8")

    with caplog.at_level(logging.WARNING):
        simpanan = muat_simpanan(tmp_path)

    assert simpanan.wilayah is None
    assert simpanan.ringkasan_wilayah is None
    assert simpanan.pusat_wilayah is None
    assert any(
        record.levelno == logging.WARNING and "wilayah" in record.getMessage()
        for record in caplog.records
    )


@pytest.mark.unit
def test_muat_simpanan_ringkasan_wilayah_benar(tmp_path: Path) -> None:
    _bangun_data_salinan_sintetis(tmp_path)

    simpanan = muat_simpanan(tmp_path)

    assert simpanan.ringkasan_wilayah == {
        "n_provinsi": 1,
        "n_kabupaten": 2,
        "n_desa": 4,
        "per_provinsi": [
            {"idprov": "18", "nama": "Lampung", "n_kabupaten": 2, "n_desa": 4},
        ],
    }


# --- Simpanan: pusat_wilayah (Blok A rencana fase-1-fondasi, app/) ----------


@pytest.mark.unit
def test_muat_simpanan_pusat_wilayah_benar(tmp_path: Path) -> None:
    _bangun_data_salinan_sintetis(tmp_path)

    simpanan = muat_simpanan(tmp_path)

    assert simpanan.pusat_wilayah == {
        "provinsi": [
            {
                "idprov": "18",
                "nama": "Lampung",
                "pusat": [105.0, -5.5],
                "n_desa": 4,
                "n_kabupaten": 2,
            }
        ],
        "kabupaten": [
            {
                "idkab": "1801",
                "nmkab": "KAB SATU",
                "idprov": "18",
                "pusat": [104.0, -5.0],
                "n_desa": 2,
            },
            {
                "idkab": "1802",
                "nmkab": "KAB DUA",
                "idprov": "18",
                "pusat": [106.0, -6.0],
                "n_desa": 2,
            },
        ],
    }


@pytest.mark.unit
def test_muat_simpanan_pusat_wilayah_kab_tanpa_padanan_dilewati_dengan_warning(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """`pusat_wilayah.json` bisa lebih tua dari `wilayah.json` (build selektif)."""
    _bangun_data_salinan_sintetis(tmp_path)
    _tulis_json(
        tmp_path / "pusat_wilayah.json",
        {
            "kabupaten": [
                {"idkab": "1801", "pusat": [104.0, -5.0]},
                {"idkab": "9999", "pusat": [999.0, -9.0]},
            ]
        },
    )

    with caplog.at_level(logging.WARNING):
        simpanan = muat_simpanan(tmp_path)

    assert simpanan.pusat_wilayah is not None
    idkab_terlihat = {k["idkab"] for k in simpanan.pusat_wilayah["kabupaten"]}
    assert idkab_terlihat == {"1801"}
    assert any("9999" in record.getMessage() for record in caplog.records)


@pytest.mark.unit
def test_muat_simpanan_pusat_wilayah_provinsi_tanpa_kabupaten_dilewati_dengan_warning(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Provinsi baru di `wilayah.json` yang kabupatennya belum punya geo/pusat."""
    _bangun_data_salinan_sintetis(tmp_path)
    wilayah = json.loads((tmp_path / "wilayah.json").read_text(encoding="utf-8"))
    wilayah["provinsi"].append({"idprov": "33", "nama": "Jawa Tengah"})
    wilayah["kabupaten"].append({"idkab": "3301", "nmkab": "CILACAP", "idprov": "33"})
    _tulis_json(tmp_path / "wilayah.json", wilayah)
    # pusat_wilayah.json TIDAK diperbarui -- kab 3301 sengaja tanpa entri pusat

    with caplog.at_level(logging.WARNING):
        simpanan = muat_simpanan(tmp_path)

    assert simpanan.pusat_wilayah is not None
    idprov_terlihat = {p["idprov"] for p in simpanan.pusat_wilayah["provinsi"]}
    assert idprov_terlihat == {"18"}
    assert any("33" in record.getMessage() for record in caplog.records)


@pytest.mark.unit
def test_muat_simpanan_pusat_wilayah_kunci_kabupaten_absen_kembalikan_none(
    tmp_path: Path,
) -> None:
    """`pusat_wilayah.json` ada tapi kehilangan kunci `kabupaten` = artefak
    bukan yang diklaimnya -- kontrak folder ini menjawabnya 503
    DATA_BELUM_SIAP lewat `wajib()`, bukan 200 dengan daftar kosong."""
    _bangun_data_salinan_sintetis(tmp_path)
    _tulis_json(tmp_path / "pusat_wilayah.json", {})

    simpanan = muat_simpanan(tmp_path)

    assert simpanan.pusat_wilayah is None


@pytest.mark.unit
def test_muat_simpanan_pusat_wilayah_daftar_kabupaten_kosong_kembalikan_none(
    tmp_path: Path,
) -> None:
    """`pusat_wilayah.json` ada dengan kunci `kabupaten` tapi daftarnya
    kosong -- kondisi sama seperti kunci absen (mis. `--lewati-geo` pada
    `dir-keluaran` yang bersih), hasil rakitannya juga kosong."""
    _bangun_data_salinan_sintetis(tmp_path)
    _tulis_json(tmp_path / "pusat_wilayah.json", {"kabupaten": []})

    simpanan = muat_simpanan(tmp_path)

    assert simpanan.pusat_wilayah is None


@pytest.mark.unit
def test_muat_simpanan_pusat_wilayah_kab_wilayah_tanpa_pusat_dicatat_warning(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Arah sebaliknya dari `..._kab_tanpa_padanan_...` di atas: kabupaten
    ADA di `wilayah.json` tapi TIDAK punya entri di `pusat_wilayah.json` --
    sebelumnya dibuang senyap, sekarang dicatat `logger.warning`."""
    _bangun_data_salinan_sintetis(tmp_path)
    wilayah = json.loads((tmp_path / "wilayah.json").read_text(encoding="utf-8"))
    wilayah["kabupaten"].append({"idkab": "1803", "nmkab": "KAB TIGA", "idprov": "18"})
    _tulis_json(tmp_path / "wilayah.json", wilayah)
    # pusat_wilayah.json TIDAK diperbarui -- kab 1803 sengaja tanpa entri pusat

    with caplog.at_level(logging.WARNING):
        simpanan = muat_simpanan(tmp_path)

    assert simpanan.pusat_wilayah is not None
    assert any("1803" in record.getMessage() for record in caplog.records)
