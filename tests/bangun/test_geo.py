"""Uji unit untuk bangun/geo.py — simplifikasi GeoJSON batas desa + gzip."""

import gzip
import json
from pathlib import Path

import pytest

from bangun.geo import sederhanakan_berkas, sederhanakan_semua


def _titik_kotak_redundan() -> list[list[float]]:
    """Cincin poligon kotak ~200 titik, banyak titik kolinear redundan per sisi."""
    sudut = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0), (0.0, 0.0)]
    n_per_sisi = 50
    titik: list[list[float]] = []
    for i in range(4):
        x0, y0 = sudut[i]
        x1, y1 = sudut[i + 1]
        for j in range(n_per_sisi):
            t = j / n_per_sisi
            titik.append([x0 + (x1 - x0) * t, y0 + (y1 - y0) * t])
    titik.append(list(sudut[0]))
    return titik


def _koleksi_dua_fitur() -> dict[str, object]:
    fitur_valid = {
        "type": "Feature",
        "properties": {
            "index": 0,
            "kdprov": "18",
            "kdkab": "1804",
            "kdkec": "180401",
            "kddesa": "1804010001",
            "iddesa": "1801040001",
            "nmprov": "Lampung",
            "nmkab": "Lampung Timur",
            "nmkec": "Kec Uji",
            "nmdesa": "UJI",
            "sumber": "uji",
            "periode": 2024,
        },
        "geometry": {"type": "Polygon", "coordinates": [_titik_kotak_redundan()]},
    }
    fitur_kosong = {
        "type": "Feature",
        "properties": {
            "index": 1,
            "kdprov": "18",
            "kdkab": "1804",
            "kdkec": "180401",
            "kddesa": "1804010002",
            "iddesa": "1801040002",
            "nmprov": "Lampung",
            "nmkab": "Lampung Timur",
            "nmkec": "Kec Uji",
            "nmdesa": "KOSONG",
            "sumber": "uji",
            "periode": 2024,
        },
        "geometry": {"type": "Polygon", "coordinates": []},
    }
    return {"type": "FeatureCollection", "features": [fitur_valid, fitur_kosong]}


@pytest.mark.unit
def test_sederhanakan_berkas_membuang_fitur_kosong_dan_memangkas_properti(
    tmp_path: Path,
) -> None:
    sumber = tmp_path / "sumber.geojson"
    sumber.write_text(json.dumps(_koleksi_dua_fitur()), encoding="utf-8")
    tujuan = tmp_path / "keluaran" / "hasil.geojson.gz"

    hasil = sederhanakan_berkas(sumber, tujuan, toleransi=0.0005)

    assert hasil["n_fitur"] == 1
    assert hasil["n_dibuang"] == 1
    assert hasil["bytes_masuk"] == sumber.stat().st_size
    assert hasil["bytes_keluar"] < hasil["bytes_masuk"]

    assert tujuan.is_file()
    with gzip.open(tujuan, "rt", encoding="utf-8") as berkas:
        isi = json.load(berkas)

    assert isi["type"] == "FeatureCollection"
    assert len(isi["features"]) == 1
    assert isi["features"][0]["properties"] == {
        "iddesa": "1801040001",
        "nmdesa": "UJI",
        "pusat": [5.0, 5.0],
    }


@pytest.mark.unit
def test_sederhanakan_semua_satu_berkas_menghasilkan_satu_entri_manifest(
    tmp_path: Path,
) -> None:
    dir_sumber = tmp_path / "sumber"
    dir_sumber.mkdir()
    dir_tujuan = tmp_path / "tujuan"

    berkas_sumber = dir_sumber / "1801_uji.geojson"
    fitur = {
        "type": "Feature",
        "properties": {"iddesa": "1801040001", "nmdesa": "UJI"},
        "geometry": {
            "type": "Polygon",
            "coordinates": [[[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 0.0]]],
        },
    }
    koleksi = {"type": "FeatureCollection", "features": [fitur]}
    berkas_sumber.write_text(json.dumps(koleksi), encoding="utf-8")

    entri = sederhanakan_semua(dir_sumber, dir_tujuan, toleransi=0.0005)

    assert len(entri) == 1
    satu = entri[0]
    assert satu["path"] == "geo/1801.geojson.gz"
    assert satu["sumber"] == str(berkas_sumber)
    assert isinstance(satu["sha256"], str)
    assert len(satu["sha256"]) == 64
    bytes_keluar = satu["bytes"]
    assert isinstance(bytes_keluar, int)
    assert bytes_keluar > 0


@pytest.mark.unit
def test_sederhanakan_berkas_pusat_multipolygon_gabung_bbox_semua_bagian(
    tmp_path: Path,
) -> None:
    """MultiPolygon dua bagian TAK SIMETRIS (ukuran beda), jauh terpisah:
    `pusat` adalah tengah bbox GABUNGAN kedua bagian (satu titik untuk fitur
    ini), BUKAN rerata pusat tiap bagian dihitung terpisah. Kedua bagian
    sengaja dibuat beda ukuran supaya kedua formula menghasilkan titik
    BERBEDA — dua bagian berukuran sama (kotak-kongruen) membuat "tengah bbox
    gabungan" dan "rerata pusat tiap bagian" kebetulan sama, sehingga tidak
    bisa membedakan regresi copy-paste dari rumus `hitung_pusat_kabupaten`
    satu level di atas (yang justru MERATA-RATAKAN pusat antar desa, bukan
    menggabung bbox tiap desa)."""
    sumber = tmp_path / "sumber.geojson"
    fitur = {
        "type": "Feature",
        "properties": {"iddesa": "1801040003", "nmdesa": "PULAU"},
        "geometry": {
            "type": "MultiPolygon",
            "coordinates": [
                [
                    [
                        [100.0, 0.0],
                        [101.0, 0.0],
                        [101.0, 1.0],
                        [100.0, 1.0],
                        [100.0, 0.0],
                    ]
                ],
                [
                    [
                        [102.0, 2.0],
                        [110.0, 2.0],
                        [110.0, 3.0],
                        [102.0, 3.0],
                        [102.0, 2.0],
                    ]
                ],
            ],
        },
    }
    koleksi = {"type": "FeatureCollection", "features": [fitur]}
    sumber.write_text(json.dumps(koleksi), encoding="utf-8")
    tujuan = tmp_path / "keluaran" / "hasil.geojson.gz"

    sederhanakan_berkas(sumber, tujuan, toleransi=0.0005)

    with gzip.open(tujuan, "rt", encoding="utf-8") as berkas:
        isi = json.load(berkas)

    # bbox gabungan kedua bagian: lon 100..110, lat 0..3 -> tengah (105.0, 1.5).
    # Rerata pusat tiap bagian dihitung terpisah -- (100.5, 0.5) dan
    # (106.0, 2.5) -- menghasilkan (103.25, 1.5): beda di lon, jadi assertion
    # ini merah bila implementasi diam-diam beralih ke formula itu.
    assert isi["features"][0]["properties"]["pusat"] == [105.0, 1.5]


@pytest.mark.unit
def test_sederhanakan_berkas_pusat_dibulatkan_5_desimal(tmp_path: Path) -> None:
    """`pusat` dibulatkan ke 5 desimal: bbox sempit yang pusat mentahnya
    (0,0000095) butuh lebih dari 5 desimal membuktikan `round(...)` benar
    dipanggil, bukan kebetulan sama dengan nilai tak dibulatkan — assertion
    ini merah bila `round(...)` dihapus dari `bangun/geo.py`."""
    sumber = tmp_path / "sumber.geojson"
    fitur = {
        "type": "Feature",
        "properties": {"iddesa": "1801040005", "nmdesa": "SEMPIT"},
        "geometry": {
            "type": "Polygon",
            "coordinates": [
                [
                    [0.0, 0.0],
                    [0.000019, 0.0],
                    [0.000019, 10.0],
                    [0.0, 10.0],
                    [0.0, 0.0],
                ]
            ],
        },
    }
    koleksi = {"type": "FeatureCollection", "features": [fitur]}
    sumber.write_text(json.dumps(koleksi), encoding="utf-8")
    tujuan = tmp_path / "keluaran" / "hasil.geojson.gz"

    # bbox lon 0..0,000019 -> pusat lon mentah 0,0000095; round(x, 5) = 0,00001.
    sederhanakan_berkas(sumber, tujuan, toleransi=0.0000001)

    with gzip.open(tujuan, "rt", encoding="utf-8") as berkas:
        isi = json.load(berkas)

    assert isi["features"][0]["properties"]["pusat"] == [0.00001, 5.0]


@pytest.mark.unit
def test_sederhanakan_berkas_fitur_geometri_null_menggagalkan_build(
    tmp_path: Path,
) -> None:
    """Fitur ungeoreferenced (`geometry: null`, GeoJSON sah) MENGGAGALKAN
    build dengan `ValueError` bernama `iddesa`-nya — desa tanpa batas adalah
    masalah data di `data/` yang harus dibetulkan di sana, bukan baris yang
    boleh hilang diam-diam dari artefak geo yang disajikan `api/`. Ini
    memulihkan perilaku SEBELUM properti `pusat` ada
    (`shape(None)` dulu meledak `AttributeError` dan build gagal) dengan
    galat yang lebih terbaca, bukan menambah jalur baru."""
    sumber = tmp_path / "sumber.geojson"
    fitur_valid = {
        "type": "Feature",
        "properties": {"iddesa": "1801040001", "nmdesa": "UJI"},
        "geometry": {
            "type": "Polygon",
            "coordinates": [
                [[0.0, 0.0], [10.0, 0.0], [10.0, 10.0], [0.0, 10.0], [0.0, 0.0]]
            ],
        },
    }
    fitur_null = {
        "type": "Feature",
        "properties": {"iddesa": "1801040099", "nmdesa": "TANPA GEOMETRI"},
        "geometry": None,
    }
    koleksi = {"type": "FeatureCollection", "features": [fitur_valid, fitur_null]}
    sumber.write_text(json.dumps(koleksi), encoding="utf-8")
    tujuan = tmp_path / "keluaran" / "hasil.geojson.gz"

    with pytest.raises(ValueError, match="1801040099"):
        sederhanakan_berkas(sumber, tujuan, toleransi=0.0005)


@pytest.mark.unit
def test_sederhanakan_berkas_pusat_null_untuk_geometrycollection_tercatat_log(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """GeometryCollection lolos cek `is_empty` tapi `mapping()`-nya tidak
    punya kunci `coordinates` (hanya `geometries`), jadi `pusat_bbox_fitur`
    tidak menemukan satu titik koordinat pun -> `pusat: None` ditulis, dan
    `iddesa`-nya masuk `logger.warning` supaya baris tanpa `pusat` tidak
    hilang diam-diam sebelum sampai ke `app/`."""
    sumber = tmp_path / "sumber.geojson"
    fitur = {
        "type": "Feature",
        "properties": {"iddesa": "1801040006", "nmdesa": "KOLEKSI"},
        "geometry": {
            "type": "GeometryCollection",
            "geometries": [
                {
                    "type": "Polygon",
                    "coordinates": [[[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 0.0]]],
                }
            ],
        },
    }
    koleksi = {"type": "FeatureCollection", "features": [fitur]}
    sumber.write_text(json.dumps(koleksi), encoding="utf-8")
    tujuan = tmp_path / "keluaran" / "hasil.geojson.gz"

    with caplog.at_level("WARNING"):
        sederhanakan_berkas(sumber, tujuan, toleransi=0.0005)

    with gzip.open(tujuan, "rt", encoding="utf-8") as berkas:
        isi = json.load(berkas)

    assert isi["features"][0]["properties"]["pusat"] is None
    assert "1801040006" in caplog.text


@pytest.mark.unit
def test_sederhanakan_berkas_pusat_dihitung_dari_geometri_setelah_simplifikasi(
    tmp_path: Path,
) -> None:
    """`pusat` dihitung dari geometri SETELAH simplifikasi: toleransi besar
    memangkas tonjolan sudut sehingga bbox (dan pusat) berubah dari bbox
    geometri asli sebelum disederhanakan."""
    sumber = tmp_path / "sumber.geojson"
    fitur = {
        "type": "Feature",
        "properties": {"iddesa": "1801040004", "nmdesa": "TONJOLAN"},
        "geometry": {
            "type": "Polygon",
            "coordinates": [
                [
                    [0.0, 0.0],
                    [10.0, 0.0],
                    [10.0, 10.0],
                    [5.0, 10.05],
                    [0.0, 10.0],
                    [0.0, 0.0],
                ]
            ],
        },
    }
    koleksi = {"type": "FeatureCollection", "features": [fitur]}
    sumber.write_text(json.dumps(koleksi), encoding="utf-8")
    tujuan = tmp_path / "keluaran" / "hasil.geojson.gz"

    # bbox geometri asli (0,0,10,10.05) -> pusat (5, 5.025); toleransi besar
    # memangkas tonjolan 0,05 di sumbu lat, bbox setelah simplifikasi jadi
    # (0,0,10,10) -> pusat (5, 5).
    sederhanakan_berkas(sumber, tujuan, toleransi=0.1)

    with gzip.open(tujuan, "rt", encoding="utf-8") as berkas:
        isi = json.load(berkas)

    assert isi["features"][0]["properties"]["pusat"] == [5.0, 5.0]
