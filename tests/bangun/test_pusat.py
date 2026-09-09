"""Uji unit untuk bangun/pusat.py — bbox & pusat kabupaten dari geometri GeoJSON."""

import gzip
import json
import logging
from collections.abc import Mapping
from pathlib import Path

import pytest

from bangun.pusat import hitung_pusat_kabupaten, hitung_pusat_semua, tulis_pusat_wilayah

_POLIGON_SEDERHANA: dict[str, object] = {
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
}


def _koleksi(*geometri: Mapping[str, object]) -> dict[str, object]:
    """Bungkus satu atau lebih geometri jadi FeatureCollection minimal."""
    return {
        "type": "FeatureCollection",
        "features": [
            {"type": "Feature", "properties": {}, "geometry": g} for g in geometri
        ],
    }


def _tulis_gz(path: Path, isi: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(gzip.compress(json.dumps(isi).encode("utf-8")))


@pytest.mark.unit
def test_hitung_pusat_kabupaten_polygon_sederhana() -> None:
    pusat = hitung_pusat_kabupaten(_koleksi(_POLIGON_SEDERHANA))

    assert pusat == [104.05, -5.05]


@pytest.mark.unit
def test_hitung_pusat_kabupaten_multipolygon_gabung_bbox_semua_bagian() -> None:
    multi = {
        "type": "MultiPolygon",
        "coordinates": [
            [[[100.0, 0.0], [101.0, 0.0], [101.0, 1.0], [100.0, 1.0], [100.0, 0.0]]],
            [[[102.0, 2.0], [103.0, 2.0], [103.0, 3.0], [102.0, 3.0], [102.0, 2.0]]],
        ],
    }

    pusat = hitung_pusat_kabupaten(_koleksi(multi))

    # bbox gabungan kedua bagian: lon 100..103, lat 0..3 -> tengah (101.5, 1.5)
    assert pusat == [101.5, 1.5]


@pytest.mark.unit
def test_hitung_pusat_kabupaten_dua_fitur_sama_besar_rerata_titik_tengah() -> None:
    """Dua fitur bersisian berukuran sama: rerata dua tengah bbox KEBETULAN
    sama dengan tengah bbox gabungan keduanya — lihat test setelah ini untuk
    kasus dua fitur beda ukuran, tempat keduanya berbeda."""
    fitur_kedua = {
        "type": "Polygon",
        "coordinates": [
            [[104.1, -5.1], [104.2, -5.1], [104.2, -5.2], [104.1, -5.2], [104.1, -5.1]]
        ],
    }

    pusat = hitung_pusat_kabupaten(_koleksi(_POLIGON_SEDERHANA, fitur_kedua))

    # tengah bbox fitur 1 (104.05,-5.05) + fitur 2 (104.15,-5.15), rerata
    # keduanya (104.1,-5.1) — kebetulan sama dengan tengah bbox gabungan
    # karena kedua fitur berukuran sama & bersisian.
    assert pusat == [104.1, -5.1]


@pytest.mark.unit
def test_hitung_pusat_kabupaten_dua_fitur_beda_ukuran_rerata_bukan_gabungan() -> None:
    """Desa daratan besar + desa pulau kecil jauh: pusat = rerata DUA tengah
    bbox (satu per fitur), bukan tengah bbox gabungan keduanya — pencilan
    pulau kecil tidak boleh menyeret pusat kabupaten seperti pada bbox
    gabungan (lihat CLAUDE.md akar: kabupaten berpulau melenceng ke laut)."""
    daratan = {
        "type": "Polygon",
        "coordinates": [
            [[100.0, -5.0], [102.0, -5.0], [102.0, -3.0], [100.0, -3.0], [100.0, -5.0]]
        ],
    }
    pulau = {
        "type": "Polygon",
        "coordinates": [
            [[110.0, -6.0], [110.2, -6.0], [110.2, -5.8], [110.0, -5.8], [110.0, -6.0]]
        ],
    }

    pusat = hitung_pusat_kabupaten(_koleksi(daratan, pulau))

    # tengah bbox daratan (101.0,-4.0) + tengah bbox pulau (110.1,-5.9),
    # rerata keduanya (105.55,-4.95) — BUKAN tengah bbox gabungan (105.1,-4.5).
    assert pusat == [105.55, -4.95]


@pytest.mark.unit
def test_hitung_pusat_kabupaten_tanpa_fitur_kembalikan_none() -> None:
    kosong = {"type": "FeatureCollection", "features": []}

    assert hitung_pusat_kabupaten(kosong) is None


@pytest.mark.unit
def test_hitung_pusat_kabupaten_geometri_null_dilewati_tanpa_pengaruhi_bbox() -> None:
    """Fitur ungeoreferenced (`geometry: null`, GeoJSON sah) tidak menyumbang titik."""
    fitur_null: dict[str, object] = {
        "type": "Feature",
        "properties": {},
        "geometry": None,
    }
    koleksi = _koleksi(_POLIGON_SEDERHANA)
    fitur = koleksi["features"]
    assert isinstance(fitur, list)
    fitur.append(fitur_null)

    assert hitung_pusat_kabupaten(koleksi) == [104.05, -5.05]


@pytest.mark.unit
def test_hitung_pusat_kabupaten_geometri_koordinat_kosong_kembalikan_none() -> None:
    """Fitur dengan `coordinates: []` (dibuang `bangun/geo.py`) tidak menyumbang titik."""
    fitur_kosong = _koleksi({"type": "Polygon", "coordinates": []})

    assert hitung_pusat_kabupaten(fitur_kosong) is None


@pytest.mark.unit
def test_hitung_pusat_semua_melewati_berkas_kosong_dengan_warning(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    dir_geo = tmp_path / "geo"
    _tulis_gz(dir_geo / "1801.geojson.gz", _koleksi(_POLIGON_SEDERHANA))
    _tulis_gz(
        dir_geo / "1802.geojson.gz", {"type": "FeatureCollection", "features": []}
    )

    with caplog.at_level(logging.WARNING):
        hasil = hitung_pusat_semua(dir_geo)

    assert hasil == {"kabupaten": [{"idkab": "1801", "pusat": [104.05, -5.05]}]}
    assert any("1802" in record.getMessage() for record in caplog.records)


@pytest.mark.unit
def test_hitung_pusat_semua_direktori_tanpa_berkas_kembalikan_kosong(
    tmp_path: Path,
) -> None:
    dir_geo = tmp_path / "geo-kosong"
    dir_geo.mkdir()

    assert hitung_pusat_semua(dir_geo) == {"kabupaten": []}


@pytest.mark.unit
def test_hitung_pusat_semua_cacah_nol_log_warning_bukan_info(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Cacah nol (geo kosong/belum dibangun) dicatat WARNING, bukan INFO —
    artefak kosong ini nanti ditolak `src/datastore.py` (503 DATA_BELUM_SIAP)."""
    dir_geo = tmp_path / "geo-kosong"
    dir_geo.mkdir()

    with caplog.at_level(logging.WARNING):
        hasil = hitung_pusat_semua(dir_geo)

    assert hasil == {"kabupaten": []}
    assert any("0 kabupaten" in record.getMessage() for record in caplog.records)


@pytest.mark.unit
def test_hitung_pusat_semua_direktori_tak_ada_kembalikan_kosong(
    tmp_path: Path,
) -> None:
    """Direktori geo yang belum pernah dibangun (`--lewati-geo` pertama kali)."""
    dir_geo = tmp_path / "tidak-ada"

    assert hitung_pusat_semua(dir_geo) == {"kabupaten": []}


@pytest.mark.unit
def test_hitung_pusat_semua_urut_idkab(tmp_path: Path) -> None:
    dir_geo = tmp_path / "geo"
    _tulis_gz(dir_geo / "3301.geojson.gz", _koleksi(_POLIGON_SEDERHANA))
    _tulis_gz(dir_geo / "1801.geojson.gz", _koleksi(_POLIGON_SEDERHANA))

    hasil = hitung_pusat_semua(dir_geo)

    kabupaten = hasil["kabupaten"]
    assert isinstance(kabupaten, list)
    assert [k["idkab"] for k in kabupaten] == ["1801", "3301"]


@pytest.mark.unit
def test_tulis_pusat_wilayah_menulis_berkas_dan_round_trip(tmp_path: Path) -> None:
    dir_geo = tmp_path / "geo"
    _tulis_gz(dir_geo / "1801.geojson.gz", _koleksi(_POLIGON_SEDERHANA))
    dir_keluaran = tmp_path / "keluaran"

    path_keluaran = tulis_pusat_wilayah(dir_geo, dir_keluaran)

    assert path_keluaran == dir_keluaran / "pusat_wilayah.json"
    assert path_keluaran.is_file()

    isi = json.loads(path_keluaran.read_text(encoding="utf-8"))
    assert isi == hitung_pusat_semua(dir_geo)


@pytest.mark.unit
def test_tulis_pusat_wilayah_membuat_direktori_induk(tmp_path: Path) -> None:
    dir_geo = tmp_path / "geo"
    _tulis_gz(dir_geo / "1801.geojson.gz", _koleksi(_POLIGON_SEDERHANA))
    dir_keluaran = tmp_path / "sub" / "dir"

    path_keluaran = tulis_pusat_wilayah(dir_geo, dir_keluaran)

    assert path_keluaran.is_file()
